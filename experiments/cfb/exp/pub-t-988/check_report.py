#!/usr/bin/env python3
"""PUB-T-988 independent source-safe receipt and physical LittleEndian +2 audit.
A real Writer guard may stop the chain; it is not a reason to hide failure.
"""
from __future__ import annotations
import hashlib, importlib.util, json, subprocess, sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
PLAN_KEYS={"schema","original_pub_sha256","original_pub_bytes","original_syid_header",
    "original_syid_count","original_max_live","donor_commit","donor_tree",
    "upstream_writer","t984_science_pin","t963_inherited_helpers","t971_source_control",
    "fixed_story_selection","number_of_insert_delete_cycles_per_story",
    "predicted_end_headers","predicted_final_cycle_FE_to_0100_raw_changed_bytes",
    "writer_generated_FE_not_native_Publisher_FE","direct_SYID_header_rewrite",
    "native_publisher_acceptance","pub_bytes_export_authorized"}
PROBE_KEYS={"schema","source_sha256","source_bytes","original_natural_syid",
    "source_syid_count","source_syid_max_live","source_intact","candidate_stories",
    "status","publisher_native_acceptance","original_publisher_fe_ff_witness",
    "manual_syid_rewrite"}
STORY_KEYS={"story_ordinal","story_utf16_length","ascii_alphanumeric_count",
            "offset_utf16","sequence"}
SEQ_KEYS={"completed_cycles","completed_writer_materializations","cycles",
    "reached_writer_generated_fe","reached_writer_generated_0100",
    "source_original_unchanged"}
CYCLE_KEYS={"cycle","status","start_header","after_insert_header",
     "after_delete_header","insert","delete","expected_final_header",
     "expected_changed_cycle_raw_bytes","cycle_raw","cycle_cfb",
     "original_raw","original_cfb","matches_exact_raw_quill_model"}
RAW_KEYS={"source_file_length","final_file_length","equal_length",
          "changed_same_offset_bytes","extra_bytes","whole_file_equal"}
TYPES={"PASS","RAW_MODEL_COUNTEREXAMPLE","INSERT_BLOCKED","DELETE_BLOCKED",
       "START_COUNTER_DRIFT","INSERT_SYID_COUNTER_DRIFT",
       "CYCLE_CFB_DIFF_BLOCKED","ORIGINAL_CFB_DIFF_BLOCKED"}

def mod(path,name):
    sp=importlib.util.spec_from_file_location(name,path)
    assert sp and sp.loader
    m=importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m

def uint(x,m=0xffffffff):
    assert type(x) is int and 0<=x<=m

def nchanged(a,b):
    return sum(x!=y for x,y in zip(a.to_bytes(4,"little"),b.to_bytes(4,"little")))

def rawcheck(raw):
    assert isinstance(raw,dict) and set(raw)==RAW_KEYS
    for k in ("source_file_length","final_file_length",
              "changed_same_offset_bytes","extra_bytes"):uint(raw[k],128*1024*1024)
    assert raw["equal_length"]==(raw["source_file_length"]==raw["final_file_length"])
    assert raw["extra_bytes"]==abs(raw["source_file_length"]-raw["final_file_length"])
    assert raw["whole_file_equal"]==(raw["equal_length"] and raw["changed_same_offset_bytes"]==0)
    assert type(raw["equal_length"]) is type(raw["whole_file_equal"]) is bool

def cfbcheck(cfb,legacy,orig,end):
    assert isinstance(cfb,dict)
    assert cfb["schema"]=="sk1.cfb-diag-pub-t-988.diff.v1"
    x=cfb.copy();x["schema"]="sk1.cfb-diag-pub-t-963.diff.v1"
    legacy.check_diff(x)
    assert cfb["source_syid_first_dword"]==orig
    assert cfb["final_syid_first_dword"]==end

def check_cycle(cycle,legacy,source_ordinal):
    assert isinstance(cycle,dict) and cycle["status"] in TYPES
    assert cycle["cycle"]==source_ordinal
    if cycle["status"]=="START_COUNTER_DRIFT":
        assert set(cycle)=={"cycle","status","observed_header","expected_header"}
        uint(cycle["observed_header"]);uint(cycle["expected_header"])
        return 0
    assert set(cycle)==CYCLE_KEYS
    assert cycle["start_header"]==250+2*(source_ordinal-1)
    assert cycle["expected_final_header"]==cycle["start_header"]+2
    assert cycle["expected_changed_cycle_raw_bytes"]==nchanged(
        cycle["start_header"],cycle["expected_final_header"])
    assert cycle["insert"] is not None
    legacy.check_step(cycle["insert"])
    completed=int(cycle["insert"]["status"]=="HOSTED_PASS")
    if cycle["insert"]["status"]=="HOSTED_PASS":
        assert cycle["after_insert_header"] is not None
        uint(cycle["after_insert_header"])
    else:
        assert cycle["status"]=="INSERT_BLOCKED"
        assert cycle["after_insert_header"] is None
        assert cycle["delete"] is None
        assert cycle["after_delete_header"] is None
        assert cycle["cycle_raw"] is None
        assert cycle["cycle_cfb"] is None
        assert cycle["original_raw"] is None
        assert cycle["original_cfb"] is None
        return completed
    if cycle["status"]=="INSERT_SYID_COUNTER_DRIFT":
        assert cycle["after_insert_header"]!=cycle["start_header"]+1
        assert cycle["delete"] is None
        return completed
    assert cycle["after_insert_header"]==cycle["start_header"]+1
    assert cycle["delete"] is not None
    legacy.check_step(cycle["delete"])
    completed+=int(cycle["delete"]["status"]=="HOSTED_PASS")
    if cycle["delete"]["status"]!="HOSTED_PASS":
        assert cycle["status"]=="DELETE_BLOCKED"
        assert cycle["after_delete_header"] is None
        assert cycle["cycle_raw"] is None
        return completed
    end=cycle["after_delete_header"]
    uint(end)
    rawcheck(cycle["cycle_raw"])
    rawcheck(cycle["original_raw"])
    if cycle["cycle_cfb"] is None:
        assert cycle["status"]=="CYCLE_CFB_DIFF_BLOCKED"
        return completed
    cfbcheck(cycle["cycle_cfb"],legacy,cycle["start_header"],end)
    if cycle["original_cfb"] is None:
        assert cycle["status"]=="ORIGINAL_CFB_DIFF_BLOCKED"
        return completed
    cfbcheck(cycle["original_cfb"],legacy,250,end)
    cfb=cycle["cycle_cfb"];ocfb=cycle["original_cfb"]
    raw=cycle["cycle_raw"];ora=cycle["original_raw"]
    predicted=cycle["expected_final_header"]
    expected_raw=cycle["expected_changed_cycle_raw_bytes"]
    full=nchanged(250,end)
    flag=(predicted==end and raw["equal_length"] and raw["extra_bytes"]==0
        and raw["changed_same_offset_bytes"]==expected_raw
        and ora["equal_length"] and ora["extra_bytes"]==0
        and ora["changed_same_offset_bytes"]==full
        and cfb["source_syid_first_dword"]==cycle["start_header"]
        and cfb["final_syid_first_dword"]==end
        and cfb["syid_first_dword_delta"]==2
        and cfb["syid_first_dword_changed_bytes"]==expected_raw
        and cfb["quill_changed_bytes_outside_syid_first_dword"]==0
        and cfb["same_quill_TEXT_payload_bytes"] is True
        and cfb["same_quill_story_syid_sequence"] is True
        and cfb["non_quill_streams_changed"]==0
        and cfb["missing_cfb_paths"]==0
        and cfb["added_cfb_paths"]==0
        and cfb["cfb_entry_type_changes"]==0
        and cfb["matched_descriptor_sequence"] is True
        and ocfb["source_syid_first_dword"]==250
        and ocfb["final_syid_first_dword"]==end
        and ocfb["syid_first_dword_delta"]==end-250
        and ocfb["quill_changed_bytes_outside_syid_first_dword"]==0
        and ocfb["same_quill_TEXT_payload_bytes"] is True
        and ocfb["same_quill_story_syid_sequence"] is True
        and ocfb["non_quill_streams_changed"]==0
        and ocfb["matched_descriptor_sequence"] is True)
    assert cycle["matches_exact_raw_quill_model"] is flag
    assert cycle["status"]==("PASS" if flag else "RAW_MODEL_COUNTEREXAMPLE")
    return completed

def check(out,donor,ref):
    run=mod(HERE/"run.py","sk1_988_runner")
    legacy=mod(ref/"experiments/cfb/val/pub-t-963/check_report.py","sk1_963_audit")
    assert {x.name for x in out.iterdir()}=={"plan.json","records.json","report.json"}
    p=json.loads((out/"plan.json").read_text())
    assert set(p)==PLAN_KEYS
    assert p["schema"]=="sk1.cfb-exp-pub-t-988.plan.v1"
    assert p["original_pub_sha256"]==run.NATURAL_SHA
    assert p["original_pub_bytes"]==99328
    assert (p["original_syid_header"],p["original_syid_count"],
            p["original_max_live"])==(250,21,250)
    assert p["donor_commit"]==run.DONOR_PIN and p["donor_tree"]==run.DONOR_TREE
    assert p["upstream_writer"]==run.RAR2_PIN
    assert p["t984_science_pin"]==run.SCIENCE_984
    assert p["t963_inherited_helpers"]==run.INVERSE_963
    assert p["t971_source_control"]==run.SOURCE_971
    assert p["number_of_insert_delete_cycles_per_story"]==3
    assert p["predicted_end_headers"]==[252,254,256]
    assert p["predicted_final_cycle_FE_to_0100_raw_changed_bytes"]==2
    assert p["writer_generated_FE_not_native_Publisher_FE"] is True
    assert p["direct_SYID_header_rewrite"] is False
    assert p["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert p["pub_bytes_export_authorized"] is False
    assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=donor,text=True).strip()==run.DONOR_PIN
    assert subprocess.check_output(["git","rev-parse","HEAD:pub-corpus/corpus/native/unclassified"],cwd=donor,text=True).strip()==run.DONOR_TREE
    source=donor/"pub-corpus/corpus/native/unclassified"/(run.NATURAL_SHA+".pub")
    assert source.is_file() and source.stat().st_size==99328
    assert hashlib.sha256(source.read_bytes()).hexdigest()==run.NATURAL_SHA

    r=json.loads((out/"report.json").read_text())
    rows=json.loads((out/"records.json").read_text())
    assert set(r)=={"schema","plan_sha256","summary","records",
                    "original_natural_Publisher_FE","manual_syid_header_rewrite",
                    "native_publisher_acceptance","pub_bytes_export_authorized"}
    assert r["schema"]=="sk1.cfb-exp-pub-t-988.report.v1"
    assert r["plan_sha256"]==hashlib.sha256((out/"plan.json").read_bytes()).hexdigest()
    assert r["records"]==rows and len(rows)==1
    assert r["original_natural_Publisher_FE"] is False
    assert r["manual_syid_header_rewrite"] is False
    assert r["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert r["pub_bytes_export_authorized"] is False
    only=rows[0]
    assert set(only)=={"source_sha256","source_bytes","status","probe"}
    assert only["source_sha256"]==run.NATURAL_SHA and only["source_bytes"]==99328
    assert only["status"] in {"SOURCE_PROBE_UNAVAILABLE","SOURCE_EDITOR_OPEN_BLOCKED",
        "NO_ELIGIBLE_STORIES","EVALUATED"}
    if only["status"]=="SOURCE_PROBE_UNAVAILABLE":
        assert only["probe"] is None
    else:
        pr=only["probe"]
        assert set(pr)==PROBE_KEYS and pr["status"]==only["status"]
        assert pr["schema"]==run.SCHEMA
        assert (pr["original_natural_syid"],pr["source_syid_count"],
                pr["source_syid_max_live"])==(250,21,250)
        assert pr["source_sha256"]==run.NATURAL_SHA
        assert pr["source_bytes"]==99328
        assert pr["source_intact"] is True
        assert pr["publisher_native_acceptance"]=="NOT_EVALUATED"
        assert pr["original_publisher_fe_ff_witness"] is False
        assert pr["manual_syid_rewrite"] is False
        assert isinstance(pr["candidate_stories"],list) and len(pr["candidate_stories"])<=3
        if pr["status"]=="EVALUATED":
            assert len(pr["candidate_stories"])>=1
        else:
            assert pr["candidate_stories"]==[]
        for ordinal,st in enumerate(pr["candidate_stories"]):
            assert set(st)==STORY_KEYS and st["story_ordinal"]==ordinal
            uint(st["story_utf16_length"],2**31)
            assert st["ascii_alphanumeric_count"]>=2
            uint(st["offset_utf16"],2**31)
            assert st["offset_utf16"]<st["story_utf16_length"]
            sq=st["sequence"]
            assert set(sq)==SEQ_KEYS
            cycles=sq["cycles"]
            assert isinstance(cycles,list) and 1<=len(cycles)<=3
            expected_complete=sum(c["status"]=="PASS" for c in cycles)
            assert sq["completed_cycles"]==expected_complete
            assert sq["reached_writer_generated_fe"] is any(
                c["status"]=="PASS" and c.get("after_delete_header")==254 for c in cycles)
            assert sq["reached_writer_generated_0100"] is (
                cycles[-1]["status"]=="PASS" and cycles[-1].get("after_delete_header")==256)
            assert sq["source_original_unchanged"] is True
            writes=0
            for index,c in enumerate(cycles,1):
                writes+=check_cycle(c,legacy,index)
                if index<len(cycles):
                    assert c["status"]=="PASS","only successful cycles can lead to next"
            assert sq["completed_writer_materializations"]==writes
    assert r["summary"]==run.count_summary(rows)
    print("PUB-T-988 original and receipts independently checked:")
    print(json.dumps({
        "status":only["status"],
        "story_count":r["summary"]["counts"].get("story_trials",0),
        "fe_derived":r["summary"]["writer_derived_FE_story_trials"],
        "reached_0x100":r["summary"]["writer_derived_0x100_story_trials"],
        "physical_counterexamples":len(r["summary"]["physical_counterexamples"])
    },sort_keys=True))

if __name__=="__main__":
    assert len(sys.argv)==4
    check(Path(sys.argv[1]),Path(sys.argv[2]),Path(sys.argv[3]))
