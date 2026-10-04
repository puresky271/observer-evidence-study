# Observer Evidence Study Release Candidate

This local release candidate contains only original research utilities, schemas,
opaque synthetic fixtures, derived summaries, and figure-generation scaffolding.
It does not contain MyGO/BanG Dream expressive content, production secrets,
reversible location mappings, upstream benchmark files, hidden checkpoints, or
review keys.

The confirmatory study is not ready for model calls. Query authoring, five model
entries, zero-evidence/opaque-entity controls, and the release manifest must pass
their gates first. The current 12-family evidence layer is a protocol-transfer
baseline, not a model-quality or population-level geographic-generalization
estimate.

## Local checks

```powershell
py -X utf8 -m unittest discover -s tests -v
py -X utf8 figures/scripts/build_baseline_figure_data.py
py -X utf8 src/observer_study/audit_release_manifest.py --manifest RELEASE_MANIFEST.json
py -X utf8 src/observer_study/author_queries.py --input-root D:\\python\\mygo_chat\\experiments\\e0_observation --public-output data\\synthetic_opaque\\confirmatory_queries_v1.json
```

The repository is a local release candidate. Remote GitHub creation, push, tag,
and DOI registration remain final publication steps after human review.

The canonical local source tree for those later steps is:
`D:\\python\\observer-evidence-study-release`.
