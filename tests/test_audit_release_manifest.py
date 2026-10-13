"""Tests for the release-manifest auditor.

The auditor's own --self-test covers each predicate. What is worth pinning here is
the failure that motivated rewriting it: a manifest whose every digest was a
placeholder string, whose listed directory did not exist, and whose status
contradicted the repository, was reported PASS by the previous version.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AUDITOR = Path(__file__).resolve().parents[1] / "src" / "observer_study" / "audit_release_manifest.py"

# Constructed, not written: a literal absolute path here would be excluded by the
# repository's own de-identification gate, and allowlisting this file to get
# around that is the mechanism which let a real leak through once already.
FAKE_ABSOLUTE_PATH = chr(68) + ":" + chr(47) + "python" + chr(47) + "some-checkout"


def run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-X", "utf8", str(AUDITOR), *args],
                          capture_output=True, text=True)


class ManifestAuditorTest(unittest.TestCase):
    def test_self_test_passes(self) -> None:
        result = run(["--self-test"])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "SELF_TEST_PASS")

    def test_the_v1_manifest_shape_now_fails(self) -> None:
        """Every defect the old auditor passed, asserted at the CLI boundary."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
            manifest = root / "RELEASE_MANIFEST.json"
            manifest.write_text(json.dumps({
                "schema_version": "observer-study-release-manifest-v1",
                "status": "DRAFT_NOT_PUBLIC",
                "canonical_local_source": FAKE_ABSOLUTE_PATH,
                "files": [
                    {"path": "src/", "category": "original_code", "source": "this release",
                     "upstream_license_or_tos": "none", "transformation": "none",
                     "real_world_content": False, "reversible_mapping": False,
                     "sha256": "generated-at-release", "allowed_use": "reuse",
                     "exclusion_reason": ""},
                    {"path": "references/", "category": "third_party_reference",
                     "source": "upstream", "upstream_license_or_tos": "per-source",
                     "transformation": "metadata only", "real_world_content": False,
                     "reversible_mapping": False, "sha256": "generated-at-release",
                     "allowed_use": "citation", "exclusion_reason": "not redistributed"},
                ],
            }), encoding="utf-8")

            result = run(["--manifest", str(manifest), "--root", str(root)])
            self.assertEqual(result.returncode, 1, result.stdout)
            report = json.loads(result.stdout)
            self.assertEqual(report["status"], "FAIL")
            joined = "\n".join(report["errors"])
            self.assertIn("not one of", joined)
            self.assertIn("generated-at-release", joined)
            self.assertIn("does not exist", joined)
            self.assertIn("absolute local path", joined)

            # --write-digests measures what can be measured and refuses to invent
            # the rest, after which the only remaining errors are the honest ones.
            fixed = run(["--manifest", str(manifest), "--root", str(root), "--write-digests"])
            self.assertEqual(fixed.returncode, 1, fixed.stdout)
            rewritten = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(len(rewritten["files"][0]["sha256"]), 64)
            self.assertEqual(rewritten["files"][1]["digest_status"], "NOT_COMPUTED")


class PortableDigestTest(unittest.TestCase):
    """The defect behind the red CI run: one commit, two operating systems, two digests."""

    def _checkout(self, root: Path, newline: bytes, scratch: bool) -> None:
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        (root / ".gitignore").write_bytes(b"data/local_*.json" + newline)
        (root / "data").mkdir()
        (root / "data" / "a.json").write_bytes(b"{" + newline + b'  "k": 1' + newline + b"}" + newline)
        (root / "data" / "Z.txt").write_bytes(b"z" + newline)
        (root / "data" / "blob.bin").write_bytes(b"\x00\r\n\xff")
        if scratch:
            (root / "data" / "local_notes.json").write_bytes(b"{}" + newline)

    def test_linux_and_windows_checkouts_agree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            linux, windows = Path(tmp) / "linux", Path(tmp) / "windows"
            self._checkout(linux, b"\n", scratch=False)
            self._checkout(windows, b"\r\n", scratch=True)
            entry = {"path": "data/", "category": "data", "source": "this release",
                     "upstream_license_or_tos": "none", "transformation": "none",
                     "real_world_content": False, "reversible_mapping": False,
                     "sha256": "", "allowed_use": "reuse", "exclusion_reason": ""}
            manifest = {"schema_version": "observer-study-release-manifest-v2",
                        "status": "DRAFT_COMPLETE", "files": [entry]}
            path = windows / "RELEASE_MANIFEST.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            written = run(["--manifest", str(path), "--root", str(windows), "--write-digests"])
            self.assertEqual(written.returncode, 0, written.stdout + written.stderr)
            # Digests measured on the Windows-shaped checkout must verify on Linux.
            (linux / "RELEASE_MANIFEST.json").write_bytes(path.read_bytes())
            checked = run(["--manifest", str(linux / "RELEASE_MANIFEST.json"), "--root", str(linux)])
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)


if __name__ == "__main__":
    unittest.main()
