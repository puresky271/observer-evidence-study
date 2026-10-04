r"""Pre-publication de-identification scan for the release repository.

A public push is irreversible: GitHub caches, forks and indexes. The gate-status
register for this study carries an open item stating that the admitted corpora
still hold canon character identities and locators that resolve to real
coordinates through a non-released module, and that opaque-ID transformation is
required before any release. This scan decides what may go into a public
repository.

The denylist lives in a separate file that is itself never published, for a
reason this scan demonstrates: any file that enumerates the forbidden tokens
trips the scan, so a scanner that carried its own denylist inline could not be
published either. Load it with --denylist.

Checks per candidate file:

1. Upstream benchmark content. GateMem's leak_targets and judge_spec are hidden
   scoring fields per its own docs/evaluation_protocol.md, and both manuscripts
   promise that upstream benchmark files, complete answers and hidden checkpoints
   are not redistributed.
2. Canon character identities and real-place locators from the host project.
3. Secrets, keys, tokens, credentials and absolute user paths.

Nothing is modified. The output is a per-file ADMIT / EXCLUDE decision with the
matched evidence, so the decision is reviewable rather than asserted.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

COORD = re.compile(r"3[5-7]\.\d{4,}\s*,\s*13[89]\.\d{4,}")
SECRET = re.compile(
    r"(?i)(sk-[A-Za-z0-9]{16,}|api[_-]?key\s*[:=]\s*\S{8,}|password\s*[:=]\s*\S{6,}"
    r"|gho_[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY)")
USERPATH = re.compile(r"(?i)[A-Z]:\\+Users\\+[A-Za-z0-9_.]+|/home/[a-z0-9_]+/")
UPSTREAM_FIELD = re.compile(r"\b(leak_targets|judge_spec|not_include)\b")
UPSTREAM_CKPT = re.compile(r"\b(education|household|medical|office)_episode_[a-z0-9_]+_ckpt_\d+\b")
SKIP_DIRS = {".git", "__pycache__", "build", "venv", "node_modules", ".pytest_cache"}


def load_denylist(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("canon_identities", "real_place_names"):
        if not data.get(key):
            raise SystemExit(f"denylist {path} has no {key}; refusing to scan with an empty denylist")
    return data


def classify(path: Path, deny: dict) -> dict:
    try:
        text = io.open(path, encoding="utf-8", errors="replace").read()
    except OSError as exc:
        return {"decision": "EXCLUDE", "reasons": [f"unreadable: {exc}"]}
    reasons: list[str] = []
    canon = sorted({c for c in deny["canon_identities"] if c in text})
    places = sorted({p for p in deny["real_place_names"] if p in text})
    if canon:
        reasons.append(f"canon_identity:{len(canon)}_distinct_tokens_see_denylist")
    if COORD.search(text):
        reasons.append(f"real_coordinate:{COORD.search(text).group(0)[:32]}")
    secret = SECRET.search(text)
    if secret:
        reasons.append(f"secret_pattern:{secret.group(0)[:20]}")
    userpath = USERPATH.search(text)
    if userpath:
        reasons.append(f"absolute_user_path:{userpath.group(0)[:40]}")
    checkpoint = UPSTREAM_CKPT.search(text)
    if checkpoint:
        reasons.append(f"upstream_checkpoint_id:{checkpoint.group(0)[:48]}")
    if places:
        reasons.append(f"real_place_name:{len(places)}_distinct_tokens_see_denylist")
    if UPSTREAM_FIELD.search(text) and path.suffix == ".jsonl":
        reasons.append("upstream_hidden_scoring_fields_in_a_data_file")
    return {"decision": "EXCLUDE" if reasons else "ADMIT", "reasons": reasons,
            "bytes": path.stat().st_size,
            "canon_token_count": len(canon), "place_token_count": len(places)}


def self_test(deny: dict, tmp: Path) -> dict:
    """The scan must be able to admit and to exclude, or ADMIT means nothing."""
    clean = tmp / "clean.md"
    dirty_canon = tmp / "dirty_canon.md"
    dirty_path = tmp / "dirty_path.md"
    dirty_ckpt = tmp / "dirty_ckpt.jsonl"
    clean.write_text("A study over three families with opaque identifiers.\n", encoding="utf-8")
    dirty_canon.write_text(f"family {deny['canon_identities'][0]} admitted\n", encoding="utf-8")
    dirty_path.write_text(r"script at C:\Users\someone\repo\x.py" + "\n", encoding="utf-8")
    dirty_ckpt.write_text('{"leak_targets": ["x"], "checkpoint_id": '
                          '"office_episode_custom_en_001_a_b_ckpt_03"}\n', encoding="utf-8")
    checks = {
        "admits_a_clean_file": classify(clean, deny)["decision"] == "ADMIT",
        "excludes_a_canon_identity": classify(dirty_canon, deny)["decision"] == "EXCLUDE",
        "excludes_an_absolute_user_path": classify(dirty_path, deny)["decision"] == "EXCLUDE",
        "excludes_upstream_hidden_fields": classify(dirty_ckpt, deny)["decision"] == "EXCLUDE",
        "denylist_is_not_empty": bool(deny["canon_identities"]) and bool(deny["real_place_names"]),
    }
    for path in (clean, dirty_canon, dirty_path, dirty_ckpt):
        path.unlink(missing_ok=True)
    failed = sorted(k for k, v in checks.items() if v is not True)
    return {"checks": checks, "failed": failed,
            "status": "SELF_TEST_PASS" if not failed else "SELF_TEST_FAIL"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", type=Path, nargs="*")
    parser.add_argument("--denylist", type=Path, required=True,
                        help="JSON with canon_identities and real_place_names; never published")
    parser.add_argument("--allowlist", type=Path,
                        help="JSON mapping a file name to the reason it is exempt from the "
                             "denylist. An exemption is printed, never silent: the two known "
                             "cases are a disclaimer sentence that names the host project in "
                             "order to disclaim it, and this scanner's own self-test fixtures.")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    deny = load_denylist(args.denylist)
    allow = json.loads(args.allowlist.read_text(encoding="utf-8")) if args.allowlist else {}
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            result = self_test(deny, Path(tmp))
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "SELF_TEST_PASS" else 1

    if not args.roots:
        parser.error("at least one root is required unless --self-test is given")

    table: dict[str, dict] = {}
    for root in args.roots:
        paths = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for path in paths:
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            result = classify(path, deny)
            if result["decision"] == "EXCLUDE" and path.name in allow:
                result["decision"] = "ALLOWLISTED"
                result["allowlist_reason"] = allow[path.name]
            table[str(path)] = result

    admit = sorted(k for k, v in table.items() if v["decision"] == "ADMIT")
    allowed = sorted(k for k, v in table.items() if v["decision"] == "ALLOWLISTED")
    exclude = sorted(k for k, v in table.items() if v["decision"] == "EXCLUDE")
    print(f"scanned={len(table)} ADMIT={len(admit)} ALLOWLISTED={len(allowed)} EXCLUDE={len(exclude)}")
    if allowed:
        print("\n--- ALLOWLISTED (exempt from the denylist, with a recorded reason) ---")
        for key in allowed:
            print(f"  {Path(key).name}")
            print(f"      reason: {table[key]['allowlist_reason']}")
            for reason in table[key]["reasons"]:
                print(f"      would otherwise exclude: {reason}")
    print("\n--- EXCLUDE ---")
    for key in exclude:
        print(f"  {Path(key).name}")
        for reason in table[key]["reasons"]:
            print(f"      {reason}")
    if args.json:
        args.json.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.json}")
    return 1 if exclude else 0


if __name__ == "__main__":
    sys.exit(main())
