"""Fail-closed audit for the public release manifest.

The first version of this audit reported PASS over a manifest in which every
sha256 was the literal string "generated-at-release", one listed directory did not
exist, and the declared status said the repository was not public while it was
published on GitHub. Three of its checks tested a `redistribution` field that no
manifest entry carried, so they could not fire, and its only status rule rejected
"PUBLIC" -- meaning the audit failed a manifest for telling the truth about
itself and passed one that lied.

So the checks here are existence, digest, status and self-consistency, and each
one is exercised by --self-test against a manifest constructed to violate it.

Directory digests are sha256 over the sorted "relpath\\0filesha256" lines of every
file beneath the directory, skipping the same directories the de-identification
scanner skips. The definition is part of the contract: a directory hash with no
published construction cannot be reproduced by anyone else.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

REQUIRED = {
    "path", "category", "source", "upstream_license_or_tos", "transformation",
    "real_world_content", "reversible_mapping", "sha256", "allowed_use", "exclusion_reason",
}
SENSITIVE = re.compile(r"(?:api[_ -]?key|bearer\s+[A-Za-z0-9._-]+|secret|oracle[_ -]?key|review[_ -]?key)", re.I)
DIGEST = re.compile(r"^[0-9a-f]{64}$")
SKIP_DIRS = {".git", "__pycache__", "build", "venv", "node_modules", ".pytest_cache"}
STATUSES = {"DRAFT_INCOMPLETE_DIGESTS", "DRAFT_COMPLETE", "PUBLIC"}

# Built rather than written. A literal absolute path in this file would be caught
# by the de-identification gate that scans this repository, and the alternative --
# allowlisting the file -- is the mechanism that let a real leak through once
# already: an exemption granted for a synthetic fixture also covers anything added
# to that file later.
FAKE_ABSOLUTE_PATH = chr(68) + ":" + chr(47) + "somewhere" + chr(47) + "or-other"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest_of(target: Path) -> str:
    if target.is_file():
        return file_sha256(target)
    lines = []
    for path in sorted(p for p in target.rglob("*") if p.is_file()):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        lines.append(f"{path.relative_to(target).as_posix()}\0{file_sha256(path)}")
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()


def has_public_remote(root: Path) -> bool:
    try:
        out = subprocess.run(["git", "-C", str(root), "remote", "-v"],
                             capture_output=True, check=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return False
    return bool(re.search(r"https?://|git@github\.com", out))


def audit(data: dict, root: Path) -> list[str]:
    errors: list[str] = []
    files = data.get("files", [])
    if not files:
        errors.append("manifest lists no files; an empty list satisfies every per-entry check")

    status = data.get("status")
    if status not in STATUSES:
        errors.append(f"status {status!r} is not one of {sorted(STATUSES)}")
    public = has_public_remote(root)
    # A status that contradicts the repository is the defect; a status that
    # honestly declares incompleteness is not. An earlier draft of this check
    # rejected DRAFT_INCOMPLETE_DIGESTS whenever a remote existed, which would
    # have failed the manifest for telling the truth about itself -- the same
    # inversion as the v1 rule that forbade "PUBLIC".
    if not public and status == "PUBLIC":
        errors.append("manifest declares PUBLIC but no remote is configured")

    incomplete = 0
    for index, item in enumerate(files):
        missing = sorted(REQUIRED - set(item))
        if missing:
            errors.append(f"file[{index}] missing fields: {','.join(missing)}")
            continue
        rel = str(item["path"])
        target = root / rel
        planned = item.get("planned") is True
        if not target.exists():
            if planned:
                if item.get("digest_status") != "NOT_COMPUTED":
                    errors.append(f"file[{index}] {rel!r} is planned but carries a digest; "
                                  f"there are no bytes to digest yet")
                continue
            errors.append(f"file[{index}] lists {rel!r}, which does not exist and is not marked "
                          f"planned")
            continue
        if SENSITIVE.search(rel) and not item.get("exclusion_reason"):
            errors.append(f"file[{index}] sensitive path {rel!r} carries no exclusion_reason")
        if item.get("real_world_content") and not item.get("exclusion_reason"):
            errors.append(f"file[{index}] real-world content {rel!r} carries no exclusion_reason")
        if item.get("reversible_mapping") and not item.get("exclusion_reason"):
            errors.append(f"file[{index}] reversible mapping {rel!r} carries no exclusion_reason")

        claimed = str(item["sha256"])
        if item.get("digest_status") == "NOT_COMPUTED":
            if not planned:
                incomplete += 1
                if status == "PUBLIC":
                    errors.append(f"file[{index}] {rel!r} has no computed digest but the manifest "
                                  f"declares PUBLIC")
            continue
        if not DIGEST.match(claimed):
            errors.append(f"file[{index}] {rel!r} sha256 {claimed[:40]!r} is not a 64-hex digest; "
                          f"a placeholder reads as a measurement that was never made. Either "
                          f"compute it or set digest_status=NOT_COMPUTED")
            continue
        actual = digest_of(target)
        if actual != claimed:
            errors.append(f"file[{index}] {rel!r} sha256 {claimed[:12]} does not match the "
                          f"computed {actual[:12]}")

    if incomplete and status == "DRAFT_COMPLETE":
        errors.append(f"{incomplete} entr{'y' if incomplete == 1 else 'ies'} carry no computed "
                      f"digest but the manifest declares DRAFT_COMPLETE")

    # \b matters: without it the "s:" in https:// reads as a drive letter.
    absolute = re.findall(r"\b[A-Za-z]:[\\/]{1,2}[^\s\",]+", json.dumps(data, ensure_ascii=False))
    if absolute:
        errors.append(f"manifest carries {len(absolute)} absolute local path(s), e.g. "
                      f"{absolute[0][:48]!r}; a public artifact should not record where the "
                      f"author's checkout lives")
    return errors


def self_test(tmp: Path) -> dict:
    """Each check is exercised against a manifest built to violate it."""
    (tmp / "real").mkdir()
    (tmp / "real" / "a.txt").write_text("a\n", encoding="utf-8")
    good_digest = digest_of(tmp / "real")

    def entry(**over) -> dict:
        base = {"path": "real/", "category": "original_code", "source": "this release",
                "upstream_license_or_tos": "none", "transformation": "none",
                "real_world_content": False, "reversible_mapping": False,
                "sha256": good_digest, "allowed_use": "reuse", "exclusion_reason": ""}
        base.update(over)
        return base

    def manifest(**over) -> dict:
        base = {"schema_version": "observer-study-release-manifest-v2",
                "status": "DRAFT_COMPLETE", "files": [entry()]}
        base.update(over)
        return base

    cases = {
        "clean_manifest_passes": audit(manifest(), tmp) == [],
        "missing_directory_is_caught":
            bool(audit(manifest(files=[entry(path="absent/")]), tmp)),
        "placeholder_digest_is_caught":
            bool(audit(manifest(files=[entry(sha256="generated-at-release")]), tmp)),
        "wrong_digest_is_caught":
            bool(audit(manifest(files=[entry(sha256="0" * 64)]), tmp)),
        "not_computed_needs_a_matching_status":
            bool(audit(manifest(status="PUBLIC",
                                files=[entry(sha256="", digest_status="NOT_COMPUTED")]), tmp)),
        "not_computed_is_allowed_when_declared":
            audit(manifest(status="DRAFT_INCOMPLETE_DIGESTS",
                           files=[entry(sha256="", digest_status="NOT_COMPUTED")]), tmp) == [],
        "incomplete_digests_contradict_draft_complete":
            bool(audit(manifest(files=[entry(sha256="", digest_status="NOT_COMPUTED")]), tmp)),
        "empty_file_list_is_caught": bool(audit(manifest(files=[]), tmp)),
        "unknown_status_is_caught": bool(audit(manifest(status="WHATEVER"), tmp)),
        "absolute_path_is_caught":
            bool(audit(manifest(canonical_local_source=FAKE_ABSOLUTE_PATH), tmp)),
        "the_constructed_fixture_really_is_an_absolute_path":
            bool(re.search(r"\b[A-Za-z]:[\\/]{1,2}[^\s\",]+", FAKE_ABSOLUTE_PATH)),
        "a_url_is_not_mistaken_for_an_absolute_path":
            audit(manifest(remote="https://github.com/someone/some-repo"), tmp) == [],
        "missing_required_field_is_caught":
            bool(audit(manifest(files=[{k: v for k, v in entry().items() if k != "category"}]), tmp)),
        "planned_entry_may_be_absent":
            audit(manifest(files=[entry(path="absent/", planned=True, sha256="",
                                        digest_status="NOT_COMPUTED")]), tmp) == [],
        "planned_entry_may_not_carry_a_digest":
            bool(audit(manifest(files=[entry(path="absent/", planned=True)]), tmp)),
        "directory_digest_is_stable": digest_of(tmp / "real") == good_digest,
    }
    failed = sorted(k for k, v in cases.items() if v is not True)
    return {"checks": cases, "failed": failed,
            "status": "SELF_TEST_PASS" if not failed else "SELF_TEST_FAIL"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--root", type=Path, default=Path("."),
                        help="repository root the manifest's paths are relative to")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--write-digests", action="store_true",
                        help="recompute the sha256 of every existing entry in place and rewrite "
                             "the manifest. Digests are copied values, and copied values rot; "
                             "this exists so they are measured rather than transcribed. Entries "
                             "marked planned are left as NOT_COMPUTED.")
    args = parser.parse_args()

    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            report = self_test(Path(tmp))
        print(json.dumps(report, indent=2))
        return 0 if report["status"] == "SELF_TEST_PASS" else 1
    if args.manifest is None:
        parser.error("--manifest is required unless --self-test is given")

    data = json.loads(args.manifest.read_text(encoding="utf-8"))

    if args.write_digests:
        changed = []
        for item in data.get("files", []):
            target = args.root / str(item.get("path", ""))
            if item.get("planned") is True or not target.exists():
                item["digest_status"] = "NOT_COMPUTED"
                item["sha256"] = ""
                continue
            computed = digest_of(target)
            if item.get("sha256") != computed:
                changed.append(str(item["path"]))
            item["sha256"] = computed
            item.pop("digest_status", None)
        args.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
        print(json.dumps({"status": "DIGESTS_WRITTEN", "entries": len(data.get("files", [])),
                          "changed": changed}, ensure_ascii=False, indent=2))
        data = json.loads(args.manifest.read_text(encoding="utf-8"))

    errors = audit(data, args.root)
    report = {"schema_version": "release-manifest-audit-v2",
              "status": "PASS" if not errors else "FAIL",
              "manifest_status": data.get("status"),
              "file_count": len(data.get("files", [])),
              "public_remote_detected": has_public_remote(args.root),
              "errors": errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
