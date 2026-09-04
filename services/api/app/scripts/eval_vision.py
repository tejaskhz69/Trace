"""Run the eval set through the scan pipeline and write results.json.

DIVISION OF LABOUR
This is the RUNNER only. It reads `eval/manifest.csv`, sends each photo
through `vision.recognize()`, and writes a results file. The scoring --
coverage, MAPE, bias, the adversarial behaviour check -- lives in
`eval/score.py`, which already does it well. Two scorers would drift.

    python -m app.scripts.eval_vision --dry-run     # no API calls
    python -m app.scripts.eval_vision               # writes eval/results.json
    cd ../.. && python eval/score.py --results eval/results.json

RATE LIMITS
The free tier allows ~20 requests before it 429s, and a scan that escalates
costs two. The default --delay is therefore deliberately slow, and the runner
backs off and resumes rather than dying halfway through a 25-photo set.

RESUMABILITY
Existing results are loaded and skipped, so an interrupted run continues where
it stopped instead of burning quota re-scanning what already worked.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from pathlib import Path

# services/api/app/scripts/eval_vision.py -> repo root
ROOT = Path(__file__).resolve().parents[4]
EVAL = ROOT / "eval"
MANIFEST = EVAL / "manifest.csv"
PHOTOS = EVAL / "photos"
DEFAULT_OUT = EVAL / "results.json"

PLACEHOLDER_NOTE = (
    "Placeholders are rendered cards, not food. A scan of one measures nothing "
    "except that the pipeline runs -- and each card says so in its own footer."
)


def load_rows() -> list[dict]:
    if not MANIFEST.exists():
        raise SystemExit(f"No manifest at {MANIFEST}")
    with MANIFEST.open(encoding="utf-8-sig", newline="") as fh:
        return [r for r in csv.DictReader(fh) if (r.get("file") or "").strip()]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Check the manifest and photos without calling the API.")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--cuisine")
    ap.add_argument("--no-hint", action="store_true",
                    help="Withhold the dish name. Harder, and closer to a cold scan.")
    ap.add_argument("--delay", type=float, default=8.0,
                    help="Seconds between scans. The free tier 429s below ~8s.")
    ap.add_argument("--fresh", action="store_true",
                    help="Ignore existing results and re-scan everything.")
    args = ap.parse_args()

    rows = load_rows()
    if args.cuisine:
        rows = [r for r in rows if r.get("cuisine") == args.cuisine]

    missing = [r["file"] for r in rows if not (PHOTOS / r["file"]).exists()]
    present = [r for r in rows if (PHOTOS / r["file"]).exists()]

    print(f"manifest rows : {len(rows)}")
    print(f"photos found  : {len(present)}")
    if missing:
        print(f"photos missing: {len(missing)}")
        for m in missing[:5]:
            print(f"   {m}")
        if len(missing) > 5:
            print(f"   ... and {len(missing) - 5} more")

    filled = sum(1 for r in present if (r.get("truth_kcal") or "").strip())
    print(f"truth filled  : {filled}/{len(present)}")
    if filled == 0:
        print("\nNOTE: no truth_kcal values are filled in yet, so score.py will")
        print("have nothing to score. Running now still exercises the pipeline")
        print("and the adversarial behaviour check, but produces no accuracy.")

    if args.dry_run:
        print("\nDry run: no API calls made.")
        return

    from ..config import get_settings
    if not get_settings().GEMINI_API_KEY:
        raise SystemExit("GEMINI_API_KEY is not set in services/api/.env")
    from ..services import vision

    done: dict[str, dict] = {}
    if args.out.exists() and not args.fresh:
        try:
            done = {r["file"]: r for r in json.loads(args.out.read_text())}
            print(f"resuming: {len(done)} already scanned (use --fresh to redo)")
        except (ValueError, KeyError):
            print("existing results file unreadable -- starting fresh")

    todo = [r for r in present if r["file"] not in done]
    if args.limit:
        todo = todo[: args.limit]

    for i, row in enumerate(todo, 1):
        name = row["file"]
        print(f"  [{i}/{len(todo)}] {name} ...", end="", flush=True)
        raw = (PHOTOS / name).read_bytes()
        hint = None if args.no_hint else (row.get("dish") or None)

        for attempt in range(4):
            try:
                res = await vision.recognize(raw, hint=hint)
                items = res.payload.get("items", [])
                done[name] = {
                    "file": name,
                    "kcal": sum(i_["kcal_point"] for i_ in items),
                    "kcal_low": sum(i_["kcal_low"] for i_ in items),
                    "kcal_high": sum(i_["kcal_high"] for i_ in items),
                    "confidence": res.payload.get("overall_confidence", 0.0),
                    "n_items": len(items),
                    "asked_question": any(i_.get("clarifying_question") for i_ in items),
                    "model": res.model_used,
                    "latency_ms": res.latency_ms,
                    "cost_usd": res.cost_usd,
                    # score.py grades the adversarial rows on this key by name.
                    # Without it the scorer falls back to band-and-confidence
                    # and an explicit refusal can never be credited -- which
                    # is the one behaviour those rows exist to measure.
                    "refused": bool(res.payload.get("refused", False)),
                    "refusal_reason": res.payload.get("refusal_reason", ""),
                }
                if done[name]["refused"]:
                    # A refusal has no items, so the kcal line would read
                    # "0 kcal, conf 0.00" and look like a crash. It is a pass.
                    reason = done[name]["refusal_reason"] or "no reason given"
                    print(f" REFUSED -- {reason[:70]}")
                else:
                    print(
                        f" {done[name]['kcal']:.0f} kcal, "
                        f"conf {done[name]['confidence']:.2f}"
                    )
                break
            except Exception as exc:
                msg = re.sub(r"(key=)[^&\s]+", r"\1<redacted>", str(exc))
                m = re.search(r"retry in ([\d.]+)s", msg)
                if m or "429" in msg:
                    wait = float(m.group(1)) + 3 if m else 45
                    print(f" rate-limited, waiting {wait:.0f}s", end="", flush=True)
                    await asyncio.sleep(wait)
                    continue
                print(f" FAILED: {type(exc).__name__}: {msg[:120]}")
                break
        else:
            print(" gave up after 4 attempts")

        # Write after every scan so an interrupt never loses completed work.
        args.out.write_text(json.dumps(list(done.values()), indent=2))
        if i < len(todo):
            await asyncio.sleep(args.delay)

    print(f"\n{len(done)} result(s) -> {args.out}")
    print(f"Now score them:\n  python eval/score.py --results {args.out}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
