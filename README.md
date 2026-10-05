# Observer Evidence Study — release candidate

This repository is **public**. It contains original research utilities, schemas,
opaque synthetic fixtures, derived summaries, figure-generation scaffolding and
HMAC-derived manuscript copies. It does not contain MyGO/BanG Dream expressive
content, production secrets, reversible location mappings, upstream benchmark
files, hidden checkpoints, or review keys.

The public manuscript derivatives are included below. Gate reports, freezes and
the per-instance corpus remain local because they contain host paths, hidden
evaluator fields or reversible identifiers; `RELEASE_BLOCKERS.md` records the
boundary and the resulting limit on full numerical re-execution.

The public manuscript copies are `manuscripts/paper_part1_en_public.tex` and
`manuscripts/paper_part1_zh_public.tex`. They are derived with the local
de-identification tool; the HMAC salt, denylist, mapping sidecar and untransformed
source manuscripts remain outside this repository. Gate reports, freezes and the
per-instance corpus remain held back; `RELEASE_BLOCKERS.md` records that boundary.

The confirmatory study is not ready for model calls. Query authoring, five model
entries, zero-evidence/opaque-entity controls, and the release manifest must pass
their gates first. The current 12-family evidence layer is a protocol-transfer
baseline, not a model-quality or population-level geographic-generalization
estimate.

## Checks

Every command runs from the repository root and takes its inputs as arguments.
Nothing here hardcodes a path on the author's machine, because a published
command that only works on one computer is not a reproduction recipe.

```powershell
py -X utf8 -m unittest discover -s tests -v
py -X utf8 src/observer_study/audit_release_manifest.py --manifest RELEASE_MANIFEST.json
py -X utf8 figures/scripts/build_baseline_figure_data.py --freeze <path-to-baseline-freeze.json>
py -X utf8 src/observer_study/author_queries.py --input-root <path-to-study-input-tree> --public-output data/synthetic_opaque/confirmatory_queries_v1.json
py -X utf8 src/observer_study/verify_synthetic_corpus.py --root data/synthetic_opaque/input
py -X utf8 figures/scripts/render_part1_v16_boundary_svg.py
```

`--freeze` and `--input-root` point at material that is not in this repository:
the baseline freeze is a research artifact still behind the gate, and the study
input tree is the author's working checkout. Both commands fail with a usage error
rather than guessing a default, which is deliberate — a default path baked into a
published script is how the first version of `build_baseline_figure_data.py`
leaked the author's directory layout.

The de-identification gate is not run by the test suite, because its denylist is
not published. Run it locally with the denylist you hold:

```powershell
py -X utf8 src/observer_study/scan_release_deidentification.py --denylist <denylist.json> --allowlist deidentification_allowlist.json --scope both .
```

Exit 0 means nothing tracked leaks and nothing untracked inside the repository
directory does either. See `RELEASE_BLOCKERS.md` for what the other exit codes
mean and why the scope has to be stated.

The public fixture under `data/synthetic_opaque/input/` is deliberately small and
contains only opaque IDs, declared validity, observer scope and four refresh
anchors. `verify_synthetic_corpus.py` checks that shape without reading any
evaluator-only labels. The evidence-plane SVG in `figures/exported/` is generated
from `figures/source_data/part1_v16_gate_summary.json`; it visualizes nested counts
and their independent-unit boundary, not model quality.

This is a public research artifact package, not a complete replay of the private
audit bundle. It supports inspection of the manuscript, source code, opaque
fixtures, aggregate delivery summary and figures. Exact gate counts remain
checkable only from the separately retained local evidence chain.

The de-identified manuscript derivatives are generated locally with the study's
`derive_deidentified_manuscripts.py` tool. The HMAC salt, denylist, sidecar mapping
and untransformed source files stay outside this repository. The public manuscript
files are therefore derivatives and do not provide a reversible identity mapping.

## Publication state

Created public on GitHub on 2026-10-05. Tagging and DOI registration remain
outstanding. An earlier revision of this file described the repository as a local
release candidate whose remote creation and push were still ahead; that was
already false when written, and `RELEASE_BLOCKERS.md` records the correction
rather than the history being rewritten.
