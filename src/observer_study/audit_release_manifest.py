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

The construction must also be platform-independent. Version 2 hashed working-tree
bytes, walked every file on disk and sorted platform path objects, so a Windows
checkout (CRLF line endings, git-ignored scratch inside listed directories) and a
Linux checkout of the same commit disagreed on 15 of 18 digests, and continuous
integration failed on the commit that published a manuscript claiming them.
Version 3 fixes three rules:

* Content: a file that decodes as UTF-8 and contains no NUL byte is text and is
  hashed with CRLF converted to LF; anything else is hashed as raw bytes. Digests
  are deliberately insensitive to line-ending conversion.
* Membership: inside a git work tree a directory contains exactly the files git
  would publish from it (tracked, plus untracked files that are not ignored), so
  ignored scratch cannot change a release digest. Outside git every file is walked.
* Order: lines sort by their POSIX relative path string, not by path objects whose
  ordering differs between operating systems.
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


DIGEST_CONSTRUCTION = ("release-digest-v3: UTF-8 text without NUL hashed with CRLF->LF, other "
                       "bytes raw; directory = git-publishable files sorted by POSIX relpath")
SKIPPED_NO_GIT = "SKIPPED_NO_GIT"


def canonical_bytes(raw: bytes) -> bytes:
    """Line-ending-independent content: UTF-8 without NUL is text, the rest is binary."""
    if b"\0" in raw:
        return raw
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw
    return raw.replace(b"\r\n", b"\n")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(canonical_bytes(path.read_bytes())).hexdigest()


def publishable_members(target: Path) -> list[Path] | None:
    """Files git would publish from `target`, or None when `target` is not in a work tree."""
    try:
        out = subprocess.run(
            ["git", "-C", str(target), "ls-files", "-z", "--cached", "--others",
             "--exclude-standard", "--", "."],
            capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    names = [name for name in out.decode("utf-8").split("\0") if name]
    # --cached also lists files deleted from disk but still in the index.
    return [target / name for name in names if (target / name).is_file()]


def digest_of(target: Path) -> str:
    if target.is_file():
        return file_sha256(target)
    members = publishable_members(target)
    if members is None:
        members = [p for p in target.rglob("*") if p.is_file()]
    lines = []
    for rel, path in sorted((p.relative_to(target).as_posix(), p) for p in members):
        if any(part in SKIP_DIRS for part in rel.split("/")):
            continue
        lines.append(f"{rel}\0{file_sha256(path)}")
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
    cases.update(_portability_checks(tmp))
    skipped = sorted(k for k, v in cases.items() if v == SKIPPED_NO_GIT)
    failed = sorted(k for k, v in cases.items() if v is not True and v != SKIPPED_NO_GIT)
    return {"checks": cases, "failed": failed, "skipped": skipped,
            "status": "SELF_TEST_PASS" if not failed else "SELF_TEST_FAIL"}


def _portability_checks(tmp: Path) -> dict:
    """The defects that made Windows and Linux disagree, each reconstructed."""
    pairs = {"text": (b"x\ny\n", b"x\r\ny\r\n"),
             "nul": (b"x\n\0", b"x\r\n\0"),
             "latin1": (b"\xe2\xe3\n", b"\xe2\xe3\r\n")}
    digests = {}
    for name, (lf, crlf) in pairs.items():
        (tmp / f"{name}_lf.dat").write_bytes(lf)
        (tmp / f"{name}_crlf.dat").write_bytes(crlf)
        digests[name] = (file_sha256(tmp / f"{name}_lf.dat"), file_sha256(tmp / f"{name}_crlf.dat"))
    # Upper-case names sort before lower-case ones as strings; Windows path objects
    # compare case-insensitively, which is how directory digests drifted by platform.
    (tmp / "order").mkdir()
    for name in ("b.txt", "C.txt", "a.txt"):
        (tmp / "order" / name).write_text(name, encoding="utf-8")
    expected = hashlib.sha256("\n".join(
        f"{n}\0{hashlib.sha256(n.encode()).hexdigest()}" for n in ("C.txt", "a.txt", "b.txt")
    ).encode("utf-8")).hexdigest()
    return {
        "crlf_and_lf_text_hash_identically": digests["text"][0] == digests["text"][1],
        "nul_bytes_keep_raw_hashing": digests["nul"][0] != digests["nul"][1],
        "non_utf8_keeps_raw_hashing": digests["latin1"][0] != digests["latin1"][1],
        "directory_order_is_posix_string_order": digest_of(tmp / "order") == expected,
        "ignored_file_does_not_change_directory_digest": _membership_check(tmp),
    }


def _membership_check(tmp: Path):
    """Inside a work tree, ignored files stay out of a directory digest; new ones do not."""
    repo = tmp / "membership_repo"
    (repo / "pkg").mkdir(parents=True)
    try:
        subprocess.run(["git", "init", "-q", str(repo)], capture_output=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return SKIPPED_NO_GIT
    (repo / ".gitignore").write_text("pkg/scratch.json\n", encoding="utf-8")
    (repo / "pkg" / "kept.json").write_text("{}\n", encoding="utf-8")
    before = digest_of(repo / "pkg")
    (repo / "pkg" / "scratch.json").write_text('{"local": true}\n', encoding="utf-8")
    ignored_excluded = digest_of(repo / "pkg") == before
    (repo / "pkg" / "added.json").write_text("{}\n", encoding="utf-8")
    unignored_included = digest_of(repo / "pkg") != before
    return ignored_excluded and unignored_included


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
    report = {"schema_version": "release-manifest-audit-v3",
              "digest_construction": DIGEST_CONSTRUCTION,
              "status": "PASS" if not errors else "FAIL",
              "manifest_status": data.get("status"),
              "file_count": len(data.get("files", [])),
              "public_remote_detected": has_public_remote(args.root),
              "errors": errors}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
