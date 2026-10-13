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

from ._replay_payload import model_context, request_payload
from ._replay_projection import project_query
HERE = Path(__file__).resolve().parents[2]
SEALED = HERE / "data" / "replay_opaque" / "sealed_timeline_v1"
OUT = HERE / "replay_output"

STRATEGIES = ("on_query", "fixed_interval", "event_trigger")

POLICIES = ("evidence_scoped", "timestamp_ttl")

STRADDLE_MINUTES = 8

GATE_MODEL = "twin-gate-model"

def digest(value: Any) -> str:
    if isinstance(value, bytes):
        return hashlib.sha256(value).hexdigest()
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def load(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), raw

def state_slot(row: dict[str, Any]) -> str:
    claim = row["claim"]
    return "|".join([
        str(claim["subject_ref"]),
        str(claim["predicate"]),
        str(row.get("scope", {}).get("target_space_ref")),
        str(claim["assertion_kind"]),
    ])

def hidden_event_windows(
    stream: dict[str, Any],
    as_of_jst: str,
    *,
    straddle_minutes: int = STRADDLE_MINUTES,
    ongoing: bool = True,
) -> dict[str, dict[str, str]]:
    """Reconstruct the world-event plane that the projector must never consult.

    Each twin pair holds observer evidence fixed and moves only the hidden end of the
    observed state across the query instant: `ongoing` puts the end after the query,
    the perturbation puts it before. That is the exact shape of the E1 failure, so a
    projector with the E1 data dependency must change its output between the pair.
    """
    as_of = datetime.fromisoformat(as_of_jst)
    end = as_of + timedelta(minutes=straddle_minutes if ongoing else -straddle_minutes)
    windows: dict[str, dict[str, str]] = {}
    for row in stream["evidence"]:
        if row["claim"]["assertion_kind"] != "state":
            continue
        windows[row["evidence_id"]] = {
            "slot": state_slot(row),
            "start_jst": row["observed_at_jst"],
            "end_jst": end.isoformat(),
        }
    return windows

def leaky_project(
    stream: dict[str, Any],
    trace: dict[str, Any],
    query_id: str,
    windows: dict[str, dict[str, str]],
) -> dict[str, Any]:
    """E1 `scoped_validity` semantics: currentness read off hidden event boundaries."""
    query = next(row for row in trace["queries"] if row["query_id"] == query_id)
    as_of = datetime.fromisoformat(query["at_jst"])
    rows = [row for row in stream["evidence"] if row["evidence_id"] in set(trace_snapshot_ids(trace, query))]
    latest: dict[str, str] = {}
    for row in rows:
        window = windows.get(row["evidence_id"])
        if not window or row["claim"]["assertion_kind"] != "state":
            continue
        if as_of >= datetime.fromisoformat(window["start_jst"]):
            slot = window["slot"]
            if slot not in latest or datetime.fromisoformat(row["observed_at_jst"]) > datetime.fromisoformat(latest[slot]):
                latest[slot] = row["observed_at_jst"]
    current, history = [], []
    for row in rows:
        window = windows.get(row["evidence_id"])
        is_current = bool(window) and (
            datetime.fromisoformat(window["start_jst"]) <= as_of < datetime.fromisoformat(window["end_jst"])
            and latest.get(window["slot"]) == row["observed_at_jst"]
        )
        entry = {"evidence_id": row["evidence_id"], "claim": dict(row["claim"])}
        (current if is_current else history).append(entry)
    return {
        "current": sorted(current, key=lambda entry: entry["evidence_id"]),
        "history": sorted(history, key=lambda entry: entry["evidence_id"]),
    }

def trace_snapshot_ids(trace: dict[str, Any], query: dict[str, Any]) -> list[str]:
    snapshot_id = query["snapshot_id"]
    if snapshot_id == trace["initial_snapshot_id"]:
        return list(trace["initial_snapshot_evidence_ids"])
    for sample in trace["sample_events"]:
        if sample["snapshot_id"] == snapshot_id:
            return list(sample["snapshot_evidence_ids"])
    raise ValueError(f"unknown snapshot {snapshot_id}")

class FamilyArtifacts:
    def __init__(self, family_dir: Path) -> None:
        self.family_slug = family_dir.name
        self.stream, self.stream_raw = load(family_dir / "evidence_stream.json")
        self.registry, self.registry_raw = load(family_dir / "source_registry.json")
        self.policies = {name: load(family_dir / f"policy_{name}.json") for name in POLICIES}
        self.traces = {strategy: load(family_dir / f"refresh_{strategy}.json") for strategy in STRATEGIES}
        self.manifest, _ = load(family_dir / "manifest.json")

    def visible_chain(self, strategy: str, policy_name: str, query_id: str, **hidden_plane: Any) -> dict[str, Any]:
        trace, trace_raw = self.traces[strategy]
        policy, policy_raw = self.policies[policy_name]
        projection = project_query(
            self.stream, self.registry, trace, policy, query_id,
            stream_sha256=digest(self.stream_raw),
            source_registry_sha256=digest(self.registry_raw),
            trace_sha256=digest(trace_raw),
            policy_sha256=digest(policy_raw),
            **hidden_plane,
        )
        query = next(row for row in trace["queries"] if row["query_id"] == query_id)
        context = model_context(projection, as_of_jst=query["at_jst"])
        wording = self.manifest["query_wording"]
        order = [row["query_id"] for row in trace["queries"]]
        payload = request_payload(
            wording[order.index(query_id)] if order.index(query_id) < len(wording) else f"sealed query for {self.family_slug}",
            context, max_tokens=256, model=GATE_MODEL,
        )
        return {"projection": projection, "context": context, "payload": payload}

def by_evidence_id(projection: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["evidence_id"]: row for column in ("current", "history") for row in projection[column]}

def column_map(projection: dict[str, Any]) -> dict[str, str]:
    return {row["evidence_id"]: column for column in ("current", "history") for row in projection[column]}

def run_positive_control(art: FamilyArtifacts, failures: list[dict[str, Any]],
                         *, mutate: Any = None) -> int:
    """Visible positive control: an authorized visible edit must move the payload.

    ``mutate`` is an optional callable applied to the copied state row instead of
    the default claim rewrite. The capability probe passes a no-op mutate so the
    SAME failure branches are exercised on a degenerate input; the probe writes
    into its own failures list and never into the gate's.
    """
    query_id = art.traces["on_query"][0]["queries"][0]["query_id"]
    target = next((index for index, row in enumerate(art.stream["evidence"])
                   if row["claim"]["assertion_kind"] == "state"), None)
    if target is None:
        return 0
    before = art.visible_chain("on_query", "evidence_scoped", query_id)
    mutated = copy.deepcopy(art.stream)
    changed_id = mutated["evidence"][target]["evidence_id"]
    if mutate is None:
        mutated["evidence"][target]["claim"]["object"] = "visible-signal-changed"
    else:
        mutate(mutated["evidence"][target])
    original = art.stream
    art.stream = mutated
    try:
        after = art.visible_chain("on_query", "evidence_scoped", query_id)
    finally:
        art.stream = original
    before_rows, after_rows = by_evidence_id(before["projection"]), by_evidence_id(after["projection"])
    diverged = {
        evidence_id for evidence_id in set(before_rows) | set(after_rows)
        if before_rows.get(evidence_id, {}).get("claim") != after_rows.get(evidence_id, {}).get("claim")
        or (evidence_id in before_rows) != (evidence_id in after_rows)
    }
    if digest(before["payload"]) == digest(after["payload"]):
        failures.append({"family": art.manifest["family_id"], "gate": "visible_positive_control",
                         "reason": "prompt payload unchanged by authorized visible evidence"})
        return 0
    if diverged != {changed_id}:
        failures.append({"family": art.manifest["family_id"], "gate": "visible_positive_control",
                         "reason": "divergence not attributable to the mutated evidence",
                         "diverged": sorted(diverged), "expected": changed_id})
        return 0
    return 1

def authorization_probe(art: FamilyArtifacts, *, redirect: bool = True) -> bool | None:
    """True when a claim re-addressed to another person still reaches context.

    Only recipient- and actor-scoped kinds are in scope here; direct observations are
    bounded by the package/topology scope validator instead, which the projector does not
    own. Returns None when the family has no such evidence or no baseline claim.

    ``redirect=False`` runs the identical survival computation on the unmodified
    (authorized) stream. That is the capability probe: if authorized guarded
    claims reach context, the predicate is not the constant False, so a True
    return under redirection remains observable and the failure branch is live.
    """
    strategy, policy_name = "on_query", "evidence_scoped"
    query_id = art.traces[strategy][0]["queries"][0]["query_id"]
    guarded_ids = {row["evidence_id"] for row in art.stream["evidence"]
                   if row["evidence_kind"] in {"communication", "self_action_receipt"}}
    if not guarded_ids:
        return None
    baseline = art.visible_chain(strategy, policy_name, query_id)
    if not (baseline["projection"]["current"] or baseline["projection"]["history"]):
        return None
    original_stream = art.stream
    art.stream = copy.deepcopy(original_stream)
    try:
        if redirect:
            for row in art.stream["evidence"]:
                if row["evidence_id"] not in guarded_ids:
                    continue
                row["participants"]["recipient_refs"] = ["person:unauthorised_other"]
                row["participants"]["actor_ref"] = "person:unauthorised_other"
        after = art.visible_chain(strategy, policy_name, query_id)
    finally:
        art.stream = original_stream
    surviving = {row["evidence_id"] for column in ("current", "history")
                 for row in after["projection"][column]}
    return bool(guarded_ids & surviving)

def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    families = sorted(SEALED.glob("*/manifest.json"))
    failures: list[dict[str, Any]] = []
    detail: list[dict[str, Any]] = []
    arms = twins = sensitive_arms = powered_families = controls = auth_tested = auth_leaks = 0
    auth_observations: list[dict[str, Any]] = []
    positive_control_probe: dict[str, Any] | None = None
    noop_guard_reachable_families = 0
    noop_degenerate_probe: dict[str, Any] | None = None

    for manifest_path in families:
        art = FamilyArtifacts(manifest_path.parent)
        family_adversarial = 0
        for strategy in STRATEGIES:
            trace, _ = art.traces[strategy]
            for policy_name in POLICIES:
                for query in trace["queries"]:
                    query_id = query["query_id"]
                    arms += 1
                    base = art.visible_chain(strategy, policy_name, query_id)
                    ongoing = hidden_event_windows(art.stream, query["at_jst"])
                    leaky_reference = column_map(leaky_project(art.stream, trace, query_id, ongoing))
                    arm_sensitive = False
                    windows = hidden_event_windows(art.stream, query["at_jst"], ongoing=False)
                    if windows:
                        twin = art.visible_chain(
                            strategy, policy_name, query_id,
                            hidden_world={"event_windows": windows},
                            hidden_event_windows=windows,
                        )
                        for plane in ("projection", "context", "payload"):
                            if digest(base[plane]) != digest(twin[plane]):
                                failures.append({"family": art.manifest["family_id"],
                                                 "arm": [strategy, policy_name, query_id],
                                                 "plane": plane, "gate": "hidden_twin"})
                        twins += 1
                        if column_map(leaky_project(art.stream, trace, query_id, windows)) != leaky_reference:
                            arm_sensitive = True
                    if arm_sensitive:
                        family_adversarial += 1

        reference_as_of = art.traces["on_query"][0]["queries"][0]["at_jst"]
        ongoing_windows = hidden_event_windows(art.stream, reference_as_of)
        ended_windows = hidden_event_windows(art.stream, reference_as_of, ongoing=False)
        ongoing_ends = {key: value["end_jst"] for key, value in ongoing_windows.items()}
        ended_ends = {key: value["end_jst"] for key, value in ended_windows.items()}
        guard_condition_holds = bool(ongoing_windows) and ongoing_ends == ended_ends
        if guard_condition_holds:
            failures.append({"family": art.manifest["family_id"], "gate": "perturbation_noop"})
            noop_guard_reachable_families += 1
        if noop_degenerate_probe is None and ongoing_windows:
            # Capability probe for the equality comparison itself: at
            # straddle_minutes=0 -- where the perturbation degenerates to a no-op --
            # the same map comparison on the same frozen stream must return equal.
            zero_ongoing = hidden_event_windows(art.stream, reference_as_of, straddle_minutes=0)
            zero_ended = hidden_event_windows(art.stream, reference_as_of,
                                              straddle_minutes=0, ongoing=False)
            noop_degenerate_probe = {
                "family": art.manifest["family_id"],
                "shipped_straddle_minutes": STRADDLE_MINUTES,
                "maps_equal_at_shipped_straddle": ongoing_ends == ended_ends,
                "maps_equal_at_zero_straddle": bool(zero_ongoing) and
                    {key: value["end_jst"] for key, value in zero_ongoing.items()}
                    == {key: value["end_jst"] for key, value in zero_ended.items()},
            }
        if family_adversarial:
            powered_families += 1
            sensitive_arms += family_adversarial
        controls += run_positive_control(art, failures)
        if positive_control_probe is None:
            probe_failures: list[dict[str, Any]] = []
            run_positive_control(art, probe_failures, mutate=lambda row: None)
            if probe_failures:
                positive_control_probe = {
                    "family": art.manifest["family_id"],
                    "method": "same run_positive_control() code path re-run with a no-op mutation, so "
                              "the payload cannot change; the 'prompt payload unchanged' failure branch "
                              "must fire on that degenerate input. Probe failures go to a separate list "
                              "and never enter the gate's failures.",
                    "probe_failures_recorded": len(probe_failures),
                    "first_probe_failure_reason": probe_failures[0].get("reason"),
                }
        auth_result = authorization_probe(art)
        if auth_result is not None:
            auth_tested += 1
            auth_observations.append({
                "family": art.manifest["family_id"],
                "redirected_claims_reach_context": auth_result,
                "authorized_baseline_claims_reach_context": authorization_probe(art, redirect=False),
            })
            if auth_result:
                auth_leaks += 1
                failures.append({"family": art.manifest["family_id"], "gate": "authorization_probe"})
        detail.append({"family_id": art.manifest["family_id"],
                       "hidden_state_windows": len(ongoing_windows),
                       "perturbation_sensitive_arms": family_adversarial,
                       "has_detection_power": bool(family_adversarial)})

    # Runtime vacuity probe: read the callee signature instead of trusting prose.
    # If project_query ever starts consuming the hidden plane, this flips and the
    # status below becomes a real PASS rather than a reference-only one.
    swallowed = [
        name for name, param in inspect.signature(project_query).parameters.items()
        if param.kind is inspect.Parameter.VAR_KEYWORD
    ]
    hidden_equality_can_fail = not any(name.startswith("_") for name in swallowed)

    if not powered_families:
        status = "INCONCLUSIVE"
    elif failures:
        status = "FAIL"
    elif not hidden_equality_can_fail:
        status = "PASS_REFERENCE_ONLY"
    else:
        status = "PASS"

    # Capability values below are COMPUTED from observed firings and the recorded
    # probes, never asserted. A probe that could not be made to fire yields
    # capable_of_failing=False plus contributes_no_detection_power=True.
    noop_fired = any(item.get("gate") == "perturbation_noop" for item in failures)
    noop_capable = noop_fired or noop_guard_reachable_families > 0
    noop_why = (
        "The guard condition held (or fired) on at least one family of the frozen corpus; see probe."
        if noop_capable else
        "At the shipped STRADDLE_MINUTES=8 the ended end_jst (as_of-8min) of every state row differs "
        "from its ongoing end_jst (as_of+8min), so the guard condition -- a non-empty ongoing window "
        "map whose end_jst map equals the ended one -- is unreachable for ANY input stream. It cannot "
        "be made to fire even by modifying the frozen corpus, let alone without modifying it; the only "
        "way to make the two maps equal is straddle_minutes=0, which degenerates the perturbation "
        "itself into a no-op (see probe.maps_equal_at_zero_straddle). capable_of_failing is therefore "
        "computed as False. The hardcoded True in the v3 report contradicted this record's own reason "
        "field ('has never fired and contributes no detection power')."
    )
    positive_control_capable = positive_control_probe is not None
    auth_capable = any(obs["authorized_baseline_claims_reach_context"] for obs in auth_observations)

    detection_power = {
        "description": "Every field in this block is computed at runtime: from the callee signature, "
                       "from observed firing counts on the frozen corpus, or from the recorded "
                       "capability probes. A check listed as incapable of failing contributes no "
                       "detection power, and the status must not be read as evidence of gate adequacy.",
        "hidden_equality_check": {
            "capable_of_failing": hidden_equality_can_fail,
            "reason": ("project_query consumes the hidden plane" if hidden_equality_can_fail else
                       "project_query swallows the hidden plane via " + ", ".join(swallowed) +
                       "; projection/context/payload equality is a theorem of the callee signature"),
        },
        "reference_differential_check": {
            "capable_of_failing": sensitive_arms > 0,
            "firing_observed": sensitive_arms > 0,
            "sensitive_arms": sensitive_arms,
            "reason": "computed from the observed firing count: the differential against leaky_project "
                      "actually changed its verdict on this many arms of the frozen corpus, so the check "
                      "is not a constant; a corpus with zero sensitive arms would compute False. Its "
                      "sensitivity is evidence about the reference projector, not about the evaluated "
                      "chain, which receives the perturbed plane only through **_hidden_world.",
        },
        "perturbation_noop_guard": {
            "capable_of_failing": noop_capable,
            "contributes_no_detection_power": not noop_capable,
            "fired": noop_fired,
            "guard_condition_reachable_on_frozen_corpus": noop_guard_reachable_families > 0,
            "families_where_guard_condition_holds": noop_guard_reachable_families,
            "probe": {
                "description": "the guard condition was evaluated per family at the shipped "
                               "STRADDLE_MINUTES, and the same end_jst map comparison was re-run at "
                               "straddle_minutes=0 on the same frozen stream to show the comparison "
                               "itself can return equal (so the False below is a measurement, not a "
                               "constant of the probe code)",
                "degenerate_straddle_probe": noop_degenerate_probe,
            },
            "why": noop_why,
        },
        "visible_positive_control": {
            "capable_of_failing": positive_control_capable,
            "firing_observed_in_probe": positive_control_capable,
            "probe": positive_control_probe,
            "controls_attributed": controls,
            "reason": "computed by re-running the same run_positive_control() code path with a no-op "
                      "mutation; the observed firing of its failure branch on that degenerate input is "
                      "the evidence for capability, not an assertion.",
        },
        "authorization_probe": {
            "capable_of_failing": auth_capable,
            "firing_observed_in_probe": auth_capable,
            "probe": {
                "method": "the same authorization_probe() survival computation run with redirect=False "
                          "(authorized baseline). If authorized guarded claims reach context, the "
                          "predicate is not the constant False, so a True return under redirection -- "
                          "and the appended authorization_probe failure -- remains observable.",
                "observations": auth_observations,
                "baseline_reachability_observed": auth_capable,
            },
            "guarded_families_tested": auth_tested,
            "leaks": auth_leaks,
        },
        "evaluated_chain_fault_injection": {
            "present": False,
            "reason": "no faulty implementation is substituted into the evaluated chain, so no assertion "
                      "here can reject the historical leak",
        },
        "verdict": "EVALUATED_CHAIN" if hidden_equality_can_fail else "REFERENCE_ONLY",
    }

    report = {
        "schema_version": "observer-twin-gate-report-v4",
        "supersedes": [
            "twin_v3/twin_gate_report_v3.json (schema v3): its detection_power block claimed the "
            "fields were 'Computed at runtime' but hardcoded capable_of_failing=True for "
            "reference_differential_check, perturbation_noop_guard, visible_positive_control and "
            "authorization_probe -- in the perturbation_noop_guard case contradicting that record's "
            "own reason field ('has never fired and contributes no detection power'). The frozen v3 "
            "bytes are preserved unmodified; this corrected rerun writes only to the TWIN_V3_OUT "
            "directory (twin_v4/).",
        ],
        "status": status,
        "status_semantics": {
            "PASS_REFERENCE_ONLY": "the reference differential is sensitive but the evaluated-chain "
                                   "equality assertion cannot fail; not evidence of gate adequacy",
            "PASS": "the evaluated chain consumes the perturbed plane and no failure was recorded",
            "INCONCLUSIVE": "no family gave the reference differential any sensitivity",
            "FAIL": "at least one recorded failure",
        },
        "interpretation_withdrawn": True,
        "detection_power": detection_power,
        "family_count": len(families),
        "arms_tested": arms,
        "hidden_twin_comparisons": twins,
        "families_with_detection_power": powered_families,
        "perturbation_sensitive_arms": sensitive_arms,
        "visible_positive_controls": controls,
        "authorization_probe": {
            "guarded_families_tested": auth_tested,
            "families_reaching_context_without_authorization": auth_leaks,
            "note": "covers recipient- and actor-scoped kinds only; direct observations are bounded by the package scope validator",
        },
        "perturbation_design": (
            f"hidden state end moved +/-{STRADDLE_MINUTES} minutes across the query instant; "
            "evidence stream, source registry, refresh trace and policy bytes unchanged"
        ),
        "prompt_chain": "run_e2.model_context + run_e2.request_payload",
        "model_calls": 0,
        "artifact_writes": f"{OUT.relative_to(HERE).as_posix() if OUT.is_relative_to(HERE) else OUT} "
                           "only (TWIN_V3_OUT override); frozen twin_v3/, the per-package "
                           "v1_5_admitted_*/twin_v3/ reports and the sealed corpus untouched",
        "limitations": [
            "Families with no state assertion carry no hidden event window and contribute no detection power.",
            "The adversarial projector is a purpose-built E1-semantics clone; it shows this harness can detect that leak class, not that no other class exists.",
            "project_query emits no unknown column, so the twin asserts equality over a context whose unknown field is always empty.",
            "Recipient and actor scoping is now refused by the projector as well as the validator; spatial scope for direct observations remains the package validator's responsibility and is not covered by this gate.",
        ],
        "failures": failures,
    }
    report_path = OUT / "twin_gate_report_v4.json"
    detail_path = OUT / "twin_gate_detail_v4.json"
    for path in (report_path, detail_path):
        if path.exists():
            raise SystemExit(f"refusing to overwrite existing artifact: {path}")
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    detail_path.write_text(
        json.dumps({"families": detail}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items()
                      if key not in ("failures", "limitations")}, ensure_ascii=False, indent=2, sort_keys=True))
    if failures:
        print(json.dumps(failures[:4], ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1
