#!/usr/bin/env python3
"""PUB-T-993: real, immutable publisher 2007 original 0x3F1 + eight Writer cycles.

T992 downloads and authenticates all 13 historic MicrosoftPress archive PUBs.
The original Writer of T988/T984 performs every edit; no counter rewriting.
Only plan, records, report JSON leave this GitHub worker.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,subprocess,tempfile
from collections import Counter
from pathlib import Path

ORIGINAL_SHA="b4b005a7e6f662546cf07bdd155a1cf936293e6ceb6ac7f424456fee87051f1b"
ORIGINAL_SIZE=471552
ORIGINAL_SYID=1009
ORIGINAL_SYID_COUNT=65
ORIGINAL_MAX_LIVE=965
RAR2_PIN="703808408fd919e564a90cdc236e81db3c04af8b"
SOURCE_T992_PIN="cfcce7f3f9c425210ee28265d4dbdf79bf742dcc"
SCIENTIFIC_T988_PIN="72e64b9c48fc108df656cd0a3be3fa67167d405e"
SCIENCE_T984_PIN="14ac75ae0346b3bdbeeada110e1f463dda6cbb27"
INVERSE_T963_PIN="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
SOURCE_T971_PIN="cd38c8d6a545737f9f99821076340505db5e149c"
SCHEMA="sk1.cfb-exp-pub-t-993.source.v1"
ORIGINAL_PACKAGE_KEY="publisher2007_sbs"
END_HEADERS=[ORIGINAL_SYID+2*(i+1) for i in range(8)]
SHA_CHARS=set("0123456789abcdef")

def file_sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def module(path:Path,name):
    sp=importlib.util.spec_from_file_location(name,path)
    assert sp and sp.loader
    m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
def git(root:Path,*args):
    return subprocess.check_output(["git",*args],cwd=root,text=True).strip()

def count_summary(rows):
    statuses=Counter();cycle_status=Counter();first_status=Counter();second_status=Counter()
    cycle_physical=Counter();finishes=Counter();errors=[]
    selected=steps=done_cycles=reached_03ff=reached_0401=0
    for r in rows:
        statuses[r["status"]]+=1
        p=r["probe"]
        if p is None:continue
        if p["status"]!="EVALUATED":continue
        for st in p["candidate_stories"]:
            selected+=1
            q=st["sequence"]
            steps+=q["completed_writer_materializations"]
            done_cycles+=q["completed_cycles"]
            finishes[str(q["completed_cycles"])+"_completed_cycles"]+=1
            reached_03ff+=int(q["reached_writer_generated_03ff"])
            reached_0401+=int(q["reached_writer_generated_0401"])
            for cycle in q["cycles"]:
                cycle_status[cycle["status"]]+=1
                if cycle["insert"] is not None:first_status[cycle["insert"]["status"]]+=1
                if cycle["delete"] is not None:second_status[cycle["delete"]["status"]]+=1
                if cycle["status"]=="PASS":
                    cycle_physical[str(cycle["cycle"])+"_cycle_"+str(cycle["cycle_raw"]["changed_same_offset_bytes"])+"_bytes"]+=1
                    if cycle["cycle"]==8:cycle_physical["full_03ff_to_0401"]+=1
                elif cycle["status"]=="RAW_MODEL_COUNTEREXAMPLE":
                    errors.append({"source_sha256":r["source_sha256"],
                         "story_ordinal":st["story_ordinal"],
                         "cycle":cycle["cycle"],"start_header":cycle["start_header"],
                         "observed_end_header":cycle["after_delete_header"],
                         "expected_final_header":cycle["expected_final_header"],
                         "observed_raw_bytes":cycle["cycle_raw"]["changed_same_offset_bytes"],
                         "expected_raw_bytes":cycle["expected_changed_cycle_raw_bytes"]})
    return {
        "source_status":dict(sorted(statuses.items())),
        "original_pub_source_sha_verified":statuses["EVALUATED"]+statuses["SOURCE_EDITOR_OPEN_BLOCKED"]+statuses["NO_ELIGIBLE_STORIES"]+statuses["SOURCE_PROBE_UNAVAILABLE"],
        "eligible_original_stories":selected,
        "writer_step_outcomes_first":dict(sorted(first_status.items())),
        "writer_step_outcomes_second":dict(sorted(second_status.items())),
        "writer_actual_materializations":steps,
        "writer_full_cycle_count":done_cycles,
        "writer_cycle_results":dict(sorted(cycle_status.items())),
        "writer_cycle_physical_byte_counts":dict(sorted(cycle_physical.items())),
        "writer_cycle_completions":dict(sorted(finishes.items())),
        "writer_generated_03ff_story_trials":reached_03ff,
        "writer_generated_0401_story_trials":reached_0401,
        "cycle_8_03ff_to_0401_full_raw_two_bytes":cycle_physical["8_cycle_2_bytes"],
        "model_counterexamples":errors,
        "original_publisher_saveas_03ff_claim":False,
        "manual_original_SYID_byte_edits":0,
        "native_microsoft_publisher_acceptance":"NOT_EVALUATED"
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--rar2",required=True,type=Path)
    ap.add_argument("--reference-992",required=True,type=Path)
    ap.add_argument("--source-stage",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    a=ap.parse_args()
    rar=a.rar2.resolve(strict=True)
    ref=a.reference_992.resolve(strict=True)
    stage=a.source_stage.resolve();stage.mkdir(parents=True,exist_ok=True)
    output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    assert not list(stage.iterdir()),"original stage must start empty"
    assert git(rar,"rev-parse","HEAD")==RAR2_PIN
    assert git(ref,"rev-parse","HEAD")==SOURCE_T992_PIN
    old=module(ref/"experiments/cfb/diag/pub-t-992/run.py","frozen_training_992")
    packages,entries=old.frozen_training(rar)
    selected=[p for p in packages if p["key"]==ORIGINAL_PACKAGE_KEY]
    assert len(selected)==1 and selected[0]["expected_unique_sha_count"]==13
    expected=[r for key,r in entries if key==ORIGINAL_PACKAGE_KEY and r["sha256"]==ORIGINAL_SHA]
    assert len(expected)==1
    assert expected[0]["size"]==ORIGINAL_SIZE
    source_status,package_sha=old.retrieve_package(selected[0],stage)
    record={"source_sha256":ORIGINAL_SHA,"source_bytes":ORIGINAL_SIZE,
            "package_key":ORIGINAL_PACKAGE_KEY,
            "source_package_status":source_status,
            "source_package_archive_sha256":package_sha,
            "status":"SOURCE_ARCHIVE_UNAVAILABLE","probe":None}
    if source_status=="VERIFIED":
        files=sorted(stage.glob("*.pub"))
        assert len(files)==13
        expected_sha={x["sha256"] for x in selected[0]["files"]}
        assert {x.stem for x in files}==expected_sha
        for p in files:
            row=next(y for y in selected[0]["files"] if y["sha256"]==p.stem)
            assert file_sha(p)==p.stem and p.stat().st_size==row["size"]
        src=stage/(ORIGINAL_SHA+".pub")
        assert file_sha(src)==ORIGINAL_SHA and src.stat().st_size==ORIGINAL_SIZE
        writer=rar/"tools/native-pub-candidate-cli/target/release/examples/sk1_pub_t_993_writer_chain"
        if not writer.is_file():
            raise RuntimeError("immutable original Writer chain executable missing")
        with tempfile.TemporaryDirectory(prefix="sk1-t993-true-writer-") as td:
            tmp=Path(td)/"receipt.json"
            try:
                proc=subprocess.run([str(writer),str(src),ORIGINAL_SHA,str(tmp)],
                      capture_output=True,timeout=800,check=False)
            except (OSError,subprocess.TimeoutExpired):
                proc=None
            if proc is None or proc.returncode!=0 or not tmp.is_file():
                record["status"]="SOURCE_PROBE_UNAVAILABLE"
            else:
                receipt=json.loads(tmp.read_text(encoding="utf-8"))
                assert receipt["schema"]==SCHEMA
                assert receipt["source_sha256"]==ORIGINAL_SHA
                assert receipt["source_bytes"]==ORIGINAL_SIZE
                assert (receipt["original_natural_syid"],
                        receipt["source_syid_count"],
                        receipt["source_syid_max_live"])==(1009,65,965)
                assert receipt["publisher_native_acceptance"]=="NOT_EVALUATED"
                assert receipt["manual_syid_rewrite"] is False
                assert receipt["original_publisher_fe_ff_witness"] is False
                assert receipt["source_intact"] is True
                record["status"]=receipt["status"]
                record["probe"]=receipt
        assert file_sha(src)==ORIGINAL_SHA,"original PUB modified by Writer!"
    records=[record]
    plan={
        "schema":"sk1.cfb-exp-pub-t-993.plan.v1",
        "source_RAR_pin":RAR2_PIN,
        "source_T992_scientific_retriever_pin":SOURCE_T992_PIN,
        "real_Writer_T988_chain_pin":SCIENTIFIC_T988_PIN,
        "upstream_original_Writer_T984_pin":SCIENCE_T984_PIN,
        "upstream_original_Writer_helpers_T963_pin":INVERSE_T963_PIN,
        "upstream_source_T971_pin":SOURCE_T971_PIN,
        "original_sha256":ORIGINAL_SHA,"original_bytes":ORIGINAL_SIZE,
        "source_training_package":ORIGINAL_PACKAGE_KEY,
        "source_original_SYID_header":ORIGINAL_SYID,
        "source_original_SYID_count":ORIGINAL_SYID_COUNT,
        "source_original_max_live_SYID":ORIGINAL_MAX_LIVE,
        "max_preregistered_original_Quill_stories":3,
        "fixed_story_ascii_slot":"second ascii alphanumeric",
        "genuine_writer_insert_delete_cycles_per_story":8,
        "expected_complete_cycle_headers":END_HEADERS,
        "expected_cross_boundary_middle_03ff_to_0400_to_0401":True,
        "expected_final_cycle_changed_raw_bytes":2,
        "manual_original_SYID_header_edits":0,
        "upstream_product_modified":False,
        "native_microsoft_publisher_acceptance":"NOT_EVALUATED",
        "raw_PUB_archive_artifact_export_authorized":False
    }
    (output/"plan.json").write_text(json.dumps(plan,indent=2)+"\n")
    (output/"records.json").write_text(json.dumps(records,indent=2)+"\n")
    report={
        "schema":"sk1.cfb-exp-pub-t-993.report.v1",
        "plan_sha256":file_sha(output/"plan.json"),
        "records":records,"summary":count_summary(records),
        "raw_PUB_archive_artifact_export_authorized":False,
        "native_microsoft_publisher_acceptance":"NOT_EVALUATED"
    }
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    s=report["summary"]
    print(json.dumps({"original_source_status":record["status"],
        "source_package_status":source_status,
        "eligible_story_trials":s["eligible_original_stories"],
        "writer_actual_materializations":s["writer_actual_materializations"],
        "completed_inverse_cycles":s["writer_full_cycle_count"],
        "writer_generated_03ff":s["writer_generated_03ff_story_trials"],
        "writer_generated_0401":s["writer_generated_0401_story_trials"],
        "physical_two_byte_boundary_trials":s["cycle_8_03ff_to_0401_full_raw_two_bytes"],
        "model_counterexamples":len(s["model_counterexamples"])
    },sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
