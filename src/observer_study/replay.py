"""Offline same-chain audit: four primary configurations and two controls.

The historical gate is kept intact in _replay_gate. Its signature heuristic is
reported as a heuristic, never upgraded into a correctness proof.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
from pathlib import Path
from typing import Any

from . import _replay_gate as gate
from ._replay_payload import model_context, redact_claim, request_payload
from ._replay_projection import project_query, strict_time


CONFIGURATIONS = (
    "original_projector_original_gate", "leaky_projector_original_gate",
    "underscored_leak_original_gate", "leaky_projector_discarding_gate",
    "original_projector_discarding_gate", "leaky_projector_restored_forwarding_gate",
)
DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "data" / "replay_opaque" / "sealed_timeline_v1"


def validate_fixture(root: Path) -> list[Path]:
    """Reject empty/unsupported inputs before entering the historical gate.

    This is replay-input validation, not the full private spatial validator.
    """
    families = sorted(root.glob("*/manifest.json"))
    if not families:
        raise ValueError("no fixture families found")
    seen_families = set()
    for manifest in families:
        art = gate.FamilyArtifacts(manifest.parent)
        if art.manifest.get("schema_version") != "observer-sealed-family-v2":
            raise ValueError("unsupported family schema")
        family_id = art.manifest["family_id"]
        if family_id in seen_families:
            raise ValueError("duplicate family ID")
        seen_families.add(family_id)
        if art.stream.get("schema_version") != "observer-evidence-stream-v2":
            raise ValueError("unsupported stream schema")
        if art.registry.get("schema_version") != "observer-source-registry-v2":
            raise ValueError("unsupported registry schema")
        rows = art.stream.get("evidence")
        if not isinstance(rows, list) or not rows:
            raise ValueError("empty evidence stream")
        evidence_ids = {row["evidence_id"] for row in rows}
        if len(evidence_ids) != len(rows):
            raise ValueError("duplicate evidence ID")
        registry_sha = gate.digest(art.registry_raw)
        stream_sha = gate.digest(art.stream_raw)
        if art.stream.get("source_registry_sha256") != registry_sha:
            raise ValueError("source registry digest mismatch")
        if art.manifest.get("stream_sha256") != stream_sha or art.manifest.get("source_registry_sha256") != registry_sha:
            raise ValueError("manifest input digest mismatch")
        source_ids = {row["source_ref"] for row in art.registry["sources"]}
        if len(source_ids) != len(art.registry["sources"]):
            raise ValueError("duplicate source reference")
        for row in rows:
            if row["claim"].get("assertion_kind") not in {"state", "plan", "occurrence", "reported_occurrence"}:
                raise ValueError("unsupported assertion kind")
            if row.get("evidence_kind") not in {"direct_observation", "communication", "self_action_receipt", "authorized_inference"}:
                raise ValueError("unsupported evidence kind")
            if row["support"].get("mode") not in {"point", "source_attested_until"}:
                raise ValueError("unsupported support mode")
            if row["source_ref"] not in source_ids:
                raise ValueError("unresolved source reference")
            strict_time(row["observed_at_jst"])
        for strategy, (trace, _) in art.traces.items():
            if trace.get("schema_version") != "observer-refresh-trace-v2" or trace.get("strategy") != strategy:
                raise ValueError("unsupported refresh trace")
            queries = trace.get("queries", [])
            if not queries or len({q["query_id"] for q in queries}) != len(queries):
                raise ValueError("missing or duplicate queries")
            if trace.get("stream_sha256") != stream_sha:
                raise ValueError("trace stream digest mismatch")
            for query in queries:
                strict_time(query["at_jst"])
                if not set(gate.trace_snapshot_ids(trace, query)) <= evidence_ids:
                    raise ValueError("unresolved snapshot evidence")
        for policy_name, (policy, _) in art.policies.items():
            if policy.get("schema_version") != "observer-projection-policy-v2" or policy.get("state_freshness_mode") != policy_name:
                raise ValueError("unsupported projection policy")
            if policy_name == "timestamp_ttl" and (not isinstance(policy.get("freshness_window_seconds"), int)
                    or policy["freshness_window_seconds"] <= 0):
                raise ValueError("TTL must be a positive integer")
    return families


def leaky_projector(stream, registry, trace, policy, query_id, *, hidden_world=None,
                    hidden_event_windows=None, **provenance):
    """One post-hoc fault: use hidden state boundaries for column assignment."""
    projection = project_query(stream, registry, trace, policy, query_id, **provenance)
    query = next(q for q in trace["queries"] if q["query_id"] == query_id)
    windows = hidden_event_windows
    if windows is None:
        windows = (hidden_world or {}).get("event_windows")
    if windows is None:
        windows = gate.hidden_event_windows(stream, query["at_jst"], ongoing=True)
    leak_map = gate.column_map(gate.leaky_project(stream, trace, query_id, windows))
    entries = projection["current"] + projection["history"]
    projection["current"] = sorted([row for row in entries if leak_map.get(row["evidence_id"]) == "current"],
                                   key=lambda row: row["evidence_id"])
    projection["history"] = sorted([row for row in entries if leak_map.get(row["evidence_id"]) != "current"],
                                   key=lambda row: row["evidence_id"])
    return projection


def underscored_leaky_projector(stream, registry, trace, policy, query_id, **_hidden_world):
    return leaky_projector(stream, registry, trace, policy, query_id, **_hidden_world)


def run_audit(fixture_root: Path, output_root: Path, *, configurations=CONFIGURATIONS) -> dict[str, Any]:
    if not configurations or any(name not in CONFIGURATIONS for name in configurations):
        raise ValueError("empty or unsupported audit configuration")
    validate_fixture(fixture_root)
    if output_root.exists():
        raise ValueError("refusing to overwrite existing output directory")
    original_projector, original_chain = gate.project_query, gate.FamilyArtifacts.visible_chain
    original_sealed, original_out = gate.SEALED, gate.OUT

    def discard_at_gate(self, strategy, policy_name, query_id, **hidden_plane):
        return original_chain(self, strategy, policy_name, query_id)

    def restored_forwarding(self, strategy, policy_name, query_id, **hidden_plane):
        # Reversal of the artificial adapter fault, not a fix to historical code.
        return original_chain(self, strategy, policy_name, query_id, **hidden_plane)

    implementations = {
        CONFIGURATIONS[0]: (project_query, original_chain),
        CONFIGURATIONS[1]: (leaky_projector, original_chain),
        CONFIGURATIONS[2]: (underscored_leaky_projector, original_chain),
        CONFIGURATIONS[3]: (leaky_projector, discard_at_gate),
        CONFIGURATIONS[4]: (project_query, discard_at_gate),
        CONFIGURATIONS[5]: (leaky_projector, restored_forwarding),
    }
    output_root.mkdir(parents=True)
    summaries = []
    try:
        gate.SEALED = fixture_root.resolve()
        for name in configurations:
            gate.project_query, gate.FamilyArtifacts.visible_chain = implementations[name]
            gate.OUT = output_root / name
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = gate.main()
            path = gate.OUT / "twin_gate_report_v4.json"
            report = json.loads(path.read_text(encoding="utf-8"))
            # A historical diagnostic used an absolute output path. Normalize
            # this metadata only; all failures and gate verdicts remain intact.
            report["artifact_writes"] = name + "/ only; replay input fixtures untouched"
            hidden = [f for f in report["failures"] if f["gate"] == "hidden_twin"]
            arms = {tuple(f["arm"]) + (f["family"],) for f in hidden}
            gate_fault = name in {CONFIGURATIONS[3], CONFIGURATIONS[4]}
            projector_fault = name in {CONFIGURATIONS[1], CONFIGURATIONS[2], CONFIGURATIONS[3], CONFIGURATIONS[5]}
            evidence_state = ("INVALID_INJECTED_GATE_FAULT" if gate_fault else
                              "FAULT_REJECTED" if hidden else "REFERENCE_ONLY_BASELINE")
            summaries.append({"configuration": name, "gate_status": report["status"], "exit_code": exit_code,
                "families": report["family_count"], "nested_arms": report["arms_tested"],
                "hidden_comparisons": report["hidden_twin_comparisons"], "hidden_failure_entries": len(hidden),
                "distinct_hidden_failure_arms": len(arms), "distinct_hidden_failure_families": len({f["family"] for f in hidden}),
                "visible_positive_controls": report["visible_positive_controls"],
                "signature_heuristic": report["detection_power"]["verdict"],
                "experiment_role": "primary" if name in CONFIGURATIONS[:4] else "appendix_control",
                "measurement_state": evidence_state,
                "underlying_equality_outcome": "UNEQUAL" if hidden else "EQUAL",
                "injected_fault": {"projector_hidden_currentness": projector_fault, "gate_discards_hidden_inputs": gate_fault},
                "intervention": ("reverse author-injected discarding fault; restore original forwarding"
                                 if name == CONFIGURATIONS[5] else "none"),
                "other_failures": [f["gate"] for f in report["failures"] if f["gate"] != "hidden_twin"]})
            report["replay_measurement"] = {key: summaries[-1][key] for key in
                ("experiment_role", "measurement_state", "underlying_equality_outcome", "injected_fault", "intervention")}
            path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    finally:
        gate.project_query, gate.FamilyArtifacts.visible_chain = original_projector, original_chain
        gate.SEALED, gate.OUT = original_sealed, original_out
    result = {"schema_version": "same-chain-replay-v2", "model_calls": 0, "fault_classes": 1,
        "gate_fault_classes": 1, "configurations": summaries,
        "interpretation": ["Faults are author-designed and post hoc, not a confirmatory sample.",
            "One leaking projector semantics is exercised through two signatures.",
            "Nested arms and three compared artifact planes are not independent mutants.",
            "A gate adapter discarding hidden inputs is an injected gate fault.",
            "A visible positive control alone does not establish hidden-fault detection."]}
    (output_root / "same_chain_summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run_audit(args.fixture_root, args.out)
    except (ValueError, KeyError, StopIteration, FileNotFoundError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2))
    # Exit 0 means the audit ran; injected failures are retained in its report.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
