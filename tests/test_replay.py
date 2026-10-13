import ast
import hashlib
import json
import shutil
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from observer_study import replay
from observer_study import _replay_gate as gate


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "run"

    def test_fault_rejection_gate_fault_and_restored_forwarding_controls(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")):
            result = replay.run_audit(replay.DEFAULT_FIXTURE, self.output)
        configs = {row["configuration"]: row for row in result["configurations"]}
        honest = configs[replay.CONFIGURATIONS[0]]
        fault = configs[replay.CONFIGURATIONS[1]]
        underscored = configs[replay.CONFIGURATIONS[2]]
        discarded = configs[replay.CONFIGURATIONS[3]]
        healthy_discarded = configs[replay.CONFIGURATIONS[4]]
        restored = configs[replay.CONFIGURATIONS[5]]
        self.assertEqual(honest["gate_status"], "PASS_REFERENCE_ONLY")
        self.assertEqual(honest["hidden_failure_entries"], 0)
        self.assertEqual(fault["gate_status"], "FAIL")
        self.assertGreater(fault["distinct_hidden_failure_arms"], 0)
        self.assertEqual(fault["distinct_hidden_failure_arms"], underscored["distinct_hidden_failure_arms"])
        self.assertEqual(underscored["gate_status"], "FAIL")
        self.assertEqual(underscored["signature_heuristic"], "REFERENCE_ONLY")
        self.assertEqual(discarded["gate_status"], "PASS")
        self.assertEqual(discarded["visible_positive_controls"], fault["visible_positive_controls"])
        self.assertGreater(discarded["visible_positive_controls"], 0)
        self.assertEqual(discarded["measurement_state"], "INVALID_INJECTED_GATE_FAULT")
        self.assertEqual(healthy_discarded["underlying_equality_outcome"], "EQUAL")
        self.assertEqual(healthy_discarded["measurement_state"], "INVALID_INJECTED_GATE_FAULT")
        self.assertEqual(restored["distinct_hidden_failure_arms"], fault["distinct_hidden_failure_arms"])
        self.assertEqual(restored["measurement_state"], "FAULT_REJECTED")
        self.assertEqual(underscored["underlying_equality_outcome"], "UNEQUAL")
        report = json.loads((self.output / replay.CONFIGURATIONS[1] / "twin_gate_report_v4.json").read_text(encoding="utf-8"))
        groups = {}
        for failure in report["failures"]:
            if failure["gate"] == "hidden_twin":
                key = (failure["family"], *failure["arm"])
                groups.setdefault(key, set()).add(failure["plane"])
        self.assertTrue(groups)
        self.assertTrue(all(planes == {"projection", "context", "payload"} for planes in groups.values()))
        # These are the original measured aggregates, checked against an actual
        # fresh run. They are not constants baked into the runner.
        reference = json.loads((ROOT / "data/replay_opaque/reference_run_v2/same_chain_summary.json").read_text(encoding="utf-8"))
        self.assertEqual(result, reference)

    def test_selected_code_matches_recorded_source_segments(self):
        provenance = json.loads((ROOT / "data/replay_opaque/extraction_provenance.json").read_text(encoding="utf-8"))
        for record in provenance["symbols"]:
            source = (ROOT / record["output_file"]).read_text(encoding="utf-8")
            found = []
            for node in ast.parse(source).body:
                name = getattr(node, "name", None)
                if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                    name = node.targets[0].id
                if name == record["symbol"]:
                    segment = ast.get_source_segment(source, node)
                    found.append(hashlib.sha256(segment.encode("utf-8")).hexdigest())
            self.assertEqual(found, [record["extracted_segment_normalized_sha256"]])

    def test_empty_root_and_unsupported_configuration_fail_before_output(self):
        with self.assertRaisesRegex(ValueError, "no fixture families"):
            replay.run_audit(Path(self.temp.name), self.output)
        for configurations in [(), ("invented",)]:
            with self.assertRaisesRegex(ValueError, "unsupported audit configuration"):
                replay.run_audit(replay.DEFAULT_FIXTURE, self.output, configurations=configurations)
        self.assertFalse(self.output.exists())

    def fixture_copy(self):
        target = Path(self.temp.name) / "fixtures"
        family = sorted(replay.DEFAULT_FIXTURE.iterdir())[0]
        shutil.copytree(family, target / family.name)
        return target, target / family.name

    def test_unsupported_policy_is_rejected(self):
        root, family = self.fixture_copy()
        path = family / "policy_evidence_scoped.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["state_freshness_mode"] = "hidden_world"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported projection policy"):
            replay.run_audit(root, self.output)
        self.assertFalse(self.output.exists())

    def test_empty_stream_and_unsupported_schema_are_rejected(self):
        root, family = self.fixture_copy()
        path = family / "evidence_stream.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["evidence"] = []
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "empty evidence"):
            replay.validate_fixture(root)
        doc["schema_version"] = "future-schema"
        path.write_text(json.dumps(doc), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unsupported stream schema"):
            replay.validate_fixture(root)

    def test_overwrite_is_refused_and_patching_is_restored_on_failure(self):
        self.output.mkdir()
        with self.assertRaisesRegex(ValueError, "overwrite"):
            replay.run_audit(replay.DEFAULT_FIXTURE, self.output)
        original, chain = gate.project_query, gate.FamilyArtifacts.visible_chain
        with patch.object(gate, "main", side_effect=RuntimeError("injected runner error")):
            with self.assertRaisesRegex(RuntimeError, "runner error"):
                replay.run_audit(replay.DEFAULT_FIXTURE, Path(self.temp.name) / "error")
        self.assertIs(gate.project_query, original)
        self.assertIs(gate.FamilyArtifacts.visible_chain, chain)

    def test_explicit_model_is_required_and_hidden_labels_are_redacted(self):
        context = replay.model_context({"current": [{"claim": {"subject_ref": "opaque_entity", "predicate": "current_state",
            "object": "open", "oracle": "hidden"}, "global_truth": "hidden", "evidence_id": "opaque_evidence"}]},
            as_of_jst="2026-10-11T09:00:00+09:00")
        payload = replay.request_payload("opaque question", context, max_tokens=256, model="offline-placeholder")
        self.assertEqual(payload["model"], "offline-placeholder")
        self.assertNotIn("hidden", json.dumps(payload))
        self.assertNotIn("evidence_id", json.dumps(payload))
        with self.assertRaises(TypeError):
            replay.request_payload("q", context, max_tokens=256)
        with self.assertRaises(ValueError):
            replay.request_payload("q", context, max_tokens=256, model="")

    def test_time_requires_jst_and_future_snapshot_is_rejected(self):
        for bad in ["2026-10-11T09:00:00Z", "2026-10-11T09:00:00", "2026-10-11T09:00:00+08:00"]:
            with self.assertRaises(ValueError):
                replay.strict_time(bad)
        family = gate.FamilyArtifacts(sorted(replay.DEFAULT_FIXTURE.iterdir())[0])
        trace = family.traces["on_query"][0]
        query = trace["queries"][0]
        snapshot = next(row for row in trace["sample_events"] if row["snapshot_id"] == query["snapshot_id"])
        snapshot["sampled_at_jst"] = "2099-01-01T00:00:00+09:00"
        with self.assertRaisesRegex(ValueError, "future"):
            family.visible_chain("on_query", "evidence_scoped", query["query_id"])


if __name__ == "__main__":
    unittest.main()
