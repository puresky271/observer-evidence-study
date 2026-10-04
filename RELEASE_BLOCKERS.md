# Release blockers — de-identification must pass before this repository is public

This repository is **private** until every item below is closed. Making it public
is irreversible: GitHub caches, forks and indexes immediately.

This document deliberately does not reproduce any forbidden token. Enumerating
them here would make this file itself a leak, which is the same reason the
scanner's denylist lives outside the repository. Findings are reported as counts
and locations; the token list is in the scanner's `--denylist` file.

The gate-status register for this study carries an open item stating that the
admitted corpora still hold canon character identities and locators that resolve
to real coordinates through a non-released module, and that opaque-ID
transformation is required before any release. That work is **not done**. A
pre-publication scan (`src/observer_study/scan_release_deidentification.py`, run
2026-10-05 over 39 candidate files) found three classes of hard leak.

## 1. Canon character identities (blocker)

The host project's character names are still used as package and family
identifiers, so they appear in the manuscripts themselves and not only in data.
Locations found:

| Location | Leak |
|---|---|
| `paper_part1_en.tex`, `paper_part1_zh.tex` | one admitted-package id embeds a character name |
| `twin_gate_report_v4.json`, `twin_gate_detail_v4.json` | the same package id |
| `validity_v3/validity_gate_gap_analysis_v2.json` | the same package id |
| `peer_review_revision_v3/allocation_preimage.jcs.json` | the same package id |
| `peer_review_revision_v3/confirmatory_query_readiness_report_v3.json` | four distinct character names |
| `audits/confirmatory_query_readiness_report.json` (held back from this repo) | four distinct character names |

Required: an opaque-ID transformation whose mapping is **not** published, applied
to derived release copies. The frozen originals must not be rewritten —
publication artifacts are redacted derivatives, and the register records that the
originals differ.

## 2. Host project name and absolute user paths (blocker)

Artifacts that record their own generator path leak both the local user name and
the host project name:

| Location | Leak |
|---|---|
| `gatemem_target_alignment_report_v3.json` → `generator.script`, `per_case_inputs` | absolute user path containing the host project directory |
| `gatemem_corpus_matcher_report_v3.json` → `generator.script`, `corpus_sha256` keys | same |
| `GATE_STATUS_AND_KNOWN_BAD_REGISTER_2026-10-05.md` | same, plus one canon token |
| `figures/scripts/build_baseline_figure_data.py` | **fixed 2026-10-05** — the freeze path is now a `--freeze` argument |

Required: relative paths in every published artifact, and no host-project name in
any public file.

## 3. Upstream benchmark hidden scoring fields (blocker)

Both manuscripts state that upstream benchmark files, complete answers and hidden
checkpoints are not redistributed. Upstream `docs/evaluation_protocol.md` lists
`leak_targets` and `judge_spec` as hidden fields used only for scoring. These
files carry them per instance and must not be published:

| File | Content |
|---|---|
| `gatemem_corpus_matcher_instances_v1/v2/v3.jsonl` | per-instance upstream target values, judge-spec entries, upstream checkpoint ids, verbatim episode excerpts |
| `gatemem_corpus_matcher_report_v3.json` → `examples` | upstream checkpoint ids and target literals |

Required: publish the aggregate counts, the measuring script, the pinned upstream
commit and a regeneration recipe instead. Anyone can reproduce the instance rows
locally from the upstream commit; redistributing them is what the manuscripts
promise not to do. The `examples` block must be dropped or reduced to counts by
shape and field.

## Scanner false positives (reviewed, not blockers)

- A single common kanji in the host project's character names also occurs in
  ordinary words, so it was removed from the denylist; only full names are listed.
- This repository's `README.md` and `DATA_LICENSE` mention the host project only
  inside the sentence disclaiming that its expressive content is included.
- Real Tokyo place names are used in manuscript prose to describe the study's
  spatial substrate, which already states that the substrate is modelled on
  multiple Tokyo locations. Place names in prose are acceptable; a locator that
  resolves to real coordinates is not. The scan reports both and a human decides.

## What is committed while the repository is private

Only files the scan admits. `audits/confirmatory_query_readiness_report.json` is
git-ignored rather than deleted: it stays on disk for audit continuity and is
excluded from version control until an opaque-ID derivative replaces it. The
denylist file is git-ignored for the reason given at the top of this document.

## Closing condition

`scan_release_deidentification.py` over the full candidate set returns exit code
0 — zero `EXCLUDE` decisions. Only then may the repository be switched to public.
The scanner carries its own `--self-test`, which must pass before its verdict is
trusted; a scanner that could not exclude anything would otherwise report a clean
repository by construction.
