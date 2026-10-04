"""Build IP-free figure source data from the frozen Part I baseline."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", type=Path, required=True,
                        help="path to the frozen Part I baseline JSON; the path is an argument "
                             "rather than a literal so this file carries no local user directory")
    args = parser.parse_args()
    here = Path(__file__).resolve().parents[2]
    baseline = args.freeze
    data = json.loads(baseline.read_text(encoding="utf-8"))
    out = here / "figures" / "source_data"
    out.mkdir(parents=True, exist_ok=True)
    rows = [
        {"layer": "v15_external_validity", "families": data["v15_external_validity"]["family_count"], "conditions": data["v15_external_validity"]["projection_conditions"], "model_calls": data["v15_external_validity"]["model_calls"]},
        {"layer": "observer_development", "families": data["observer_protocol"]["development_families"], "conditions": data["observer_protocol"]["development_conditions"], "model_calls": data["observer_protocol"]["model_calls"]},
        {"layer": "observer_sealed", "families": data["observer_protocol"]["sealed_families"], "conditions": data["observer_protocol"]["sealed_conditions"], "model_calls": data["observer_protocol"]["model_calls"]},
        {"layer": "validity_corpus", "families": data["validity_gate"]["families"], "conditions": data["validity_gate"]["conditions"], "model_calls": data["validity_gate"]["model_calls"]},
    ]
    with (out / "part1_baseline_layers.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (out / "part1_gate_summary.json").write_text(json.dumps({
        "twin_hidden_comparisons": data["twin_gate_v3"]["hidden_twin_comparisons"],
        "twin_sensitive_arms": data["twin_gate_v3"]["perturbation_sensitive_arms"],
        "visible_positive_controls": data["twin_gate_v3"]["visible_positive_controls"],
        "source_attested_sensitive_arms": data["validity_gate"]["source_attested_sensitive_arms"],
        "hidden_expiry_comparisons": data["validity_gate"]["hidden_expiry_comparisons"],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "rows": len(rows), "output": str(out)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
