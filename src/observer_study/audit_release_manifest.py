"""Fail-closed audit for the public release manifest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

REQUIRED = {
    "path", "category", "source", "upstream_license_or_tos", "transformation",
    "real_world_content", "reversible_mapping", "sha256", "allowed_use", "exclusion_reason",
}
SENSITIVE = re.compile(r"(?:api[_ -]?key|bearer\s+[A-Za-z0-9._-]+|secret|oracle[_ -]?key|review[_ -]?key)", re.I)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    files = data.get("files", [])
    errors: list[str] = []
    if data.get("status") == "PUBLIC":
        errors.append("public status is forbidden for a release candidate")
    for index, item in enumerate(files):
        missing = sorted(REQUIRED - set(item))
        if missing:
            errors.append(f"file[{index}] missing fields: {','.join(missing)}")
        path = str(item.get("path", ""))
        if SENSITIVE.search(path) and item.get("redistribution") == "public":
            errors.append(f"sensitive path marked public: {path}")
        if item.get("real_world_content") and item.get("redistribution") == "public":
            errors.append(f"real-world content marked public: {path}")
        if item.get("reversible_mapping") and item.get("redistribution") == "public":
            errors.append(f"reversible mapping marked public: {path}")
    report = {"schema_version": "release-manifest-audit-v1", "status": "PASS" if not errors else "FAIL", "file_count": len(files), "errors": errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
