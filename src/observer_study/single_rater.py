"""Prepare primary and delayed re-rating sets for one blinded rater."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


FIELDS = [
    "review_id", "response_status", "A_awareness_0_2", "C_compliance_0_2",
    "K_target_accuracy_0_2_or_NA", "failure_tags_semicolon_separated",
    "claim_notes", "rater_id", "rating_pass", "adjudication_note",
]


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load_rows(path: Path) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8"))["records"]


def load_key(path: Path) -> dict[str, dict[str, Any]]:
    rows = json.loads(path.read_text(encoding="utf-8"))["records"]
    return {str(row["review_id"]): row for row in rows}


def write_template(path: Path, rows: list[dict[str, Any]], review_pass: str) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({
                "review_id": row["review_id"],
                "response_status": row["response_status"],
                "rater_id": "single_rater",
                "rating_pass": review_pass,
            })


def choose_delayed(rows: list[dict[str, Any]], key: dict[str, dict[str, Any]], fraction: float, salt: str) -> list[dict[str, Any]]:
    strata: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        meta = key.get(str(row["review_id"]), {})
        stratum = (str(meta.get("family_id", "")), str(meta.get("strategy", "")), str(row.get("response_status", "")))
        strata[stratum].append(row)
    selected: list[dict[str, Any]] = []
    for stratum, members in sorted(strata.items()):
        ranked = sorted(members, key=lambda item: digest(salt + "|" + stratum[0] + "|" + str(item["review_id"])))
        count = max(1, round(len(ranked) * fraction))
        selected.extend(ranked[:count])
    return sorted(selected, key=lambda item: str(item["review_id"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-set", type=Path, required=True)
    parser.add_argument("--review-key", type=Path, required=True)
    parser.add_argument("--primary-template", type=Path, required=True)
    parser.add_argument("--delayed-template", type=Path, required=True)
    parser.add_argument("--delayed-subset", type=Path, required=True)
    parser.add_argument("--fraction", type=float, default=0.25)
    parser.add_argument("--salt", default="single-rater-delayed-rerating-v1")
    args = parser.parse_args()
    rows = load_rows(args.review_set)
    key = load_key(args.review_key)
    delayed = choose_delayed(rows, key, args.fraction, args.salt)
    write_template(args.primary_template, rows, "primary")
    write_template(args.delayed_template, delayed, "delayed_rerating")
    args.delayed_subset.write_text(json.dumps({
        "schema_version": "single-rater-delayed-subset-v1",
        "source_review_set_sha256": digest(args.review_set.read_text(encoding="utf-8")),
        "fraction_requested": args.fraction,
        "salt": args.salt,
        "review_ids": [row["review_id"] for row in delayed],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "primary_rows": len(rows), "delayed_rows": len(delayed), "fraction": len(delayed) / len(rows) if rows else 0}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
