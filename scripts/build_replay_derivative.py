"""Extract offline experiment code and derive opaque fixtures; never write a map.

This is an author-side derivation tool, not required by the public replay recipe.
Only --output-root is written. Source paths are supplied explicitly.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import uuid
from pathlib import Path


FILES = ("evidence_stream.json", "source_registry.json", "manifest.json",
         "refresh_on_query.json", "refresh_fixed_interval.json", "refresh_event_trigger.json",
         "policy_evidence_scoped.json", "policy_timestamp_ttl.json")
SAFE_FIELDS = {
    "schema_version", "actor_observer_relation", "assertion_kind", "authorization",
    "conflict_rule", "eligible_trigger_kinds", "event_time_basis", "evidence_kind",
    "interval_boundary", "modality", "mode", "occurrence_rule", "origin_class",
    "plan_rule", "polarity", "predicate", "sampler_version", "scene_class_id",
    "state_freshness_mode", "strategy", "tick_alignment", "trigger_kind",
    "explicit_validity_json_pointer", "authoring_procedure", "hidden_twin_rule",
}
TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T.*\+09:00$")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--code-only", action="store_true", help="refresh selected code without reidentifying fixtures")
    args = parser.parse_args()
    source, target = args.experiment_root, args.output_root
    package = target / "src" / "observer_study"
    fixture = target / "data" / "replay_opaque"
    if (fixture / "sealed_timeline_v1").exists() and not args.code_only:
        parser.error("refusing to overwrite an existing derivative")
    package.mkdir(parents=True, exist_ok=True)
    fixture.mkdir(parents=True, exist_ok=True)
    records = []
    extraction = {
        "validate_observer_v2.py": ("_replay_projection.py", ["TIMESTAMP_RE", "strict_time", "_state_slot", "project_query"]),
        "run_e2.py": ("_replay_payload.py", ["SYSTEM_PROMPT", "redact_claim", "model_context", "request_payload"]),
        "run_twin_gate_v3.py": ("_replay_gate.py", ["STRATEGIES", "POLICIES", "STRADDLE_MINUTES", "GATE_MODEL",
            "digest", "load", "state_slot", "hidden_event_windows", "leaky_project", "trace_snapshot_ids",
            "FamilyArtifacts", "by_evidence_id", "column_map", "run_positive_control", "authorization_probe", "main"]),
    }
    base_header = ('"""AST-selected experiment code; see extraction_provenance.json."""\n'
        'from __future__ import annotations\nimport copy\nimport hashlib\nimport inspect\nimport json\nimport re\n'
        'from datetime import datetime, timedelta\nfrom pathlib import Path\nfrom typing import Any\n\n')
    for filename, (output, names) in extraction.items():
        raw = (source / filename).read_bytes()
        text = raw.decode("utf-8")
        tree = ast.parse(text)
        pieces = []
        for node in tree.body:
            name = getattr(node, "name", None)
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
            if name not in names:
                continue
            original = ast.get_source_segment(text, node)
            selected = original.replace("\r\n", "\n")
            adaptation = "exact AST source segment; LF newline normalization only"
            if name == "request_payload":
                selected = selected.replace("model: str | None = None", "model: str")
                selected = selected.replace('str(model if model is not None else get_secret("LLM_MODEL", ""))', 'str(model)')
                selected = selected.replace('    user_prompt =', '    if not isinstance(model, str) or not model.strip():\n        raise ValueError("model must be an explicit nonempty string")\n    user_prompt =')
                adaptation = "required explicit model and nonempty check; remove secret fallback; payload fields unchanged"
            pieces.append(selected)
            records.append({"source_file": "experiments/e0_observation/" + filename,
                "source_file_sha256": sha(raw), "symbol": name, "source_line_start": node.lineno,
                "source_line_end": node.end_lineno, "source_segment_sha256": sha(original.encode("utf-8")),
                "extracted_segment_sha256": sha(selected.encode("utf-8")), "output_file": "src/observer_study/" + output,
                "extracted_segment_normalized_sha256": sha(selected.replace("\r\n", "\n").encode("utf-8")),
                "adaptation": adaptation})
        header = base_header
        if filename == "run_twin_gate_v3.py":
            header += ('from ._replay_payload import model_context, request_payload\n'
                'from ._replay_projection import project_query\n'
                'HERE = Path(__file__).resolve().parents[2]\n'
                'SEALED = HERE / "data" / "replay_opaque" / "sealed_timeline_v1"\n'
                'OUT = HERE / "replay_output"\n\n')
        (package / output).write_bytes((header + "\n\n".join(pieces) + "\n").encode("utf-8"))

    provenance = {"schema_version": "offline-extraction-v1", "symbols": records,
        "dependency_policy": "Python standard library only; no third-party implementation copied",
        "code_license": "repository LICENSE; author-owned experiment functions"}
    (fixture / "extraction_provenance.json").write_bytes(encoded(provenance))
    if args.code_only:
        return

    # Random opaque tokens are fixed in the generated package. No key or map is saved.
    mapping = {}
    def transform(value, key=""):
        if isinstance(value, dict):
            return {k: transform(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [transform(v, key) for v in value]
        if not isinstance(value, str):
            return value
        if key in SAFE_FIELDS or TIME.fullmatch(value) or key.endswith("sha256") or value == "*":
            return value
        if value not in mapping:
            mapping[value] = "opaque_" + uuid.uuid4().hex
        return mapping[value]

    import sys
    sys.path.insert(0, str(target / "src"))
    from observer_study._replay_projection import project_query
    from observer_study._replay_gate import column_map
    checked = 0
    families = []
    source_hashes = []
    for family in sorted((source / "sealed_timeline_v1").iterdir()):
        if not family.is_dir():
            continue
        original = {name: json.loads((family / name).read_text(encoding="utf-8")) for name in FILES}
        derived = {name: transform(value) for name, value in original.items()}
        slug = transform(family.name)
        dest = fixture / "sealed_timeline_v1" / slug
        dest.mkdir(parents=True)
        registry = derived["source_registry.json"]
        for row in registry["sources"]:
            row["payload_sha256"] = sha(json.dumps(row["payload"], ensure_ascii=False, sort_keys=True,
                separators=(",", ":")).encode("utf-8"))
        registry_sha = sha(encoded(registry))
        stream = derived["evidence_stream.json"]
        stream["source_registry_sha256"] = registry_sha
        stream_sha = sha(encoded(stream))
        for value in derived.values():
            if "source_registry_sha256" in value:
                value["source_registry_sha256"] = registry_sha
            if "stream_sha256" in value:
                value["stream_sha256"] = stream_sha
        for name, value in derived.items():
            (dest / name).write_bytes(encoded(value))
        # Identity-free membership checks inspect every arm, not just totals.
        for strategy in ("on_query", "fixed_interval", "event_trigger"):
            for policy in ("evidence_scoped", "timestamp_ttl"):
                trace_name, policy_name = f"refresh_{strategy}.json", f"policy_{policy}.json"
                for query in original[trace_name]["queries"]:
                    def project(doc, qid):
                        return project_query(doc["evidence_stream.json"], doc["source_registry.json"],
                            doc[trace_name], doc[policy_name], qid, stream_sha256="check", source_registry_sha256="check",
                            trace_sha256="check", policy_sha256="check")
                    before = column_map(project(original, query["query_id"]))
                    after = column_map(project(derived, transform(query["query_id"])))
                    assert {transform(k): v for k, v in before.items()} == after
                    checked += 1
        families.append(slug)
        source_hashes.append(sha(b"".join((family / name).read_bytes() for name in FILES)))
    (fixture / "derivation_receipt.json").write_bytes(encoded({"schema_version": "opaque-fixture-derivation-v1",
        "family_count": len(families), "files_per_family": len(FILES), "projection_membership_arms_checked": checked,
        "projection_membership_preserved": True, "identity_mapping_written": False,
        "transformation": "random UUID opaque tokens for all identifiers and free text; timestamps/enums retained; derived hashes recomputed",
        "source_family_bundle_sha256_unordered": sorted(source_hashes),
        "limitations": ["Derived bytes and identities differ from the private originals.",
            "This checks current/history membership, not language understanding or spatial truth.",
            "Only the eight visible replay inputs per family are included; hidden/oracle/package data are excluded."]}))
    print(json.dumps({"families": len(families), "membership_arms_checked": checked, "private_map_written": False}))


if __name__ == "__main__":
    main()
