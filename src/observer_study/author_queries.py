"""Author query candidates from evidence and refresh artifacts without reading Oracle."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def load(path: Path) -> tuple[dict[str, Any], str]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), hashlib.sha256(raw).hexdigest()


def opaque(value: str) -> str:
    return "entity_" + digest(value)[:12]


def make_question(role: str, subject: str, predicate: str, target: str, at_jst: str, public: bool) -> str:
    subject_label = opaque(subject) if public else subject
    predicate_label = opaque(predicate) if public else predicate
    target_label = opaque(target) if public else target
    if role == "current_supported":
        return f"截至 {at_jst}，观察者能否根据当前证据确认 {subject_label} 的 {predicate_label} 状态？"
    if role == "history_expiry":
        return f"截至 {at_jst}，观察者能否确认 {subject_label} 过去是否有过 {predicate_label} 的观察记录？"
    if role == "unknown_scope":
        return f"截至 {at_jst}，观察者能否确认 {subject_label} 在 {target_label} 中具有未提供证据的 {predicate_label} 状态？"
    return f"截至 {at_jst}，观察者能否确认与 {subject_label} 相关的 {predicate_label} 是否属于当前观察者可直接确认的范围？"


def author_family(family_dir: Path, public: bool) -> dict[str, Any]:
    manifest, manifest_hash = load(family_dir / "manifest.json")
    stream, stream_hash = load(family_dir / "evidence_stream.json")
    trace, trace_hash = load(family_dir / "refresh_event_trigger.json")
    evidence = stream.get("evidence", [])
    first = evidence[0] if evidence else {"claim": {}, "scope": {}}
    claim = first.get("claim", {})
    subject = str(claim.get("subject_ref", "unobserved_subject"))
    predicate = str(claim.get("predicate", "unobserved_state"))
    target = str(first.get("scope", {}).get("target_space_ref", "unobserved_target"))
    times = [str(row.get("at_jst")) for row in trace.get("queries", [])][:4]
    while len(times) < 4:
        times.append(str(trace.get("run_end_jst", "unknown_time")))
    roles = ["current_supported", "history_expiry", "unknown_scope", "scope_recipient_or_plan"]
    queries = []
    for index, (role, at_jst) in enumerate(zip(roles, times), 1):
        queries.append({
            "query_id": f"{manifest['family_id']}:confirmatory:q{index:02d}",
            "role": role,
            "at_jst": at_jst,
            "question": make_question(role, subject, predicate, target, at_jst, public),
        })
    result = {
        "family_id": manifest["family_id"],
        "scene_class_id": manifest.get("scene_class_id"),
        "query_count": len(queries),
        "queries": queries,
        "authoring": {"oracle_read": False, "source_manifest_sha256": manifest_hash, "evidence_stream_sha256": stream_hash, "refresh_trace_sha256": trace_hash, "generator": "observer_study.author_queries.v1"},
    }
    if not public:
        result["private_semantics"] = {"subject": subject, "predicate": predicate, "target": target}
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-root", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path)
    args = parser.parse_args()
    family_dirs = sorted(path.parent for path in (args.input_root / "sealed_timeline_v1").glob("*/manifest.json"))
    public = {"schema_version": "confirmatory-query-authoring-v1", "status": "AUTHORING_CANDIDATE", "oracle_read": False, "families": [author_family(path, True) for path in family_dirs]}
    args.public_output.parent.mkdir(parents=True, exist_ok=True)
    args.public_output.write_text(json.dumps(public, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.private_output:
        private = {"schema_version": "confirmatory-query-authoring-private-v1", "status": "LOCAL_ONLY", "oracle_read": False, "families": [author_family(path, False) for path in family_dirs]}
        args.private_output.parent.mkdir(parents=True, exist_ok=True)
        args.private_output.write_text(json.dumps(private, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "family_count": len(family_dirs), "query_count": len(family_dirs) * 4, "oracle_read": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
