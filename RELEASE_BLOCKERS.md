# Release blockers — de-identification must pass before the research artifacts are added

This repository is **public**. What it does not yet contain is the research
material: the manuscripts, the gate reports, the freezes and the corpus
measurement. Those stay out until every item below is closed, because adding
them is the irreversible step — a public push is cached, forked and indexed.

The first commit's message described this snapshot as "private", which was wrong
at the moment it was written: the repository was created public. That is recorded
here rather than rewritten, because a commit message that contradicts the state
it produced is exactly the defect class this study audits. The correction is this
paragraph, not a history rewrite.

This document deliberately does not reproduce any forbidden token. Enumerating
them here would make this file itself a leak, which is the same reason the
scanner's denylist lives outside the repository. Findings are reported as counts
and locations; the token list is in the scanner's `--denylist` file.

The gate-status register for this study carries an open item stating that the
admitted corpora still hold canon character identities and locators that resolve
to real coordinates through a non-released module, and that opaque-ID
transformation is required before any release. That work is **not done**.

Two scans were run on 2026-10-05 with
`src/observer_study/scan_release_deidentification.py`, over different candidate
sets. Keeping the scopes apart matters, because a count without its scope is not
reproducible — an earlier draft of this document cited "39 candidate files" with
no enumeration, and that number could not be regenerated from any command, so it
has been replaced by the two sets below, each of which can be.

| Scan | Candidate set | Result |
|---|---|---|
| release-candidate scan | the 14 artifacts this document names: both manuscripts, the v3 GateMem reports, the corpus instance file, the v4 twin reports, the v3 validity analysis, the v6 freeze and manifest, the v3 consistency audit, the gate-status register | 1 ADMIT, 13 EXCLUDE, exit 1 |
| repository scan | the tracked set of *this* repository (`git ls-files`) | 0 EXCLUDE, exit 0 |

The repository row states the invariant, not the file count: the count moves every
time a file is added, and a count written into prose is stale the next commit. The
claim that matters is that nothing tracked is excluded. Two files are allowlisted,
both only for the sentence in which they name the host project in order to
disclaim its content. A third exemption, for the scanner's own self-test fixtures,
was removed: the fixtures are now built from character codes and the scanner's
`--self-test` asserts that its own source file is admitted, so a scanner that no
longer needs to exempt itself is the stronger position.

The only admitted release candidate is `part1_baseline_freeze_revision_v6`. Every
other one is a blocker instance below. The repository scan gates on the tracked
set, not on the working tree, and reports untracked-on-disk hits separately (see
"Scanner scope defect").

## 1. Canon character identities (blocker)

The host project's character names are still used as package and family
identifiers, so they appear in the manuscripts themselves and not only in data.
Locations found by the release-candidate scan:

| Location | Leak |
|---|---|
| `paper_part1_en.tex`, `paper_part1_zh.tex` | one admitted-package id embeds a character name |
| `twin_gate_report_v4.json`, `twin_gate_detail_v4.json` | the same package id |
| `validity_v3/validity_gate_gap_analysis_v2.json` | the same package id |
| `peer_review_revision_v3/allocation_preimage.jcs.json` | the same package id |
| `peer_review_revision_v3/gatemem_target_alignment_report_v3.json` | the same package id |
| `corpus_matcher_v1/gatemem_corpus_matcher_report_v3.json` | the same package id |
| `GATE_STATUS_AND_KNOWN_BAD_REGISTER_2026-10-05.md` | the same package id |
| `part1_delivery_manifest_revision_v6_2026-10-05.json` | the same package id |
| `paper_claim_consistency_audit_v3_57fff7bd5c07.json` | the same package id |
| `peer_review_revision_v3/confirmatory_query_readiness_report_v3.json` | four distinct character names |

Five rows in this table — the two v3 GateMem reports, the gate-status register,
the v6 delivery manifest and the v3 consistency audit — were absent from the first
version of it. That version was written from a scan of the study worktree before
the v6 delivery set existed, and was never re-run afterwards, so the document
listed a strict subset of the locations while reading as if it listed all of
them. Every row above now comes from the release-candidate scan named in the
scope table, and re-running that scan is the check: if it reports an EXCLUDE that
is not in these tables, the tables are stale again.

A superseded unversioned duplicate of the readiness report was also sitting
inside this repository's working tree, git-ignored. It was moved out on
2026-10-05 to the study's staging directory and renamed to carry its version,
because its stated justification — kept on disk for audit continuity — was
false: the authoritative v1 remains in the study worktree, byte-identical
(sha256 `d59aff6a…2684`), so the copy here provided no continuity and added a
file with four canon identities one `git add -f` away from being published.

Required: an opaque-ID transformation whose mapping is **not** published, applied
to derived release copies. The frozen originals must not be rewritten —
publication artifacts are redacted derivatives, and the register records that the
originals differ.

## 2. Host project name and absolute user paths (blocker)

Artifacts that record their own generator path leak both the local user name and
the host project name. Note that the JSON-serialised form doubles the separator,
so a search for the literal single-backslash path misses four of these:

| Location | Leak |
|---|---|
| `gatemem_target_alignment_report_v3.json` → `generator.script`, `per_case_inputs` | absolute user path containing the host project directory |
| `gatemem_corpus_matcher_report_v3.json` → `generator.script`, `corpus_sha256` keys | same |
| `paper_claim_consistency_audit_v3_57fff7bd5c07.json` | same |
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

## What was already published, and cannot be unpublished (2026-10-05)

Two absolute local paths reached the public repository before the gate could stop
them. They are fixed at HEAD and **still present in git history** at commits
`c99840e` and `1f8e9ea`. A public push is cached, forked and indexed, so removing
a line from HEAD is a correction, not a retraction. What leaked:

| File | Leaked value | Sensitivity |
|---|---|---|
| `README.md` (line 21) | an absolute path to the host project's study directory, inside a reproduction command | names the host project and the author's directory layout |
| `RELEASE_MANIFEST.json` | `canonical_local_source`, an absolute path to this checkout | author machine layout only |

Neither is a secret, a credential, a canon identity or a real coordinate. Both are
still failures of the gate that exists to prevent them, and the second was found
only after the gate was fixed — so the honest statement is that the scan reported
clean while a tracked file leaked, twice.

Three reasons the scan missed them, all now fixed:

1. **The path pattern was narrower than the claim.** `USERPATH` matched a drive
   letter followed by a `Users` directory. A path to a project directory anywhere
   else on the drive did not match. Broadened to any drive-letter absolute path,
   with doubled separators, since JSON and Markdown both escape them.
2. **The allowlist exempted whole files.** `README.md` was allowlisted for naming
   the host project inside its disclaimer, keyed on basename. That exemption then
   covered a leak added later, in a command example nobody re-reviewed. Allowlist
   entries now name the reason *classes* they waive; an unwaived class still
   excludes, and a bare-string entry is reported as `whole_file_UNSCOPED` rather
   than silently honoured.
3. **The closing condition counted only `EXCLUDE`.** A file moved to
   `ALLOWLISTED` left the count, so an exemption was indistinguishable from a
   clean file in the exit code. The output now prints the scope of every
   exemption and what it waived.

## The release-manifest auditor passed a manifest that measured nothing

`audit_release_manifest.py` reported `PASS` over a manifest in which all seven
`sha256` fields held the literal string `generated-at-release`, one listed
directory did not exist, and `status` said `DRAFT_NOT_PUBLIC` while the repository
was published. Three of its checks tested a `redistribution` field that no entry
carried, so they could not fire. Its only status rule rejected `PUBLIC`, which
means it failed a manifest for telling the truth about itself and passed one that
lied — the inversion this study's own mechanism register calls out.

Rewritten to check existence, digests, status and self-consistency, with a
`--self-test` that constructs a violating manifest for each predicate, and a
`--write-digests` mode so digests are measured rather than transcribed. Directory
digests are sha256 over the sorted `relpath\0filesha256` lines beneath them; the
construction is published in the manifest, because a directory hash nobody can
recompute is not a hash. Against the manifest as it stood, the rewrite reports
nine errors.

## Scanner scope defect (found and fixed 2026-10-05)

The scanner walked the working tree and gated on it. That is the wrong
denominator for the question it answers. What gets published is the tracked set,
so a git-ignored file drove the verdict: the same invocation returned exit 1 over
`.` and exit 0 over `git ls-files`, and neither result said which set it had
measured. A gate whose verdict changes with an undocumented scope choice is the
defect class this study audits, in this study's own tooling.

Fixed by splitting the scope rather than by picking one. `--scope` takes
`tracked`, `worktree` or `both` (default). `both` gates on the tracked set and
prints untracked-on-disk hits as an advisory, because dropping them entirely
would hide a leak-shaped file sitting inside the repository directory one
`git add -f` away from being published. Exit codes are now distinct: 0 clean,
1 a tracked file would be published with a leak, 2 nothing tracked leaks but a
file inside the repository does, 3 the git index reports no tracked file among
the scanned paths.

Two guards keep the new scope from passing vacuously. If git is unavailable every
file is treated as gating and the report says so, so a git failure cannot produce
a clean verdict. If the tracked set is empty the scan refuses with exit 3, because
an empty gating set satisfies every predicate by construction and would otherwise
report a clean repository that contains nothing. The `--self-test` carries three
cases for the split itself — a tracked leak gates, an untracked one only advises,
and without git everything gates — so a `scope_of` that returned the same answer
for all three would fail the self-test instead of silently collapsing the
distinction.

The fix was measured while the duplicate readiness report was still in the
working tree, which is the state that makes the scopes disagree: `tracked` exit 0,
`both` exit 2 (one advisory), `worktree` exit 1. Three different verdicts from one
directory, none of them saying which set it had measured, is the defect. After the
duplicate was moved out all three scopes agree at exit 0 — so this paragraph
records a divergence that no longer reproduces, and the reason it no longer
reproduces is stated above rather than left to be inferred. Anyone wanting to see
the divergence again can put any untracked leak-shaped file in the repository
directory and re-run; that is a cheaper check than trusting this text.

`tests/test_scan_release_deidentification.py` keeps the divergence reproducible
without anybody having to plant a file by hand: it builds a throwaway repository
containing one tracked leak and one git-ignored leak, and asserts that
`--scope tracked` reports only the first, `--scope both` reports both and exits 2
once the tracked one is cleaned, an empty tracked set exits 3 rather than passing,
and a missing git index fails toward gating. Its denylist tokens are invented, so
the test file is itself scanned clean by the gate it tests; a first draft used a
real place name as a fixture and the gate correctly excluded it.

## What is committed

Only files the tracked-scope scan admits. The denylist file is git-ignored for
the reason given at the top of this document. Readiness reports are git-ignored
by pattern rather than by exact name, because the duplicate that was moved out was
protected by a rule that stopped matching the moment it was renamed.

## Closing condition

The repository is already public; the scan does not gate its visibility. What it
gates is **adding the research material** — the manuscripts, the gate reports, the
freezes, the corpus measurement. That is the irreversible step, so it is the step
that needs the gate.

Two conditions, both required:

1. `scan_release_deidentification.py --scope both .` over this repository returns
   exit 0. `--scope tracked` is not sufficient here: it skips untracked files, so
   it cannot report an advisory, and exit 0 under it is consistent with a
   leak-shaped file still sitting in the working tree.
2. The release-candidate scan over the 14 named artifacts returns exit 0. It
   returns exit 1 today. No research artifact enters the repository until it does,
   and each of the three blocker classes above must be closed by transforming a
   derivative, not by relaxing the scanner.

Both gates carry a `--self-test`, and both must pass before either verdict is
trusted; a gate that could not fail would otherwise report a clean repository by
construction. Neither self-test count is quoted here, for the reason given above:
a number in prose is stale the next time a check is added. Run them.

A third condition applies to `RELEASE_MANIFEST.json` specifically:
`audit_release_manifest.py --manifest RELEASE_MANIFEST.json --root .` must report
`PASS`. Its `--self-test` constructs a violating manifest for every predicate, so
a check that cannot fire is caught there rather than discovered by a reviewer.
