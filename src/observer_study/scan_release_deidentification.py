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

Scope
-----
What gets published is the tracked set, not the working tree, so the two must be
reported separately. Scanning only the working tree lets a git-ignored file drive
the verdict and hides the fact that nothing publishable is wrong; scanning only
`git ls-files` stops reporting a leak-shaped file that is sitting inside the
repository directory one `git add -f` away from being published. `--scope both`
(the default) gates on the tracked set and reports untracked-on-disk hits as an
advisory with its own exit code.

Exit codes: 0 clean, 1 a tracked file would be published with a leak, 2 nothing
tracked leaks but a file inside the repository directory does.

Nothing is modified. The output is a per-file ADMIT / EXCLUDE decision with the
matched evidence, so the decision is reviewable rather than asserted.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
from pathlib import Path

COORD = re.compile(r"3[5-7]\.\d{4,}\s*,\s*13[89]\.\d{4,}")
SECRET = re.compile(
    r"(?i)(sk-[A-Za-z0-9]{16,}|api[_-]?key\s*[:=]\s*\S{8,}|password\s*[:=]\s*\S{6,}"
    r"|gho_[A-Za-z0-9]{20,}|BEGIN [A-Z ]*PRIVATE KEY)")
# Any absolute path, not only one under a home directory. The first version of
# this pattern matched only a drive letter followed by a Users directory, which
# is why a published README could carry an absolute path to the host project
# through a scan whose whole job was to stop that: the leak was real, the regex
# was narrower than the claim. Doubled separators are matched too, since JSON and
# Markdown both escape them.
USERPATH = re.compile(r"(?i)\b[A-Za-z]:[\\/]{1,2}[A-Za-z0-9_.\-]+|[\\/]{1,2}home[\\/]+[a-z0-9_]+[\\/]")
UPSTREAM_FIELD = re.compile(r"\b(leak_targets|judge_spec|not_include)\b")
UPSTREAM_CKPT = re.compile(r"\b(education|household|medical|office)_episode_[a-z0-9_]+_ckpt_\d+\b")
SKIP_DIRS = {".git", "__pycache__", "build", "venv", "node_modules", ".pytest_cache"}

# The self-test fixtures are constructed rather than written literally. A literal
# absolute path or upstream checkpoint id in this file is caught by this file's own
# scan, and the alternative -- allowlisting the scanner -- is the mechanism that
# let a real leak through once already: an exemption granted for a synthetic
# fixture also covers anything added to that file later, unreviewed. Constructing
# them keeps the allowlist down to the two disclaimer sentences that genuinely
# need it.
FIXTURE_PATH = ("script at " + chr(67) + ":" + chr(92) * 2 + "Users" + chr(92) * 2
                + "someone" + chr(92) * 2 + "repo" + chr(92) * 2 + "x.py\n")
FIXTURE_CKPT = ("office" + chr(95) + "episode" + chr(95) + "custom" + chr(95) + "en" + chr(95)
                + "001" + chr(95) + "a" + chr(95) + "b" + chr(95) + "ckpt" + chr(95) + "03")


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


def git_index(root: Path) -> tuple[Path | None, set[str] | None]:
    """Return (work-tree top level, tracked paths relative to it), or (None, None)."""
    try:
        top = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"],
                             capture_output=True, check=True, text=True).stdout.strip()
        listing = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--full-name"],
                                 capture_output=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None, None
    return Path(top), {p for p in listing.decode("utf-8", "replace").split("\0") if p}


def scope_of(path: Path, toplevel: Path | None, tracked: set[str] | None) -> str:
    """'gating' when the file would be published, 'advisory' when it only sits on disk.

    A file outside the work tree, or any file when git is unavailable, is gating:
    the caller asked about it explicitly, so the safe reading is that it is intended.
    """
    if toplevel is None or tracked is None:
        return "gating"
    try:
        rel = path.resolve().relative_to(toplevel.resolve()).as_posix()
    except ValueError:
        return "gating"
    return "gating" if rel in tracked else "advisory"


def reason_class(reason: str) -> str:
    return reason.split(":", 1)[0]


def apply_allowlist(result: dict, entry) -> dict:
    """Exempt only the reason classes the allowlist names, never the whole file.

    The first version exempted a file outright, keyed on its basename. That let a
    published README carry an absolute host-project path straight through: the
    file was allowlisted for naming the host project inside a disclaimer, and the
    exemption then covered a leak in a command example nobody had reviewed. An
    exemption scoped to a class is reviewable; an exemption scoped to a file is
    an exemption from the scan.
    """
    if isinstance(entry, str):
        entry = {"reason": entry, "exempt_classes": None}
    exempt = entry.get("exempt_classes")
    result["allowlist_reason"] = entry.get("reason", "")
    if exempt is None:
        result["decision"] = "ALLOWLISTED"
        result["allowlist_scope"] = "whole_file_UNSCOPED"
        result["still_excluded"] = []
        return result
    kept = [r for r in result["reasons"] if reason_class(r) not in set(exempt)]
    waived = [r for r in result["reasons"] if reason_class(r) in set(exempt)]
    result["allowlist_scope"] = f"classes:{','.join(sorted(exempt))}"
    result["waived"] = waived
    result["still_excluded"] = kept
    result["decision"] = "EXCLUDE" if kept else "ALLOWLISTED"
    return result


def load_allowlist(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("_comment", None)
    unscoped = sorted(k for k, v in data.items() if isinstance(v, str) or v.get("exempt_classes") is None)
    if unscoped:
        print(f"WARNING: {len(unscoped)} allowlist entr{'y' if len(unscoped) == 1 else 'ies'} exempt a "
              f"whole file rather than named reason classes: {', '.join(unscoped)}")
    return data


def self_test(deny: dict, tmp: Path) -> dict:
    """The scan must be able to admit and to exclude, or ADMIT means nothing."""
    clean = tmp / "clean.md"
    dirty_canon = tmp / "dirty_canon.md"
    dirty_path = tmp / "dirty_path.md"
    dirty_ckpt = tmp / "dirty_ckpt.jsonl"
    dirty_nonhome = tmp / "dirty_nonhome.md"
    clean.write_text("A study over three families with opaque identifiers.\n", encoding="utf-8")
    dirty_canon.write_text(f"family {deny['canon_identities'][0]} admitted\n", encoding="utf-8")
    dirty_path.write_text(FIXTURE_PATH, encoding="utf-8")
    dirty_ckpt.write_text('{"leak_targets": ["x"], "checkpoint_id": '
                          f'"{FIXTURE_CKPT}"' + '}\n', encoding="utf-8")
    # The regression that motivated broadening USERPATH: an absolute path to a
    # project directory that is not under any home directory.
    dirty_nonhome.write_text("run it with --input-root " + chr(68) + ":" + chr(92) * 2
                             + "python" + chr(92) * 2 + "some_project" + chr(92) * 2
                             + "experiments\n", encoding="utf-8")
    tracked = {"clean.md", "dirty_canon.md"}

    mixed = classify(dirty_nonhome, deny)
    mixed["reasons"] = ["canon_identity:1_x", "absolute_user_path:D:"]
    scoped_one = apply_allowlist(dict(mixed), {"reason": "r", "exempt_classes": ["canon_identity"]})
    scoped_both = apply_allowlist(dict(mixed), {"reason": "r",
                                                "exempt_classes": ["canon_identity", "absolute_user_path"]})
    unscoped = apply_allowlist(dict(mixed), "a bare string exempts everything")

    checks = {
        "admits_a_clean_file": classify(clean, deny)["decision"] == "ADMIT",
        "excludes_a_canon_identity": classify(dirty_canon, deny)["decision"] == "EXCLUDE",
        "excludes_an_absolute_user_path": classify(dirty_path, deny)["decision"] == "EXCLUDE",
        "excludes_upstream_hidden_fields": classify(dirty_ckpt, deny)["decision"] == "EXCLUDE",
        "denylist_is_not_empty": bool(deny["canon_identities"]) and bool(deny["real_place_names"]),
        # The regression: an absolute path outside any home directory. The old
        # pattern admitted this file, and a published README carried exactly it.
        "excludes_a_non_home_absolute_path": classify(dirty_nonhome, deny)["decision"] == "EXCLUDE",
        # The scope split must actually discriminate: a tracked leak gates, an
        # untracked one only advises, and without git everything gates.
        "tracked_file_is_gating": scope_of(tmp / "dirty_canon.md", tmp, tracked) == "gating",
        "untracked_file_is_advisory": scope_of(tmp / "dirty_ckpt.jsonl", tmp, tracked) == "advisory",
        "no_git_makes_everything_gating": scope_of(tmp / "dirty_ckpt.jsonl", None, None) == "gating",
        # An allowlist scoped to one class must not waive the others.
        "scoped_allowlist_still_excludes_unwaived_classes": scoped_one["decision"] == "EXCLUDE",
        "scoped_allowlist_waives_only_what_it_names": scoped_both["decision"] == "ALLOWLISTED",
        "unscoped_allowlist_is_labelled_as_such":
            unscoped["allowlist_scope"] == "whole_file_UNSCOPED",
        # The fixtures are constructed from character codes, so a typo would make
        # them stop matching and the exclusion checks above would pass for the
        # wrong reason. These assert the fixtures are what they claim to be.
        "fixture_path_really_matches_the_path_pattern": bool(USERPATH.search(FIXTURE_PATH)),
        "fixture_checkpoint_really_matches_the_checkpoint_pattern":
            bool(UPSTREAM_CKPT.search(FIXTURE_CKPT)),
        # This file needs no allowlist entry, which is the point of constructing
        # the fixtures: a scanner that had to exempt itself could not be used to
        # argue that an exemption is exceptional.
        "this_source_file_is_admitted_by_its_own_rules":
            classify(Path(__file__).resolve(), deny)["decision"] == "ADMIT",
    }
    for path in (clean, dirty_canon, dirty_path, dirty_ckpt, dirty_nonhome):
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
    parser.add_argument("--scope", choices=("both", "tracked", "worktree"), default="both",
                        help="both (default): gate on the tracked set, advise on untracked "
                             "files inside the work tree. tracked: only what would be "
                             "published. worktree: every file on disk, which lets an ignored "
                             "file drive the verdict.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    deny = load_denylist(args.denylist)
    allow = load_allowlist(args.allowlist) if args.allowlist else {}
    if args.self_test:
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            result = self_test(deny, Path(tmp))
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "SELF_TEST_PASS" else 1

    if not args.roots:
        parser.error("at least one root is required unless --self-test is given")

    table: dict[str, dict] = {}
    index_available = False
    for root in args.roots:
        toplevel, tracked = git_index(root) if args.scope != "worktree" else (None, None)
        index_available = index_available or tracked is not None
        paths = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for path in paths:
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            scope = scope_of(path, toplevel, tracked)
            if args.scope == "tracked" and scope != "gating":
                continue
            result = classify(path, deny)
            if result["decision"] == "EXCLUDE" and path.name in allow:
                apply_allowlist(result, allow[path.name])
            result["scope"] = scope
            result["tracked"] = scope == "gating" and tracked is not None
            table[str(path)] = result

    def pick(decision: str, scope: str | None = None) -> list[str]:
        return sorted(k for k, v in table.items() if v["decision"] == decision
                      and (scope is None or v["scope"] == scope))

    allowed = pick("ALLOWLISTED")
    gating_exclude = pick("EXCLUDE", "gating")
    advisory_exclude = pick("EXCLUDE", "advisory")
    print(f"scanned={len(table)} ADMIT={len(pick('ADMIT'))} ALLOWLISTED={len(allowed)} "
          f"EXCLUDE={len(gating_exclude) + len(advisory_exclude)} "
          f"(tracked={len(gating_exclude)} untracked_on_disk={len(advisory_exclude)})")
    if not index_available:
        print("git index UNAVAILABLE: every scanned file was treated as gating")
    elif table and all(not v["tracked"] for v in table.values()):
        # Nothing tracked means the gating set is empty, and an empty set satisfies
        # every predicate. Reporting that as a pass would be a vacuous verdict, so
        # it is reported as an error instead.
        print("REFUSED: the git index reports no tracked file among the scanned paths; "
              "an empty gating set passes by construction and proves nothing")
        return 3
    print(f"scope={args.scope}")
    if allowed:
        print("\n--- ALLOWLISTED (exempt from the denylist, with a recorded reason) ---")
        for key in allowed:
            entry = table[key]
            print(f"  {Path(key).name}")
            print(f"      reason: {entry['allowlist_reason']}")
            print(f"      scope: {entry.get('allowlist_scope', 'whole_file_UNSCOPED')}")
            for reason in entry.get("waived", entry["reasons"]):
                print(f"      waived: {reason}")
    if gating_exclude:
        print("\n--- EXCLUDE (tracked: this WOULD be published) ---")
        for key in gating_exclude:
            print(f"  {Path(key).name}")
            entry = table[key]
            if entry.get("allowlist_scope"):
                print(f"      allowlist covers {entry['allowlist_scope']} but not these:")
            for reason in entry.get("still_excluded") or entry["reasons"]:
                print(f"      {reason}")
    if advisory_exclude:
        print("\n--- ADVISORY (untracked on disk inside the repository: not published today,"
              " but one `git add -f` or one .gitignore edit away) ---")
        for key in advisory_exclude:
            print(f"  {Path(key).name}")
            for reason in table[key].get("still_excluded") or table[key]["reasons"]:
                print(f"      {reason}")
    if args.json:
        args.json.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.json}")
    if gating_exclude:
        return 1
    return 2 if advisory_exclude else 0


if __name__ == "__main__":
    sys.exit(main())
