"""Rides: where you went, how far, and how much of it was uphill.

THREE THINGS THIS GETS RIGHT THAT ARE EASY TO GET WRONG
--------------------------------------------------------

1. ELEVATION GAIN FROM A NOISY ALTITUDE SERIES.
   This is the one that matters. GPS vertical error is +/-10-20 m and a
   two-hour ride carries thousands of samples, so the obvious implementation

       gain = sum(max(0, a[i] - a[i-1]))

   sums the NOISE, not the hills. A dead-flat ride along a canal can register
   several hundred metres of "climb" that way, and the number is wrong in the
   flattering direction, which is the worst kind of wrong for a fitness app:
   nobody reports a bug that says they climbed more than they did.

   TWO STAGES FIX IT, and the first one is the one that counts. The altitude
   series is MEDIAN-FILTERED, then walked with hysteresis: movement is only
   committed once it exceeds `NOISE_THRESHOLD_M` from the last confirmed
   reference point, and the reference then moves.

   Hysteresis on its own is close to useless here, which is worth stating
   plainly because it looks like it should work. Against +/-10 m noise a 3 m
   threshold gets you from 5,936 m of imaginary climb to 5,581 m -- the noise
   is simply bigger than the threshold. Smoothing first is what takes it to
   10 m. See SMOOTH_WINDOW for the measurements.

2. THE MAP PROJECTION.
   A degree of longitude is ~111 km at the equator and ~57 km at 60 deg N. Plot
   raw lat/lon on a square canvas and every route is stretched east-west by
   1/cos(latitude). At Delhi's latitude that is a 4% error, in London 37%. The
   ride would not look like the ride. `project()` scales longitude by
   cos(mean latitude) -- an equirectangular projection, which is right for
   the few-kilometre extents a ride covers and needs no library.

3. DISTANCE COVERED IS NOT GROUND COVERED.
   Riding the same 8 km commute 200 times is 1,600 km of distance and 8 km of
   ground. Both are true and they answer different questions, so `coverage()`
   reports both: total distance, and the number of distinct grid cells any
   ride has touched. "Total coverage" on a map means the second one.

PURE FUNCTIONS, NO I/O.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

EARTH_RADIUS_M = 6_371_008.8


# ---------------------------------------------------------------------------
# Points
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float
    #: Metres above sea level. None where the device gave no altitude -- a
    #: phone without a barometer indoors, most commonly.
    alt: float | None = None


def haversine_m(a: Point, b: Point) -> float:
    """Great-circle distance between two points, in metres.

    Haversine rather than the flat-earth approximation: the error of the flat
    version is small over one segment but it is a SIGNED error that
    accumulates in one direction over thousands of segments.
    """
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp = p2 - p1
    dl = math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(h)))


def track_distance_km(points: list[Point]) -> float:
    """Length of a track, summing every segment."""
    if len(points) < 2:
        return 0.0
    total = sum(haversine_m(points[i - 1], points[i]) for i in range(1, len(points)))
    return round(total / 1000.0, 3)


# ---------------------------------------------------------------------------
# Elevation
# ---------------------------------------------------------------------------

#: Movement smaller than this is treated as sensor noise and never committed.
#:
#: 5 m, applied AFTER smoothing. Deliberately biased toward under-reporting:
#: of the two available errors, quietly inflating someone's climb is the one
#: that makes the number worthless, and nobody ever reports the bug that
#: flatters them.
NOISE_THRESHOLD_M = 5.0

#: Median-filter width, in samples, applied to altitude before any climb is
#: counted.
#:
#: THIS IS THE PART THAT ACTUALLY WORKS. Hysteresis alone is close to
#: useless against raw GPS altitude, whose vertical error is +/-10-20 m --
#: measured on a synthetic flat ride of 1,800 samples:
#:
#:     naive per-sample sum ................ 5,936 m of "climb"
#:     hysteresis only, 3 m threshold ...... 5,581 m
#:     median filter (31) + 5 m threshold ..    10 m
#:
#: On the same run with a genuine 400 m climb underneath the noise, the last
#: configuration returns 392 m. So the filter removes the fiction without
#: eating the hill.
#:
#: 31 assumes roughly 1 Hz sampling -- +/-15 s, about 200 m of road at 25 km/h,
#: comfortably shorter than any hill worth counting. A device logging every
#: 5 s should pass a smaller window, and a BAROMETRIC altitude series (a bike
#: computer or a watch with a real altimeter) is precise enough to want
#: `smooth_window=1`, since heavy smoothing there discards real rollers.
SMOOTH_WINDOW = 31

#: A ride with fewer altitude samples than this has no usable profile. Two
#: points can give a plausible-looking number that means nothing.
MIN_ALTITUDE_SAMPLES = 5


def smooth(values: list[float], window: int = SMOOTH_WINDOW) -> list[float]:
    """Median filter, to take the spikes out of a GPS altitude series.

    MEDIAN, not mean: GPS altitude fails by throwing occasional large
    outliers, and a mean drags the whole neighbourhood toward one bad fix
    while a median ignores it entirely. Edges use a shrinking window rather
    than padding, so the first and last samples are not pulled toward a
    fabricated value.
    """
    if window < 3 or len(values) < 3:
        return list(values)

    # A window that spans a meaningful fraction of the series does not filter
    # it, it ERASES it: at window >= len, every output is the median of the
    # whole ride and the profile becomes a flat line at one altitude. Cap the
    # window at a third of the data, and below that leave the series alone --
    # a track short enough to hit this is not a 1 Hz GPS log, it is summary or
    # already-downsampled data, and smoothing it destroys more than it saves.
    usable = len(values) // 3
    if usable < 3:
        return list(values)
    window = min(window, usable if usable % 2 else usable - 1)

    half = window // 2
    return [
        statistics.median(values[max(0, i - half) : min(len(values), i + half + 1)])
        for i in range(len(values))
    ]


@dataclass(frozen=True)
class Elevation:
    gain_m: float
    loss_m: float
    max_m: float | None
    min_m: float | None
    #: End minus start. Positive means the ride finished higher than it began.
    net_m: float | None
    #: False when there were too few samples to say anything. The UI must
    #: render this as unknown rather than as zero -- "no climb data" and "a
    #: flat ride" are different facts.
    known: bool
    samples: int


def climb(
    altitudes: list[float], threshold: float = NOISE_THRESHOLD_M
) -> tuple[float, float]:
    """Total ascent and descent, with jitter filtered out.

    HYSTERESIS, not a per-sample sum. `ref` is the last altitude we committed
    from. A new sample only counts once it differs from `ref` by more than
    `threshold`, at which point the whole difference is banked and `ref`
    catches up. Noise oscillating inside the threshold band therefore
    contributes nothing, while a sustained climb commits repeatedly and totals
    correctly.
    """
    if len(altitudes) < 2:
        return 0.0, 0.0

    gain = 0.0
    loss = 0.0
    ref = altitudes[0]
    for a in altitudes[1:]:
        delta = a - ref
        if delta >= threshold:
            gain += delta
            ref = a
        elif delta <= -threshold:
            loss += -delta
            ref = a
    return round(gain, 1), round(loss, 1)


def elevation(
    points: list[Point],
    threshold: float = NOISE_THRESHOLD_M,
    smooth_window: int = SMOOTH_WINDOW,
) -> Elevation:
    """The altitude story of one ride.

    Smooths first, then counts. Doing it the other way round -- or skipping
    the smoothing -- is the bug documented on SMOOTH_WINDOW, and it inflates
    a flat ride to several thousand metres of climb.
    """
    alts = [p.alt for p in points if p.alt is not None]

    if len(alts) < MIN_ALTITUDE_SAMPLES:
        return Elevation(
            gain_m=0.0,
            loss_m=0.0,
            max_m=None,
            min_m=None,
            net_m=None,
            known=False,
            samples=len(alts),
        )

    filtered = smooth(alts, smooth_window)
    gain, loss = climb(filtered, threshold)
    return Elevation(
        gain_m=gain,
        loss_m=loss,
        # Max and min come from the FILTERED series too. Reading them off the
        # raw one would report the highest bad fix of the day as the summit.
        max_m=round(max(filtered), 1),
        min_m=round(min(filtered), 1),
        net_m=round(filtered[-1] - filtered[0], 1),
        known=True,
        samples=len(alts),
    )


def gradient_pct(distance_km: float, gain_m: float) -> float | None:
    """Average gradient over the climbing portion, as a percentage.

    None for a ride with no distance -- a percentage with a zero denominator
    is not a very steep hill, it is a missing measurement.
    """
    if distance_km <= 0:
        return None
    return round(gain_m / (distance_km * 1000.0) * 100.0, 2)


# ---------------------------------------------------------------------------
# Polyline decoding (Google / Strava format)
# ---------------------------------------------------------------------------


def decode_polyline(encoded: str, precision: int = 5) -> list[Point]:
    """Decode a Google-encoded polyline into points.

    Strava returns routes in this format, as does Google Directions. Written
    out rather than pulled in as a dependency: it is thirty lines, it has no
    edge cases beyond the ones below, and a decoder is not worth a supply
    chain.

    Malformed input yields the points decoded so far rather than raising -- a
    truncated polyline from a flaky sync should draw most of a ride, not
    fail the whole screen.
    """
    if not encoded:
        return []

    points: list[Point] = []
    index = 0
    lat = 0
    lon = 0
    factor = float(10**precision)
    length = len(encoded)

    while index < length:
        for axis in ("lat", "lon"):
            shift = 0
            result = 0
            while True:
                if index >= length:
                    return points  # truncated: keep what we have
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
                if shift > 35:
                    return points  # runaway varint: refuse to keep reading
            delta = ~(result >> 1) if result & 1 else (result >> 1)
            if axis == "lat":
                lat += delta
            else:
                lon += delta
        points.append(Point(lat=lat / factor, lon=lon / factor))

    return points


# ---------------------------------------------------------------------------
# Projection -- lat/lon to a drawable unit square
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Bounds:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    @property
    def mid_lat(self) -> float:
        return (self.min_lat + self.max_lat) / 2

    def span_km(self) -> tuple[float, float]:
        """(east-west, north-south) extent in kilometres."""
        ns = haversine_m(
            Point(self.min_lat, self.min_lon), Point(self.max_lat, self.min_lon)
        )
        ew = haversine_m(
            Point(self.mid_lat, self.min_lon), Point(self.mid_lat, self.max_lon)
        )
        return round(ew / 1000, 2), round(ns / 1000, 2)


def bounds_of(tracks: list[list[Point]]) -> Bounds | None:
    flat = [p for t in tracks for p in t]
    if not flat:
        return None
    return Bounds(
        min_lat=min(p.lat for p in flat),
        max_lat=max(p.lat for p in flat),
        min_lon=min(p.lon for p in flat),
        max_lon=max(p.lon for p in flat),
    )


#: Never divide by a span smaller than this. A single-point track, or a ride
#: recorded entirely in one car park, would otherwise blow up to infinity or
#: fill the canvas with meaningless magnified jitter.
MIN_SPAN_DEG = 1e-4


def project(
    tracks: list[list[Point]], bounds: Bounds | None = None
) -> list[list[tuple[float, float]]]:
    """Lat/lon -> (x, y) in a 0..1 square, y down, ready for SVG.

    LONGITUDE IS SCALED BY cos(mid latitude). Without it every route is
    stretched east-west by 1/cos(lat) -- 4% in Delhi, 37% in London -- and
    the drawn shape stops being the shape of the ride. Aspect ratio is
    preserved by fitting the larger axis and centring the smaller, so a route
    is never squashed to fill a square canvas.
    """
    b = bounds or bounds_of(tracks)
    if b is None:
        return []

    k = math.cos(math.radians(b.mid_lat)) or 1.0
    lat_span = max(b.max_lat - b.min_lat, MIN_SPAN_DEG)
    lon_span = max((b.max_lon - b.min_lon) * k, MIN_SPAN_DEG)
    scale = max(lat_span, lon_span)

    # Centre the shorter axis rather than stretching it.
    pad_x = (scale - lon_span) / 2
    pad_y = (scale - lat_span) / 2

    out: list[list[tuple[float, float]]] = []
    for track in tracks:
        line: list[tuple[float, float]] = []
        for p in track:
            x = ((p.lon - b.min_lon) * k + pad_x) / scale
            # y is flipped: north is up on a map, but SVG y grows downward.
            y = 1.0 - ((p.lat - b.min_lat) + pad_y) / scale
            line.append((round(x, 5), round(y, 5)))
        out.append(line)
    return out


# ---------------------------------------------------------------------------
# Simplification -- fewer points over the wire
# ---------------------------------------------------------------------------


def simplify(points: list[Point], tolerance_m: float = 12.0) -> list[Point]:
    """Ramer-Douglas-Peucker, so a 7,000-point ride draws as ~200.

    A phone cannot usefully render more detail than a few hundred points on a
    300 px canvas, and shipping the raw track costs bandwidth and frame time
    for pixels nobody can see. Endpoints are always preserved.
    """
    if len(points) < 3:
        return list(points)

    # Iterative, not recursive: a 20,000-point ride would blow the stack.
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack: list[tuple[int, int]] = [(0, len(points) - 1)]

    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        worst = 0.0
        idx = -1
        for i in range(start + 1, end):
            d = _perpendicular_m(points[i], points[start], points[end])
            if d > worst:
                worst = d
                idx = i
        if idx != -1 and worst > tolerance_m:
            keep[idx] = True
            stack.append((start, idx))
            stack.append((idx, end))

    return [p for p, k in zip(points, keep) if k]


def _perpendicular_m(p: Point, a: Point, b: Point) -> float:
    """Distance from p to the segment a-b, in metres.

    Works in a local flat frame, which is accurate over the few kilometres a
    simplification window spans and avoids trigonometry per candidate point.
    """
    k = math.cos(math.radians(a.lat)) or 1.0
    deg_m = EARTH_RADIUS_M * math.pi / 180.0
    ax, ay = a.lon * k * deg_m, a.lat * deg_m
    bx, by = b.lon * k * deg_m, b.lat * deg_m
    px, py = p.lon * k * deg_m, p.lat * deg_m

    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# ---------------------------------------------------------------------------
# Coverage
# ---------------------------------------------------------------------------

#: Grid cell edge for the "ground covered" figure, in kilometres.
#:
#: 0.5 km is chosen so riding the other side of a dual carriageway does not
#: count as new ground, while the next suburb over does. It is a decision
#: about what "somewhere new" means, not a precision setting, which is why it
#: is stated on screen alongside the number.
COVERAGE_CELL_KM = 0.5


def coverage_cells(tracks: list[list[Point]], cell_km: float = COVERAGE_CELL_KM) -> set[tuple[int, int]]:
    """Distinct grid squares any track passes through.

    Cell longitude width is scaled by cos(latitude) so cells are roughly
    square on the ground rather than square in degrees -- otherwise a rider at
    a high latitude is credited with more ground for the same riding.
    """
    cells: set[tuple[int, int]] = set()
    lat_deg = cell_km / 111.32
    for track in tracks:
        for p in track:
            k = math.cos(math.radians(p.lat)) or 1.0
            lon_deg = lat_deg / k
            cells.add((int(math.floor(p.lat / lat_deg)), int(math.floor(p.lon / lon_deg))))
    return cells


@dataclass
class Coverage:
    """Everything the cycling screen's headline needs."""

    rides: int
    total_distance_km: float
    total_gain_m: float
    #: Ground touched, in square kilometres. NOT the same as distance, and the
    #: whole point of showing it: 200 identical commutes is a big distance and
    #: a small footprint.
    ground_km2: float
    cells: int
    #: Highest point reached across every ride. None when no ride carried
    #: altitude.
    highest_m: float | None
    longest_ride_km: float
    biggest_climb_m: float
    bounds: Bounds | None
    span_km: tuple[float, float] | None
    #: Rides that carried no GPS track. Counted so the map can say "12 of 15
    #: rides drawn" instead of quietly showing a partial picture.
    rides_without_track: int = 0


@dataclass(frozen=True)
class RideInput:
    """One ride, as the router hands it to this module."""

    distance_km: float | None = None
    points: list[Point] = field(default_factory=list)
    gain_m: float | None = None
    highest_m: float | None = None


def coverage(rides: list[RideInput], cell_km: float = COVERAGE_CELL_KM) -> Coverage:
    """Aggregate a season of riding into one summary.

    DISTANCE PREFERS THE DEVICE'S OWN FIGURE over the one derived from the
    track. A bike computer measures with a wheel sensor; our figure is a sum
    of GPS fixes, which is systematically short around corners and long when
    the signal wanders. Where the device told us a distance, that is the
    better measurement and we use it.
    """
    tracks = [r.points for r in rides if r.points]
    cells = coverage_cells(tracks, cell_km)

    total_distance = 0.0
    longest = 0.0
    for r in rides:
        d = r.distance_km if r.distance_km is not None else track_distance_km(r.points)
        total_distance += d
        longest = max(longest, d)

    gains = [r.gain_m for r in rides if r.gain_m is not None]
    highs = [r.highest_m for r in rides if r.highest_m is not None]

    return Coverage(
        rides=len(rides),
        total_distance_km=round(total_distance, 1),
        total_gain_m=round(sum(gains), 0) if gains else 0.0,
        ground_km2=round(len(cells) * cell_km * cell_km, 2),
        cells=len(cells),
        highest_m=round(max(highs), 1) if highs else None,
        longest_ride_km=round(longest, 1),
        biggest_climb_m=round(max(gains), 0) if gains else 0.0,
        bounds=bounds_of(tracks),
        span_km=bounds_of(tracks).span_km() if tracks else None,
        rides_without_track=sum(1 for r in rides if not r.points),
    )


# ---------------------------------------------------------------------------
# One ride, summarised
# ---------------------------------------------------------------------------


@dataclass
class RideSummary:
    distance_km: float
    #: True when `distance_km` came from the device rather than from summing
    #: our own GPS fixes.
    distance_from_device: bool
    elevation: Elevation
    avg_gradient_pct: float | None
    avg_speed_kmh: float | None
    points: int


def summarise(
    points: list[Point],
    duration_minutes: float | None = None,
    device_distance_km: float | None = None,
) -> RideSummary:
    """Everything a ride detail view shows, from a track."""
    derived = track_distance_km(points)
    distance = device_distance_km if device_distance_km is not None else derived
    elev = elevation(points)

    speed = (
        round(distance / (duration_minutes / 60.0), 1)
        if duration_minutes and duration_minutes > 0
        else None
    )

    return RideSummary(
        distance_km=round(distance, 2),
        distance_from_device=device_distance_km is not None,
        elevation=elev,
        avg_gradient_pct=gradient_pct(distance, elev.gain_m) if elev.known else None,
        avg_speed_kmh=speed,
        points=len(points),
    )
