"""One-command, model-free verification against the committed reference results."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    if args.out.exists(): parser.error("choose a new output directory")
    vendor=json.loads((root/"audits/gatemem_vendor_manifest.json").read_text(encoding="utf-8"))
    for record in vendor["files"]:
        if hashlib.sha256((root/record["vendored_path"]).read_bytes()).hexdigest()!=record["sha256"]:
            raise SystemExit("Vendored source mismatch: "+record["vendored_path"])
    sys.path.insert(0,str(root/"src"))
    from observer_study.replay import run_audit, DEFAULT_FIXTURE
    from observer_study.matcher_audit import audit
    args.out.mkdir(parents=True)
    replay=run_audit(DEFAULT_FIXTURE,args.out/"same_chain")
    reference=json.loads((root/"data/replay_opaque/reference_run_v2/same_chain_summary.json").read_text(encoding="utf-8"))
    matcher=audit()
    matcher_reference=json.loads((root/"data/matcher_audit/reference_report.json").read_text(encoding="utf-8"))
    (args.out/"matcher_report.json").write_text(json.dumps(matcher,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    checks={"same_chain_summary_matches":replay==reference,"matcher_report_matches":matcher==matcher_reference,
            "no_model_calls":replay["model_calls"]==matcher["model_calls"]==0}
    result={"status":"REPRODUCED" if all(checks.values()) else "MISMATCH","checks":checks,
            "meaning":"Recorded experiments match frozen results; nested gate FAIL is intentional fault rejection."}
    (args.out/"verification.json").write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,indent=2))
    return 0 if all(checks.values()) else 1

if __name__=="__main__": raise SystemExit(main())
