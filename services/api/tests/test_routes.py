"""Ride geometry. TestElevationNoise is the class that matters."""

import math
import random

import pytest

from app.services import routes
from app.services.routes import Point


def flat_track(n=20, lat=28.61, lon=77.20, step=0.001, alt=None):
    """A straight eastward line, optionally at constant altitude."""
    return [Point(lat, lon + i * step, alt) for i in range(n)]


class TestDistance:
    def test_a_known_distance(self):
        # One degree of latitude is ~111.19 km.
        d = routes.haversine_m(Point(0, 0), Point(1, 0))
        assert d == pytest.approx(111_195, rel=0.001)

    def test_longitude_shrinks_with_latitude(self):
        at_equator = routes.haversine_m(Point(0, 0), Point(0, 1))
        at_sixty = routes.haversine_m(Point(60, 0), Point(60, 1))
        # cos(60) = 0.5, so the same degree is half the distance.
        assert at_sixty == pytest.approx(at_equator * 0.5, rel=0.01)

    def test_a_track_sums_its_segments(self):
        km = routes.track_distance_km(flat_track(n=11, step=0.01))
        # 10 segments of 0.01 deg longitude at 28.6 N
        one = routes.haversine_m(Point(28.61, 77.20), Point(28.61, 77.21))
        assert km == pytest.approx(one * 10 / 1000, rel=0.01)

    def test_a_single_point_has_no_length(self):
        assert routes.track_distance_km([Point(1, 1)]) == 0.0

    def test_an_empty_track_has_no_length(self):
        assert routes.track_distance_km([]) == 0.0


class TestElevationNoise:
    """THE CLASS THAT KEEPS CLIMB FIGURES HONEST.

    GPS vertical error is +/-10-20 m and a two-hour ride carries thousands of
    samples, so summing every positive sample-to-sample delta sums the noise:
    a flat canal ride comes back claiming several THOUSAND metres of climb.
    The error flatters the user, so nobody ever reports it.

    These use realistic +/-10 m noise deliberately. An earlier version of this
    class tested +/-2 m, which every implementation passes -- including the
    broken ones -- and so proved nothing.

    If you are here because this failed: either the median filter was removed,
    or the smoothing now runs after the counting instead of before. Every
    climb figure in the app is currently fiction.
    """

    def flat_ride(self, n=1800, noise=10.0, seed=7):
        rnd = random.Random(seed)
        return [Point(28.6, 77.2, 100 + rnd.uniform(-noise, noise)) for _ in range(n)]

    def climbing_ride(self, n=1800, gain=400.0, noise=10.0, seed=7):
        """A genuine `gain` climbed over the first half, given back on the second."""
        rnd = random.Random(seed)
        out = []
        for i in range(n):
            true = gain * (i / (n / 2)) if i < n / 2 else gain * (2 - i / (n / 2))
            out.append(Point(28.6, 77.2, 100 + true + rnd.uniform(-noise, noise)))
        return out

    def test_a_flat_ride_reports_essentially_no_climb(self):
        e = routes.elevation(self.flat_ride())
        assert e.gain_m < 60          # ~30 minutes of flat riding

    def test_the_naive_sum_would_have_claimed_thousands_of_metres(self):
        # The bug this class exists to prevent, stated as arithmetic.
        alts = [p.alt for p in self.flat_ride()]
        naive = sum(max(0, alts[i] - alts[i - 1]) for i in range(1, len(alts)))
        assert naive > 5000                              # what the bug reports
        assert routes.elevation(self.flat_ride()).gain_m < 60   # what we report

    def test_hysteresis_alone_would_not_have_saved_us(self):
        """The measurement that drove the design.

        A threshold is the obvious fix and it looks like it should work. It
        does not: the noise is simply bigger than any threshold small enough
        to keep real hills. Smoothing is what does the work.
        """
        alts = [p.alt for p in self.flat_ride()]
        unsmoothed = routes.climb(alts, threshold=3.0)[0]
        assert unsmoothed > 4000
        assert routes.elevation(self.flat_ride()).gain_m < 60

    def test_a_real_climb_survives_the_filter(self):
        # The filter must remove the fiction without eating the hill.
        e = routes.elevation(self.climbing_ride(gain=400))
        assert e.gain_m == pytest.approx(400, abs=40)

    def test_and_the_descent_with_it(self):
        e = routes.elevation(self.climbing_ride(gain=400))
        assert e.loss_m == pytest.approx(400, abs=40)

    def test_an_out_and_back_gains_and_loses_the_same(self):
        e = routes.elevation(self.climbing_ride(gain=400))
        assert e.gain_m == pytest.approx(e.loss_m, abs=40)

    def test_a_bigger_climb_reads_bigger(self):
        small = routes.elevation(self.climbing_ride(gain=200)).gain_m
        big = routes.elevation(self.climbing_ride(gain=800)).gain_m
        assert big > small * 3

    def test_the_summit_is_not_the_worst_gps_fix_of_the_day(self):
        """max_m comes off the FILTERED series.

        Read from the raw one, a single bad fix becomes the day's summit and
        the rider is told they topped out 20 m higher than they did.
        """
        ride = self.climbing_ride(gain=400, noise=0.0)
        spiked = list(ride)
        spiked[900] = Point(28.6, 77.2, 9999.0)   # one absurd fix
        assert routes.elevation(spiked).max_m == pytest.approx(
            routes.elevation(ride).max_m, abs=5
        )

    def test_smoothing_a_short_series_is_a_no_op_rather_than_a_crash(self):
        assert routes.smooth([1.0, 2.0]) == [1.0, 2.0]

    def test_the_median_ignores_an_outlier_a_mean_would_smear(self):
        vals = [10.0] * 10 + [500.0] + [10.0] * 10
        assert max(routes.smooth(vals, 9)) == 10.0

    def test_a_barometric_series_can_opt_out_of_smoothing(self):
        """A real altimeter resolves ~1 m, so it can count smaller rollers.

        The GPS defaults deliberately cannot: 4 m of rise is inside the noise
        floor of a phone and counting it would be counting nothing.
        """
        rollers = [Point(28.6, 77.2, 100 + (4 if i % 40 < 20 else 0)) for i in range(400)]
        assert routes.elevation(rollers).gain_m == 0.0
        assert routes.elevation(rollers, threshold=3.0, smooth_window=1).gain_m > 30

    def test_climb_hysteresis_still_totals_a_clean_series(self):
        gain, loss = routes.climb([float(i) for i in range(101)])
        assert gain == pytest.approx(100, abs=6)
        assert loss == 0.0

    def test_a_single_sample_is_not_a_profile(self):
        assert routes.climb([100.0]) == (0.0, 0.0)


class TestElevationSummary:
    def test_reports_max_and_min(self):
        pts = [Point(1, 1, a) for a in (100, 250, 180, 300, 220)]
        e = routes.elevation(pts)
        assert e.max_m == 300
        assert e.min_m == 100

    def test_net_is_end_minus_start(self):
        pts = [Point(1, 1, a) for a in (100, 250, 180, 300, 220)]
        assert routes.elevation(pts).net_m == 120

    def test_too_few_samples_is_unknown_not_zero(self):
        # "No climb data" and "a flat ride" are different facts and must not
        # render the same way.
        e = routes.elevation([Point(1, 1, 100), Point(1, 1, 200)])
        assert e.known is False
        assert e.max_m is None

    def test_a_track_with_no_altitude_at_all_is_unknown(self):
        e = routes.elevation(flat_track(n=50))
        assert e.known is False
        assert e.samples == 0

    def test_points_missing_altitude_are_skipped_not_zeroed(self):
        # A zero would read as sea level and destroy the minimum.
        pts = [Point(1, 1, 100), Point(1, 1, None), Point(1, 1, 110),
               Point(1, 1, 120), Point(1, 1, 130), Point(1, 1, 140)]
        e = routes.elevation(pts)
        assert e.min_m == 100
        assert e.samples == 5

    def test_gradient_is_climb_over_distance(self):
        assert routes.gradient_pct(10.0, 500.0) == 5.0

    def test_gradient_refuses_a_zero_denominator(self):
        assert routes.gradient_pct(0, 500) is None


class TestPolyline:
    def test_decodes_the_reference_example(self):
        # The example from Google's own polyline documentation.
        pts = routes.decode_polyline("_p~iF~ps|U_ulLnnqC_mqNvxq`@")
        assert len(pts) == 3
        assert pts[0].lat == pytest.approx(38.5)
        assert pts[0].lon == pytest.approx(-120.2)
        assert pts[1].lat == pytest.approx(40.7)
        assert pts[1].lon == pytest.approx(-120.95)
        assert pts[2].lat == pytest.approx(43.252)

    def test_an_empty_string_is_an_empty_track(self):
        assert routes.decode_polyline("") == []

    def test_truncated_input_returns_what_it_could_read(self):
        # A flaky sync should draw most of a ride, not fail the screen.
        full = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
        partial = routes.decode_polyline(full[:11])
        assert len(partial) >= 1
        assert partial[0].lat == pytest.approx(38.5)

    def test_garbage_does_not_hang_or_raise(self):
        assert isinstance(routes.decode_polyline("!!!!!!!!"), list)


class TestProjection:
    def test_output_is_inside_the_unit_square(self):
        out = routes.project([flat_track(n=30)])
        for x, y in out[0]:
            assert 0.0 <= x <= 1.0
            assert 0.0 <= y <= 1.0

    def test_north_is_up(self):
        # SVG y grows downward, so the northern point must have the SMALLER y.
        track = [Point(28.60, 77.20), Point(28.70, 77.20)]
        (south, north) = routes.project([track])[0]
        assert north[1] < south[1]

    def test_longitude_is_scaled_by_latitude(self):
        """A square in degrees is NOT a square on the ground.

        Without the cos(lat) correction a route at 60 N is stretched to twice
        its true east-west extent and stops looking like the ride.
        """
        # 0.1 deg each way at 60 N: on the ground that is ~11 km north-south
        # and ~5.5 km east-west, so the drawn shape must be twice as tall.
        track = [Point(60.0, 0.0), Point(60.1, 0.1)]
        pts = routes.project([track])[0]
        width = abs(pts[1][0] - pts[0][0])
        height = abs(pts[1][1] - pts[0][1])
        assert height == pytest.approx(width * 2, rel=0.05)

    def test_aspect_ratio_is_preserved_not_stretched(self):
        # A long thin ride must draw long and thin, centred, not filled.
        track = [Point(28.60, 77.20), Point(28.61, 77.60)]
        pts = routes.project([track])[0]
        assert abs(pts[1][1] - pts[0][1]) < 0.2   # barely any vertical extent
        assert abs(pts[1][0] - pts[0][0]) > 0.8   # fills horizontally

    def test_a_stationary_track_does_not_divide_by_zero(self):
        out = routes.project([[Point(28.61, 77.20)] * 5])
        assert all(0 <= x <= 1 and 0 <= y <= 1 for x, y in out[0])

    def test_many_tracks_share_one_frame(self):
        # Otherwise each ride is drawn to its own scale and the composite map
        # is meaningless.
        a = [Point(28.60, 77.20), Point(28.61, 77.21)]
        b = [Point(28.70, 77.30), Point(28.71, 77.31)]
        out = routes.project([a, b])
        # Projected together, the two tracks sit at opposite corners. Projected
        # separately each would fill its own frame and the composite map would
        # be meaningless.
        assert out[0][0][1] > out[1][0][1]      # a is south of b -> larger y
        assert out[0][0][0] < out[1][0][0]      # a is west of b  -> smaller x
        alone = routes.project([a])[0]
        assert abs(alone[1][0] - alone[0][0]) > abs(out[0][1][0] - out[0][0][0])

    def test_an_empty_input_projects_to_nothing(self):
        assert routes.project([]) == []


class TestSimplify:
    def test_a_straight_line_collapses_to_its_ends(self):
        assert len(routes.simplify(flat_track(n=50))) == 2

    def test_a_corner_survives(self):
        track = [Point(28.60, 77.20), Point(28.60, 77.25), Point(28.65, 77.25)]
        assert len(routes.simplify(track)) == 3

    def test_endpoints_are_always_kept(self):
        track = flat_track(n=50)
        out = routes.simplify(track)
        assert out[0] == track[0]
        assert out[-1] == track[-1]

    def test_a_short_track_is_returned_intact(self):
        track = [Point(1, 1), Point(2, 2)]
        assert routes.simplify(track) == track

    def test_a_huge_track_does_not_blow_the_stack(self):
        # Iterative, not recursive -- a 20,000-point ride is normal.
        big = [Point(28.6 + i * 1e-5, 77.2 + math.sin(i / 50) * 1e-3) for i in range(20_000)]
        assert len(routes.simplify(big)) < len(big)

    def test_it_keeps_the_shape(self):
        big = [Point(28.6 + i * 1e-4, 77.2 + math.sin(i / 20) * 1e-3) for i in range(500)]
        before = routes.track_distance_km(big)
        after = routes.track_distance_km(routes.simplify(big, tolerance_m=5))
        assert after == pytest.approx(before, rel=0.1)


class TestCoverage:
    def ride(self, **kw):
        return routes.RideInput(**kw)

    def test_totals_the_distances(self):
        c = routes.coverage([self.ride(distance_km=20), self.ride(distance_km=15)])
        assert c.total_distance_km == 35.0

    def test_the_device_figure_beats_our_derived_one(self):
        # A wheel sensor measures; a sum of GPS fixes approximates.
        c = routes.coverage([self.ride(distance_km=42.0, points=flat_track(n=5))])
        assert c.total_distance_km == 42.0

    def test_it_falls_back_to_the_track_when_no_device_figure(self):
        c = routes.coverage([self.ride(points=flat_track(n=11, step=0.01))])
        assert c.total_distance_km > 0

    def test_ground_covered_is_not_the_same_as_distance(self):
        """The distinction the whole feature rests on.

        The same commute ridden 200 times is a huge distance across a tiny
        patch of ground. Reporting only distance would tell someone they had
        covered the country.
        """
        commute = flat_track(n=20, step=0.001)
        many = [self.ride(points=commute, distance_km=8) for _ in range(200)]
        c = routes.coverage(many)
        assert c.total_distance_km == 1600.0
        assert c.ground_km2 < 3.0

    def test_riding_somewhere_new_grows_the_ground(self):
        here = flat_track(n=20, lat=28.61, lon=77.20)
        far = flat_track(n=20, lat=19.07, lon=72.87)
        one = routes.coverage([self.ride(points=here)])
        two = routes.coverage([self.ride(points=here), self.ride(points=far)])
        assert two.ground_km2 > one.ground_km2

    def test_reports_the_biggest_climb_and_the_highest_point(self):
        c = routes.coverage([
            self.ride(gain_m=400, highest_m=1200),
            self.ride(gain_m=900, highest_m=800),
        ])
        assert c.biggest_climb_m == 900
        assert c.highest_m == 1200

    def test_rides_with_no_track_are_counted_not_hidden(self):
        # So the map can say "12 of 15 drawn" instead of quietly lying.
        c = routes.coverage([
            self.ride(distance_km=10),
            self.ride(distance_km=10, points=flat_track()),
        ])
        assert c.rides == 2
        assert c.rides_without_track == 1

    def test_no_rides_is_all_zeroes_and_no_bounds(self):
        c = routes.coverage([])
        assert c.rides == 0
        assert c.total_distance_km == 0
        assert c.bounds is None
        assert c.highest_m is None

    def test_no_altitude_anywhere_leaves_the_highest_point_unknown(self):
        c = routes.coverage([self.ride(distance_km=10, points=flat_track())])
        assert c.highest_m is None
        assert c.biggest_climb_m == 0.0


class TestSummarise:
    def test_prefers_the_device_distance(self):
        s = routes.summarise(flat_track(n=20), device_distance_km=12.5)
        assert s.distance_km == 12.5
        assert s.distance_from_device is True

    def test_derives_distance_when_the_device_gave_none(self):
        s = routes.summarise(flat_track(n=11, step=0.01))
        assert s.distance_km > 0
        assert s.distance_from_device is False

    def test_average_speed(self):
        s = routes.summarise([], duration_minutes=60, device_distance_km=30)
        assert s.avg_speed_kmh == 30.0

    def test_a_zero_duration_gives_no_speed_rather_than_infinity(self):
        s = routes.summarise([], duration_minutes=0, device_distance_km=30)
        assert s.avg_speed_kmh is None

    def test_gradient_is_none_when_elevation_is_unknown(self):
        s = routes.summarise(flat_track(n=20), device_distance_km=10)
        assert s.elevation.known is False
        assert s.avg_gradient_pct is None
