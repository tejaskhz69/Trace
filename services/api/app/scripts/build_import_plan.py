"""Build the deterministic alias import plan from the review artifact.

    python -m app.scripts.build_import_plan

Pure file-to-file: reads `review/generated_aliases.json`, writes
`review/alias_import_plan.json`. Touches no database at all -- it does not
import SQLAlchemy and cannot open a connection.

The plan contains ONLY the final provisional import set: candidates classified
`import_ready`, which by construction have exactly one target and are not
empty, broad, duplicated, ambiguous, bare-brand, or excluded pending review.
Everything held back is summarised with its reason, so the plan is auditable
against the artifact it came from.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

from ..services.alias_gen import EXCLUDED_PENDING_REVIEW, GENERATOR_VERSION

DEFAULT_IN = pathlib.Path("review") / "generated_aliases.json"
DEFAULT_OUT = pathlib.Path("review") / "alias_import_plan.json"

PLAN_VERSION = "1.0"

#: Every field a reviewer needs to judge one row, and every field the importer
#: needs to write it. Ordered for readability; the JSON is key-sorted anyway.
PLAN_FIELDS = (
    "food_item_id", "target_name", "alias", "normalized", "alias_type",
    "source", "rule", "reason", "confidence", "script", "lang",
    "generator_version",
)


def build(artifact: dict) -> dict:
    ready = artifact.get("import_ready", [])
    findings = artifact.get("findings", [])
    counts = artifact.get("counts", {})

    rows = []
    for r in ready:
        rows.append({
            "food_item_id": r["food_item_id"],
            "target_name": r.get("target_name", ""),
            "alias": r["alias"],
            "normalized": r["normalized"],
            "alias_type": r["alias_type"],
            "source": r["source"],
            "rule": r["rule"],
            "reason": r["reason"],
            "confidence": r["confidence"],
            "script": r["script"],
            "lang": r["lang"],
            "generator_version": artifact.get("generator_version",
                                              GENERATOR_VERSION),
        })
    # Deterministic: the same total order the generator uses.
    rows.sort(key=lambda r: (r["food_item_id"], r["normalized"],
                             r["alias_type"], r["rule"]))

    by_kind: dict[str, int] = {}
    for f in findings:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + 1

    return {
        "plan_version": PLAN_VERSION,
        "generator_version": artifact.get("generator_version"),
        "input_digest": artifact.get("input_digest"),
        "sources": artifact.get("sources", {}),
        "counts": {
            "total_candidates": counts.get("candidates_generated"),
            "accepted_review_candidates": counts.get("accepted"),
            "import_ready_before_exclusions":
                counts.get("import_ready_before_exclusions"),
            "excluded_pending_review": counts.get("excluded_pending_review"),
            "final_provisional_import": len(rows),
            "ambiguous": counts.get("ambiguous_candidates"),
            "duplicate_catalogue_rows":
                counts.get("duplicate_catalogue_collisions"),
            "bare_brand_exclusions": counts.get("bare_brand_exclusions"),
            "broad_aliases": counts.get("broad_aliases"),
            "missing_targets": counts.get("missing_targets"),
            "rejected": counts.get("rejected"),
        },
        "exclusions": {
            "excluded_pending_review": {
                "count": by_kind.get("excluded_pending_review", 0),
                "reason": "held back by explicit human decision; see below",
                "entries": dict(sorted(EXCLUDED_PENDING_REVIEW.items())),
            },
            "ambiguous": {
                "count": by_kind.get("ambiguous", 0),
                "reason": "alias maps to several DIFFERENT foods; choosing one "
                          "by rule would be a guess",
            },
            "duplicate_catalogue_row": {
                "count": by_kind.get("duplicate_catalogue_row", 0),
                "reason": "alias maps to several catalogue rows sharing one "
                          "name; a data-quality backlog item, deferred",
            },
            "bare_brand": {
                "count": by_kind.get("bare_brand", 0),
                "reason": "alias is the bare brand name across several "
                          "products; would match everything that brand sells",
            },
            "broad": {
                "count": by_kind.get("broad", 0),
                "reason": "category term, or shorter than the 4-character "
                          "minimum (mtr, g, nan, osh)",
            },
            "duplicate": {
                "count": by_kind.get("duplicate", 0)
                         + by_kind.get("case_or_punctuation_variant", 0),
                "reason": "same normalised alias already produced for this "
                          "food by a higher-confidence rule",
            },
            "empty": {
                "count": by_kind.get("empty", 0),
                "reason": "normalises to the empty string",
            },
            "missing_target": {
                "count": by_kind.get("missing_target", 0),
                "reason": "food_item_id not present in the catalogue",
            },
        },
        "aliases": rows,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--in", dest="src", default=str(DEFAULT_IN))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    args = p.parse_args(argv)

    artifact = json.loads(pathlib.Path(args.src).read_text(encoding="utf-8"))
    plan = build(artifact)

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(plan, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    c = plan["counts"]
    for k in ("total_candidates", "accepted_review_candidates",
              "import_ready_before_exclusions", "excluded_pending_review",
              "final_provisional_import", "ambiguous",
              "duplicate_catalogue_rows", "bare_brand_exclusions",
              "broad_aliases", "missing_targets"):
        print("  %-34s %s" % (k, c[k]))
    print()
    print("written: %s" % out.resolve())
    print("NO DATABASE WAS TOUCHED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
