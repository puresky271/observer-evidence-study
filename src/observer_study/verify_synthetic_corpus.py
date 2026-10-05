"""Fail-closed checks for the public opaque synthetic fixture."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True,
                        help="directory containing sealed_timeline_v1")
    args = parser.parse_args()
    families = sorted((args.root / "sealed_timeline_v1").glob("*/"))
    errors: list[str] = []
    if not families:
        errors.append("no fixture family found")
    for family in families:
        manifest = json.loads((family / "manifest.json").read_text(encoding="utf-8"))
        stream = json.loads((family / "evidence_stream.json").read_text(encoding="utf-8"))
        trace = json.loads((family / "refresh_event_trigger.json").read_text(encoding="utf-8"))
        if manifest.get("contains_private_semantics") is not False:
            errors.append(f"{family.name}: private semantics flag is not false")
        if not manifest.get("family_id", "").startswith("family_opaque_"):
            errors.append(f"{family.name}: family id is not opaque")
        if not stream.get("evidence"):
            errors.append(f"{family.name}: evidence stream is empty")
        if len(trace.get("queries", [])) != 4:
            errors.append(f"{family.name}: expected four query anchors")
        raw = "\n".join(path.read_text(encoding="utf-8") for path in family.glob("*.json"))
        if any(token in raw for token in ("C:\\", "D:\\", "\\.codex", "api_key", "secret")):
            errors.append(f"{family.name}: local path or secret-shaped token found")
    report = {"status": "PASS" if not errors else "FAIL", "family_count": len(families), "errors": errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
