# Offline same-chain replay

The public package runs the evaluated projector → model-context redaction → request-payload chain and the original twin gate. Python 3.11+ and its standard library are sufficient. No install, network request, LLM call, API key, secrets file, private checkout, or third-party runtime is needed.

From a fresh clone, run:

```powershell
$env:PYTHONPATH = 'src'
py -X utf8 -m observer_study.replay --out replay_output/run_1
py -X utf8 -m unittest discover -s tests -v
```

On POSIX, use `PYTHONPATH=src python3 -m observer_study.replay --out replay_output/run_1`. Use a new output directory on every run. An existing directory is refused. `--fixture-root` optionally selects another compatible fixture tree; empty trees, unsupported schemas/policies/configurations, unresolved snapshot references, and digest mismatches fail closed.

The runner's exit 0 means that all requested audits completed. Each configuration retains the historical gate's own verdict and exit code in `same_chain_summary.json`; intentional fault rejection is an expected result of this audit. Full per-plane failure lists are in each configuration's `twin_gate_report_v4.json`, with family details alongside. The six-configuration committed reference is `data/replay_opaque/reference_run_v2/`; `reference_run/` retains the original four-configuration replay before the two additional controls.

| Configuration | Historical verdict | Families / nested arms / hidden comparisons | Failed planes / distinct failing arms / affected families | Visible positive controls |
| --- | --- | --- | --- | --- |
| Original projector, original gate | PASS_REFERENCE_ONLY | 12 / 288 / 216 | 0 / 0 / 0 | 9 |
| Leaky projector, original gate | FAIL | 12 / 288 / 216 | 648 / 216 / 9 | 9 |
| Same leak through underscored signature, original gate | FAIL | 12 / 288 / 216 | 648 / 216 / 9 | 9 |
| Leaky projector, gate discards hidden inputs | PASS | 12 / 288 / 216 | 0 / 0 / 0 | 9 |
| Appendix: original projector, gate discards hidden inputs | PASS_REFERENCE_ONLY | 12 / 288 / 216 | 0 / 0 / 0 | 9 |
| Appendix: leaky projector, original forwarding restored | FAIL | 12 / 288 / 216 | 648 / 216 / 9 | 9 |

`underlying_equality_outcome` records the observed hidden-twin equality result separately from the historical machine label. `measurement_state` marks both discarding-gate controls INVALID_INJECTED_GATE_FAULT, even with the original projector: an injected adapter fault is not evidence of a healthy measurement. The final appendix control explicitly reverses that artificial fault and restores the original forwarding method; it does not repair a discovered defect in the historical gate. Its rejection count matches the original forwarding configuration. The four primary configurations retain their original numerical results.

These are an author-designed, post-hoc fault experiment: **one projector fault class through two signatures, plus one gate adapter fault**. The 216 failing arms are nested observations across nine families, not 216 independent mutants. The 648 entries are three failed artifact planes per arm. The intentionally discarding gate's PASS is a false pass for this injected fault, while all nine visible positive controls still succeed. Signature naming misclassifies the underscored leak as REFERENCE_ONLY despite actual rejection; the heuristic is retained to make its failure inspectable. Neither PASS_REFERENCE_ONLY nor the injected gate's PASS establishes general noninterference, gate completeness, or model quality.

## What was extracted

`_replay_projection.py` contains AST-selected `strict_time`, `_state_slot`, and `project_query` with their timestamp constant. `_replay_payload.py` contains `redact_claim`, `model_context`, `request_payload`, and the original system prompt. `_replay_gate.py` contains the original helper functions, `FamilyArtifacts.visible_chain`, control/probe functions, and gate `main`. These are the evaluated functions, rather than a newly invented toy projector. The extraction receipt records original relative file names, exact source-file SHA-256, line spans, original source-segment SHA-256, and extracted segment SHA-256. Extracted code uses LF newlines; `.gitattributes` also preserves fixture LF bytes so Windows Git conversion cannot invalidate the recorded digests.

`request_payload` has one documented offline adaptation: `model` is required and must be a nonempty string; the secrets fallback is removed. The gate already supplies its explicit placeholder model, so payload semantics for the audited chain are preserved. Import headers use only the standard library and these selected modules. The adapter normalizes output-path metadata to relative paths after running the gate. Gate predicates, failure records, counters, and historical status logic are preserved.

The code is author-owned experiment code under the repository's MIT `LICENSE`. The replay chain itself uses no third-party implementation. The separate matcher audit vendors two licensed GateMem functions as described below. Data rights remain governed by `DATA_LICENSE`; the package contains no expressive franchise material, upstream map package, benchmark dataset, oracle, or hidden evaluation label.

## Fixture derivation and scope

`data/replay_opaque/sealed_timeline_v1/` contains all 12 original visible families as **opaque derivatives**, with eight files per family: evidence stream, source registry, three refresh traces, two policies, and manifest. A single in-memory map assigned random UUID tokens consistently to all identity-bearing identifiers and free text, including person/place/source/evidence/query/snapshot IDs and query wording. Tokens have no published key or sidecar mapping. Timestamps, protocol enums, freshness parameters, observer authorization relationships, claim structure, snapshot membership, and refresh schedules are retained. Payload/registry/stream digests are recomputed for derivative bytes; retained source/package fingerprints attest origins, not included package availability.

`derivation_receipt.json` records a 288-arm check that original and derivative current/history memberships are identical under the private in-memory renaming. The four primary configurations' historical summary fields match the retained original same-chain summary. Bytes, names, wording, and projection hashes are deliberately different; **this is numerical and structural replay of the same chain and visible fixtures, not byte-for-byte reproduction of the private corpus**. The derivation receipt is an author-side attestation: outsiders can replay the public data and inspect source hashes, but cannot independently prove the private-to-public renaming without the excluded originals.

The author-side `scripts/build_replay_derivative.py --experiment-root <original-experiment> --output-root <new-package>` documents the derivation procedure. It is unnecessary for public replay and never writes a private map. A new derivation uses new random tokens. It checks projection membership before reporting success; `--code-only` refreshes code extraction without replacing existing fixture identities.

This replay does not reproduce corpus authoring, package topology validation, upstream acquisition, oracle scoring, model responses, or population-level generalization. The three families with no state assertion contribute no hidden-window detection power. Input validation here checks the offline replay contract; it is not the complete private spatial scope validator.

## Matcher and full verification

`py -X utf8 scripts/reproduce.py --out replay_output/run_1` runs both experiments and compares the complete summary/report dictionaries to committed references. `data/matcher_audit/reference_report.json` holds six exact lexical input pairs and privacy target-alignment/aggregation controls. GateMem auxiliary scoring is not its primary LLM judge. The two unmodified vendored source files and upstream MIT license are pinned in `audits/gatemem_vendor_manifest.json`. No semantic-equivalence certification, upstream score-error claim or model answer quality claim follows from these probes.
