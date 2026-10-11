#!/usr/bin/env python3
"""PUB-T-988 single pinned, naturally sourced Publisher PUB.
Mutations arise exclusively inside unchanged T984 Writer step() on GitHub.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

NATURAL_SHA="ba0b30328b7fdf4d8c6209de0925d6113dc95b917b95caa2d64218869970dd79"
NATURAL_SIZE=99328
DONOR_PIN="87094c23e2a9eaa2aa9e95d72ec52f72ef109f11"
DONOR_TREE="8146fa9fdd2f577ebe02bc7205a61bb14e20d3e7"
RAR2_PIN="703808408fd919e564a90cdc236e81db3c04af8b"
SCIENCE_984="14ac75ae0346b3bdbeeada110e1f463dda6cbb27"
INVERSE_963="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
SOURCE_971="cd38c8d6a545737f9f99821076340505db5e149c"
SCHEMA="sk1.cfb-exp-pub-t-988.source.v1"

def count_summary(records):
    counters=Counter()
    states=Counter()
    first_status=Counter()
    second_status=Counter()
    witnesses=[]
    reached_fe=reached_100=0
    for r in records:
        counters[r["status"]]+=1
        p=r["probe"]
        if p is None:continue
        if p["status"]!="EVALUATED":
            continue
        for st in p["candidate_stories"]:
            sequence=st["sequence"]
            counters["story_trials"]+=1
            counters["completed_writer_writes"]+=sequence["completed_writer_materializations"]
            states[str(sequence["completed_cycles"])+"_completed_cycles"]+=1
            reached_fe+=int(sequence["reached_writer_generated_fe"])
            reached_100+=int(sequence["reached_writer_generated_0100"])
            for c in sequence["cycles"]:
                status=c["status"]
                counters["cycle_"+status]+=1
                if c.get("insert") is not None:
                    first_status[c["insert"]["status"]]+=1
                if c.get("delete") is not None:
                    second_status[c["delete"]["status"]]+=1
                if status=="PASS":
                    counters["cycle_"+str(c["cycle"])+"_pass"]+=1
                    counters["cycle_actual_changed_"+str(c["cycle_raw"]["changed_same_offset_bytes"])]+=1
                    if c["cycle"]==3:
                        counters["crossed_FE_to_0100"]+=1
                elif status=="RAW_MODEL_COUNTEREXAMPLE":
                    witnesses.append({
                        "source_sha256":r["source_sha256"],
                        "story_ordinal":st["story_ordinal"],
                        "cycle":c["cycle"],
                        "start_header":c["start_header"],
                        "after_delete_header":c["after_delete_header"],
                        "observed_raw":c["cycle_raw"]["changed_same_offset_bytes"],
                        "expected_raw":c["expected_changed_cycle_raw_bytes"]
                    })
    return {
        "source_status":dict(sorted(states.items())) if False else dict(sorted((k,v) for k,v in counters.items() if k in {"EVALUATED","SOURCE_PROBE_UNAVAILABLE"})),
        "counts":dict(sorted(counters.items())),
        "finished_cycle_distribution":dict(sorted(states.items())),
        "first_writer_outcomes":dict(sorted(first_status.items())),
        "second_writer_outcomes":dict(sorted(second_status.items())),
        "writer_derived_FE_story_trials":reached_fe,
        "writer_derived_0x100_story_trials":reached_100,
        "physical_counterexamples":witnesses,
        "genuine_original_Publisher_FE":False,
        "manual_counter_rewrite":False,
        "native_publisher_acceptance":"NOT_EVALUATED"
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--rar2",required=True,type=Path)
    ap.add_argument("--donor",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    root=a.rar2.resolve(strict=True)
    donor=a.donor.resolve(strict=True)
    src=donor/"pub-corpus/corpus/native/unclassified"/(NATURAL_SHA+".pub")
    out=a.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    binary=root/"tools/native-pub-candidate-cli/target/release/examples/sk1_pub_t_988_writer_chain"
    if not binary.is_file():ap.error("pinned Writer chain Rust binary missing")
    data=src.read_bytes()
    if hashlib.sha256(data).hexdigest()!=NATURAL_SHA or len(data)!=NATURAL_SIZE:
        raise RuntimeError("source immutable SHA/size mismatch")
    plan={
      "schema":"sk1.cfb-exp-pub-t-988.plan.v1",
      "original_pub_sha256":NATURAL_SHA,
      "original_pub_bytes":NATURAL_SIZE,
      "original_syid_header":250,
      "original_syid_count":21,
      "original_max_live":250,
      "donor_commit":DONOR_PIN,"donor_tree":DONOR_TREE,
      "upstream_writer":RAR2_PIN,
      "t984_science_pin":SCIENCE_984,
      "t963_inherited_helpers":INVERSE_963,
      "t971_source_control":SOURCE_971,
      "fixed_story_selection":"up to 3 original Quill ordinal eligible, second ASCII only",
      "number_of_insert_delete_cycles_per_story":3,
      "predicted_end_headers":[252,254,256],
      "predicted_final_cycle_FE_to_0100_raw_changed_bytes":2,
      "writer_generated_FE_not_native_Publisher_FE":True,
      "direct_SYID_header_rewrite":False,
      "native_publisher_acceptance":"NOT_EVALUATED",
      "pub_bytes_export_authorized":False
    }
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n")
    with tempfile.TemporaryDirectory(prefix="sk1-pub-t988-chain-") as td:
        tmp=Path(td)/"receipt.json"
        p=subprocess.run([str(binary),str(src),NATURAL_SHA,str(tmp)],
             capture_output=True,check=False,timeout=400)
        if p.returncode or not tmp.is_file():
            record={"source_sha256":NATURAL_SHA,"source_bytes":NATURAL_SIZE,
                    "status":"SOURCE_PROBE_UNAVAILABLE","probe":None}
        else:
            proof=json.loads(tmp.read_text(encoding="utf-8"))
            if (proof.get("schema")!=SCHEMA
                or proof.get("source_sha256")!=NATURAL_SHA
                or proof.get("source_bytes")!=NATURAL_SIZE
                or proof.get("publisher_native_acceptance")!="NOT_EVALUATED"
                or proof.get("manual_syid_rewrite") is not False
                or proof.get("original_publisher_fe_ff_witness") is not False):
                raise RuntimeError("source-safe Writer receipt drift")
            record={"source_sha256":NATURAL_SHA,"source_bytes":NATURAL_SIZE,
                    "status":proof["status"],"probe":proof}
    # No raw original or Writer-generated intermediate PUB is copied to artifacts.
    records=[record]
    (out/"records.json").write_text(json.dumps(records,indent=2)+"\n")
    report={"schema":"sk1.cfb-exp-pub-t-988.report.v1",
        "plan_sha256":hashlib.sha256((out/"plan.json").read_bytes()).hexdigest(),
        "summary":count_summary(records),"records":records,
        "original_natural_Publisher_FE":False,
        "manual_syid_header_rewrite":False,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "pub_bytes_export_authorized":False}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    s=report["summary"]
    print(json.dumps({"status":record["status"],
         "selected_stories":s["counts"].get("story_trials",0),
         "completed_writer_writes":s["counts"].get("completed_writer_writes",0),
         "writer_derived_FE_story_trials":s["writer_derived_FE_story_trials"],
         "writer_derived_0x100_story_trials":s["writer_derived_0x100_story_trials"],
         "exact_cycles":s["counts"].get("cycle_PASS",0),
         "raw_model_counterexamples":len(s["physical_counterexamples"])},sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
