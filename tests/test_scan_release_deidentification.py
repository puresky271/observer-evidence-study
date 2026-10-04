"""Tests for the pre-publication de-identification gate.

The gate decides what may enter a public repository, so the property worth
testing is not that it flags known-bad text -- the bundled --self-test covers
that -- but that it cannot report a clean repository for a reason that has
nothing to do with the content: an empty tracked set, or a git failure, or a
scope choice nobody recorded.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCANNER = Path(__file__).resolve().parents[1] / "src" / "observer_study" / "scan_release_deidentification.py"

# Synthetic, and deliberately so. The real denylist is not published -- a file
# that enumerates the forbidden tokens is itself a leak -- so a published test
# cannot depend on it. These two tokens are invented for this file; neither is a
# character name or a real place name, which is what lets the test suite run in
# public and still be scanned clean by the gate it tests.
DENYLIST = {"canon_identities": ["Vantammer Family"], "real_place_names": ["Ferrowick"]}

LEAKY = "the Vantammer Family package is admitted\n"
CLEAN = "an opaque package identifier is admitted\n"


def run_scanner(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", str(SCANNER), *args],
                          capture_output=True, text=True)


class ScannerGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.denylist = self.tmp / "denylist.json"
        self.denylist.write_text(json.dumps(DENYLIST), encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def scan(self, *extra: str) -> subprocess.CompletedProcess:
        return run_scanner(["--denylist", str(self.denylist), *extra])

    def test_self_test_passes(self) -> None:
        result = self.scan("--self-test")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "SELF_TEST_PASS")

    def test_self_test_passes_against_the_real_denylist(self) -> None:
        """Local-only: the public suite cannot cover the real denylist.

        Point RELEASE_DENYLIST at the unpublished denylist to run this. Skipped
        otherwise, and the skip is the record that coverage of the real token set
        happens outside CI rather than a silent claim that it happens here.
        """
        real = os.environ.get("RELEASE_DENYLIST")
        if not real:
            self.skipTest("RELEASE_DENYLIST not set; the real denylist is not published")
        result = run_scanner(["--denylist", real, "--self-test"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "SELF_TEST_PASS")

    def test_scope_split_discriminates(self) -> None:
        """A tracked leak gates; the same bytes untracked only advise."""
        repo = self.tmp / "repo"
        (repo / "audits").mkdir(parents=True)
        (repo / "tracked_leak.md").write_text(LEAKY, encoding="utf-8")
        (repo / "audits" / "ignored_leak.md").write_text(LEAKY, encoding="utf-8")
        (repo / "clean.md").write_text(CLEAN, encoding="utf-8")
        (repo / ".gitignore").write_text("audits/ignored_leak.md\n", encoding="utf-8")
        for cmd in (["git", "init", "-q"], ["git", "add", "tracked_leak.md", "clean.md", ".gitignore"],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"]):
            subprocess.run(cmd, cwd=repo, check=True, capture_output=True)

        tracked = self.scan("--scope", "tracked", str(repo))
        self.assertEqual(tracked.returncode, 1, tracked.stdout)
        self.assertIn("tracked_leak.md", tracked.stdout)
        self.assertNotIn("ignored_leak.md", tracked.stdout)

        both = self.scan("--scope", "both", str(repo))
        self.assertEqual(both.returncode, 1, both.stdout)
        self.assertIn("ADVISORY", both.stdout)
        self.assertIn("ignored_leak.md", both.stdout)

        (repo / "tracked_leak.md").write_text(CLEAN, encoding="utf-8")
        subprocess.run(["git", "add", "tracked_leak.md"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "clean"],
                       cwd=repo, check=True, capture_output=True)
        # Nothing publishable leaks now, but a leak-shaped file is still inside
        # the repository directory. That is exit 2, not exit 0.
        downgraded = self.scan("--scope", "both", str(repo))
        self.assertEqual(downgraded.returncode, 2, downgraded.stdout)

    def test_empty_tracked_set_is_refused_not_passed(self) -> None:
        """An empty gating set satisfies every predicate; it must not read as clean."""
        repo = self.tmp / "empty"
        repo.mkdir()
        (repo / "untracked_leak.md").write_text(LEAKY, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, capture_output=True)
        result = self.scan("--scope", "both", str(repo))
        self.assertEqual(result.returncode, 3, result.stdout)
        self.assertIn("REFUSED", result.stdout)

    def test_missing_git_index_fails_toward_gating(self) -> None:
        """Without a git index every file gates, so a git failure cannot look clean."""
        plain = self.tmp / "plain"
        plain.mkdir()
        (plain / "leak.md").write_text(LEAKY, encoding="utf-8")
        result = self.scan("--scope", "both", str(plain))
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("UNAVAILABLE", result.stdout)

    def test_both_denylist_halves_are_exercised(self) -> None:
        """load_denylist refuses an empty half, so a half that is never matched
        would still let the scan run. Assert each half actually excludes."""
        for token in (DENYLIST["canon_identities"][0], DENYLIST["real_place_names"][0]):
            path = self.tmp / f"probe_{abs(hash(token))}.md"
            path.write_text(f"mentions {token} in prose\n", encoding="utf-8")
            result = self.scan("--scope", "worktree", str(path))
            self.assertEqual(result.returncode, 1, f"{token}: {result.stdout}")
            path.unlink()

    def test_empty_denylist_is_refused(self) -> None:
        empty = self.tmp / "empty_denylist.json"
        empty.write_text(json.dumps({"canon_identities": [], "real_place_names": []}), encoding="utf-8")
        result = run_scanner(["--denylist", str(empty), "--self-test"])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("empty denylist", result.stderr)


if __name__ == "__main__":
    unittest.main()
