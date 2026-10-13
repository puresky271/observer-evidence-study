"""AST-selected experiment code; see extraction_provenance.json."""
from __future__ import annotations
import copy
import hashlib
import inspect
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+09:00$")

def strict_time(value: Any) -> datetime:
    if not isinstance(value, str) or not TIMESTAMP_RE.fullmatch(value):
        raise ValueError(f"timestamp must use explicit +09:00: {value!r}")
    parsed = datetime.fromisoformat(value)
    if parsed.utcoffset() != timedelta(hours=9):
        raise ValueError(f"timestamp offset must be +09:00: {value!r}")
    return parsed

def _state_slot(row: dict[str, Any]) -> tuple[str, str, str | None, str]:
    claim = row["claim"]
    return (
        str(claim["subject_ref"]), str(claim["predicate"]),
        row.get("scope", {}).get("target_space_ref"), str(claim["assertion_kind"]),
    )

def project_query(
    stream: dict[str, Any],
    registry: dict[str, Any],
    trace: dict[str, Any],
    policy: dict[str, Any],
    query_id: str,
    *,
    stream_sha256: str,
    source_registry_sha256: str,
    trace_sha256: str,
    policy_sha256: str,
    **_hidden_world: Any,
) -> dict[str, Any]:
    """Build the model-visible current/history projection for one query.

    Any hidden-world plane handed in by a twin harness is deliberately swallowed:
    currentness may only come from observer evidence, source-attested validity and
    the policy's own freshness rule.
    """
    query = next(row for row in trace["queries"] if row["query_id"] == query_id)
    snapshots = {
        trace["initial_snapshot_id"]: (
            strict_time(trace["initial_snapshot_at_jst"]),
            trace["initial_snapshot_evidence_ids"],
        )
    }
    for sample in trace["sample_events"]:
        snapshot_id = sample["snapshot_id"]
        if snapshot_id in snapshots:
            raise ValueError(f"duplicate snapshot ID: {snapshot_id}")
        snapshots[snapshot_id] = (strict_time(sample["sampled_at_jst"]), sample["snapshot_evidence_ids"])
    if query.get("snapshot_id") not in snapshots:
        raise ValueError(f"query references unknown snapshot: {query.get('snapshot_id')}")
    snapshot_time, snapshot = snapshots[query["snapshot_id"]]
    if snapshot_time > strict_time(query["at_jst"]):
        raise ValueError("query cannot read a snapshot from the future")
    snapshot_id = query["snapshot_id"]
    as_of = strict_time(query["at_jst"])
    observer = stream["observer_ref"]

    def admissible(row: dict[str, Any]) -> bool:
        # The contract validator already rejects mis-addressed artifacts; this guard keeps
        # the projector safe when a caller assembles a stream without validating it.
        kind = row.get("evidence_kind")
        participants = row.get("participants", {})
        if kind == "communication" and observer not in participants.get("recipient_refs", []):
            return False
        if kind == "self_action_receipt" and participants.get("actor_ref") != observer:
            return False
        return True

    rows = [
        row for row in stream["evidence"]
        if row["evidence_id"] in set(snapshot) and admissible(row)
    ]
    current_state_by_slot: dict[tuple[str, str, str | None, str], datetime] = {}
    for row in rows:
        if row["claim"]["assertion_kind"] == "state":
            observed = strict_time(row["observed_at_jst"])
            slot = _state_slot(row)
            if slot not in current_state_by_slot or observed > current_state_by_slot[slot]:
                current_state_by_slot[slot] = observed

    current: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = []
    mode = policy["state_freshness_mode"]
    ttl = policy.get("freshness_window_seconds")
    for row in rows:
        claim = row["claim"]
        kind = claim["assertion_kind"]
        observed = strict_time(row["observed_at_jst"])
        support = row["support"]
        if kind == "state":
            if support["mode"] == "source_attested_until":
                basis = "source_attested_interval"
                is_current = observed <= as_of < strict_time(support["valid_until_jst"])
            elif mode == "timestamp_ttl":
                basis = "freshness_policy"
                is_current = observed <= as_of < observed + timedelta(seconds=int(ttl))
            else:
                basis = "point_observation"
                is_current = as_of == observed
            is_current = is_current and observed == current_state_by_slot[_state_slot(row)]
        elif kind == "plan":
            basis = "plan_record"
            planned = row.get("event_time_jst")
            is_current = bool(planned) and as_of < strict_time(planned)
        else:
            basis = "historical_occurrence"
            is_current = False
        projected = {
            "evidence_id": row["evidence_id"],
            "claim": dict(claim),
            "evidence_kind": row["evidence_kind"],
            "modality": row["scope"]["modality"],
            "authorization": row["scope"]["authorization"],
            "scope": {
                "observer_position_ref": row["scope"]["observer_position_ref"],
                "target_space_ref": row["scope"]["target_space_ref"],
            },
            "participants": dict(row["participants"]),
            "event_time_basis": row["event_time_basis"],
            "observed_at_jst": row["observed_at_jst"],
            "event_time_jst": row["event_time_jst"],
            "support": dict(support),
            "currentness_basis": basis,
        }
        (current if is_current else history).append(projected)
    current.sort(key=lambda row: row["evidence_id"])
    history.sort(key=lambda row: row["evidence_id"])
    return {
        "schema_version": "observer-projection-v2",
        "observer_ref": stream["observer_ref"],
        "as_of_jst": query["at_jst"],
        "projection_policy_id": policy["policy_id"],
        "projection_policy_sha256": policy_sha256,
        "stream_sha256": stream_sha256,
        "source_registry_sha256": source_registry_sha256,
        "refresh_trace_sha256": trace_sha256,
        "snapshot_id": snapshot_id,
        "current": current,
        "history": history,
    }
