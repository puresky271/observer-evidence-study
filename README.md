# Observer Evidence Study

A deterministic replay study of failure attribution in agent evaluations. The current manuscript asks whether a passing comparison reflects a healthy implementation, a discarded intervention, or an unsupported scoring interpretation.

## Current paper

- [English manuscript](manuscripts/failure_attribution_en.pdf) · [TeX](manuscripts/failure_attribution_en.tex)
- [中文对照](manuscripts/failure_attribution_zh.pdf) · [TeX](manuscripts/failure_attribution_zh.tex)
- [Verified bibliography](manuscripts/references_verified.bib)
- [Reproduction details](docs/reproduce.md)

Author/affiliation entries intentionally remain anonymous placeholders. Pre-submission simulated-review status is recorded separately in `reviews/` when available; it is not a journal acceptance or a guarantee of fit to a university journal classification.

The older `paper_part1_*_public.tex` files are **superseded v17 historical manuscripts**. Their nine-mechanism taxonomy, incapability inference and semantic-equivalence certification must not be cited as current findings. They remain intact for traceability.

## Reproduce in one command

Python 3.11+; no pip install, credentials, model call, private checkout or network needed.

```powershell
py -X utf8 scripts/reproduce.py --out replay_output/run_1
py -X utf8 -m unittest discover -s tests -v
```

POSIX: use `python3` instead of `py -X utf8`. Always choose a new output directory. The wrapper checks the executed six-configuration summary and matcher report against committed reference values, and verifies the two vendored scorer source digests. An expected nested `FAIL` means the injected implementation fault was detected; successful reproduction does not mean every nested gate passed.

The public tests deliberately skip the local-only real denylist test when `RELEASE_DENYLIST` is absent. This does not certify that private identifiers are absent. Release privacy checks and their scope are documented independently.

## What was measured

The primary replay uses 12 opaque derivatives of synthetic timeline families, 288 nested conditions, and 216 applicable state-bearing comparisons. One leakage semantics is tested, plus one author-injected input-discarding adapter. Three compared artifact layers are dependent outcomes.

| Configuration | Historical verdict | Unequal hidden arms | Visible positive controls |
| --- | --- | ---: | ---: |
| Safe projector / original forwarding | PASS_REFERENCE_ONLY | 0 | 9 |
| Leaking projector / original forwarding | FAIL | 216 | 9 |
| Same leak / renamed keyword dictionary | FAIL | 216 | 9 |
| Leaking projector / discarding adapter | PASS | 0 | 9 |
| Safe projector / discarding adapter | PASS_REFERENCE_ONLY | 0 | 9 |
| Leaking projector / restored forwarding | FAIL | 216 | 9 |

The signature heuristic changes its label after renaming despite identical leak rejection. Discarding the hidden input conceals the leak despite passing visible controls. Restoration reverses only the injected adapter fault. These are bounded counterexamples, not a representative mutation score or a noninterference proof.

Six lexical probes of a pinned auxiliary scorer change three paired decisions. None is certified semantically equivalent. Separate synthetic target-alignment and aggregation controls distinguish label errors from matcher behavior and checkpoint consequences. No published benchmark score, primary LLM judge or model quality is evaluated.

## Artifacts and limits

- `data/replay_opaque/` contains all 12 visible derivative families, extraction/derivation receipts and complete comparison reports.
- `data/matcher_audit/` contains exact authored inputs and auxiliary scorer outputs.
- `src/observer_study/_vendor/gatemem/` contains two unmodified MIT-licensed source files from GateMem, with its original license. Origin and hashes are in `audits/gatemem_vendor_manifest.json`.
- `audits/historical_aggregate_background.json` retains older delivery/readiness counts as background only; private raw answers and the unfinished confirmatory experiment are not publicly replayed.
- `RELEASE_MANIFEST.json` binds release scopes to measured file/directory digests. [Release boundaries](RELEASE_BLOCKERS.md) distinguish current publication from historical scans.

Opaque rewriting changes identifiers, questions and hashes; author-side receipts attest preserved memberships and primary failure records. Readers can reproduce the public derivative, but cannot independently verify private-to-public renaming without excluded originals. No identity map, production state, source franchise corpus, upstream benchmark episode or private spatial validator is distributed.

## Build the PDFs

With XeLaTeX, BibTeX and latexmk installed (TeX Live recommended):

```powershell
py -X utf8 scripts/build_manuscripts.py
```

The script copies the explicit bibliography into the build directory, compiles both languages, rejects unresolved references/missing glyphs, and writes PDFs beside the TeX sources. Compiler intermediates are ignored. The Chinese source uses `ctex`; English uses standard article/TikZ packages.

Original code is MIT licensed. Vendored code retains its upstream MIT license. Synthetic/derived data permissions and excluded source rights are documented in `DATA_LICENSE`. Cite the exact Git commit and current manuscript; author metadata must be completed by the author before actual submission.
