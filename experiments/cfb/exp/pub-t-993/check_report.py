#!/usr/bin/env python3
"""PUB-T-993 independent source-safe receipt and physical LittleEndian +2 audit.
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
    "reached_writer_generated_03ff","reached_writer_generated_0401",
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
    assert cfb["schema"]=="sk1.cfb-diag-pub-t-993.diff.v1"
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
    assert cycle["start_header"]==1009+2*(source_ordinal-1)
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
    cfbcheck(cycle["original_cfb"],legacy,1009,end)
    cfb=cycle["cycle_cfb"];ocfb=cycle["original_cfb"]
    raw=cycle["cycle_raw"];ora=cycle["original_raw"]
    predicted=cycle["expected_final_header"]
    expected_raw=cycle["expected_changed_cycle_raw_bytes"]
    full=nchanged(1009,end)
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
        and ocfb["source_syid_first_dword"]==1009
        and ocfb["final_syid_first_dword"]==end
        and ocfb["syid_first_dword_delta"]==end-1009
        and ocfb["quill_changed_bytes_outside_syid_first_dword"]==0
        and ocfb["same_quill_TEXT_payload_bytes"] is True
        and ocfb["same_quill_story_syid_sequence"] is True
        and ocfb["non_quill_streams_changed"]==0
        and ocfb["matched_descriptor_sequence"] is True)
    assert cycle["matches_exact_raw_quill_model"] is flag
    assert cycle["status"]==("PASS" if flag else "RAW_MODEL_COUNTEREXAMPLE")
    return completed


def check(out:Path,rar2:Path,ref992:Path,stage:Path,ref963:Path):
    run=mod(HERE/"run.py","real_high_original_993")
    source=mod(ref992/"experiments/cfb/diag/pub-t-992/run.py","frozen_992_source_retriever")
    legacy=mod(ref963/"experiments/cfb/val/pub-t-963/check_report.py","pinned_963_cfb_checker")
    rar2=rar2.resolve(strict=True);ref992=ref992.resolve(strict=True)
    ref963=ref963.resolve(strict=True);stage=stage.resolve(strict=True)
    out=out.resolve(strict=True)
    assert {p.name for p in out.iterdir()}=={"plan.json","records.json","report.json"}
    assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=rar2,text=True).strip()==run.RAR2_PIN
    assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=ref992,text=True).strip()==run.SOURCE_T992_PIN
    assert subprocess.check_output(["git","rev-parse","HEAD"],cwd=ref963,text=True).strip()==run.INVERSE_T963_PIN

    p=json.loads((out/"plan.json").read_text(encoding="utf-8"))
    assert set(p)=={
      "schema","source_RAR_pin","source_T992_scientific_retriever_pin",
      "real_Writer_T988_chain_pin","upstream_original_Writer_T984_pin",
      "upstream_original_Writer_helpers_T963_pin","upstream_source_T971_pin",
      "original_sha256","original_bytes","source_training_package",
      "source_original_SYID_header","source_original_SYID_count",
      "source_original_max_live_SYID","max_preregistered_original_Quill_stories",
      "fixed_story_ascii_slot","genuine_writer_insert_delete_cycles_per_story",
      "expected_complete_cycle_headers",
      "expected_cross_boundary_middle_03ff_to_0400_to_0401",
      "expected_final_cycle_changed_raw_bytes",
      "manual_original_SYID_header_edits","upstream_product_modified",
      "native_microsoft_publisher_acceptance","raw_PUB_archive_artifact_export_authorized"}
    assert p["schema"]=="sk1.cfb-exp-pub-t-993.plan.v1"
    assert p["source_RAR_pin"]==run.RAR2_PIN
    assert p["source_T992_scientific_retriever_pin"]==run.SOURCE_T992_PIN
    assert p["real_Writer_T988_chain_pin"]==run.SCIENTIFIC_T988_PIN
    assert p["upstream_original_Writer_T984_pin"]==run.SCIENCE_T984_PIN
    assert p["upstream_original_Writer_helpers_T963_pin"]==run.INVERSE_T963_PIN
    assert p["upstream_source_T971_pin"]==run.SOURCE_T971_PIN
    assert p["original_sha256"]==run.ORIGINAL_SHA
    assert p["original_bytes"]==run.ORIGINAL_SIZE==471552
    assert p["source_training_package"]==run.ORIGINAL_PACKAGE_KEY=="publisher2007_sbs"
    assert (p["source_original_SYID_header"],p["source_original_SYID_count"],
            p["source_original_max_live_SYID"])==(1009,65,965)
    assert p["max_preregistered_original_Quill_stories"]==3
    assert p["fixed_story_ascii_slot"]=="second ascii alphanumeric"
    assert p["genuine_writer_insert_delete_cycles_per_story"]==8
    assert p["expected_complete_cycle_headers"]==[1011,1013,1015,1017,1019,1021,1023,1025]
    assert p["expected_cross_boundary_middle_03ff_to_0400_to_0401"] is True
    assert p["expected_final_cycle_changed_raw_bytes"]==2
    assert p["manual_original_SYID_header_edits"]==0
    assert p["upstream_product_modified"] is False
    assert p["native_microsoft_publisher_acceptance"]=="NOT_EVALUATED"
    assert p["raw_PUB_archive_artifact_export_authorized"] is False

    report=json.loads((out/"report.json").read_text(encoding="utf-8"))
    records=json.loads((out/"records.json").read_text(encoding="utf-8"))
    assert set(report)=={"schema","plan_sha256","records","summary",
                        "raw_PUB_archive_artifact_export_authorized",
                        "native_microsoft_publisher_acceptance"}
    assert report["schema"]=="sk1.cfb-exp-pub-t-993.report.v1"
    assert report["plan_sha256"]==hashlib.sha256((out/"plan.json").read_bytes()).hexdigest()
    assert report["records"]==records and len(records)==1
    assert report["raw_PUB_archive_artifact_export_authorized"] is False
    assert report["native_microsoft_publisher_acceptance"]=="NOT_EVALUATED"
    row=records[0]
    assert set(row)=={"source_sha256","source_bytes","package_key",
                     "source_package_status","source_package_archive_sha256",
                     "status","probe"}
    assert row["source_sha256"]==run.ORIGINAL_SHA
    assert row["source_bytes"]==run.ORIGINAL_SIZE
    assert row["package_key"]==run.ORIGINAL_PACKAGE_KEY
    assert row["source_package_status"] in {
        "VERIFIED","ARCHIVE_UNAVAILABLE","ARCHIVE_INVALID","MEMBERS_DRIFT","SOURCE_BYTES_DRIFT"}
    sources,members=source.frozen_training(rar2)
    pkg=next(z for z in sources if z["key"]=="publisher2007_sbs")
    assert len(pkg["files"])==13
    high=next(x for x in pkg["files"] if x["sha256"]==run.ORIGINAL_SHA)
    assert high["size"]==471552
    originals=sorted(stage.glob("*.pub"))
    if row["source_package_status"]=="VERIFIED":
        assert len(originals)==13
        assert {x.stem for x in originals}=={r["sha256"] for r in pkg["files"]}
        for candidate in originals:
            expected=next(x for x in pkg["files"] if x["sha256"]==candidate.stem)
            assert candidate.stat().st_size==expected["size"]
            assert hashlib.sha256(candidate.read_bytes()).hexdigest()==candidate.stem
        assert isinstance(row["source_package_archive_sha256"],str)
        assert len(row["source_package_archive_sha256"])==64
        assert set(row["source_package_archive_sha256"])<=set("0123456789abcdef")
    else:
        assert row["source_package_archive_sha256"] is None
        assert originals==[]
        assert row["status"]=="SOURCE_ARCHIVE_UNAVAILABLE" and row["probe"] is None
    assert row["status"] in {"SOURCE_ARCHIVE_UNAVAILABLE","SOURCE_PROBE_UNAVAILABLE",
                              "SOURCE_EDITOR_OPEN_BLOCKED","NO_ELIGIBLE_STORIES","EVALUATED"}
    if row["source_package_status"]=="VERIFIED":
        assert row["status"]!="SOURCE_ARCHIVE_UNAVAILABLE"
    receipt=row["probe"]
    if row["status"] in {"SOURCE_ARCHIVE_UNAVAILABLE","SOURCE_PROBE_UNAVAILABLE"}:
        assert receipt is None
    else:
        assert isinstance(receipt,dict) and set(receipt)==PROBE_KEYS
        assert receipt["schema"]==run.SCHEMA
        assert receipt["source_sha256"]==run.ORIGINAL_SHA
        assert receipt["source_bytes"]==471552
        assert (receipt["original_natural_syid"],receipt["source_syid_count"],
                receipt["source_syid_max_live"])==(1009,65,965)
        assert receipt["source_intact"] is True
        assert receipt["status"]==row["status"]
        assert receipt["publisher_native_acceptance"]=="NOT_EVALUATED"
        assert receipt["original_publisher_fe_ff_witness"] is False
        assert receipt["manual_syid_rewrite"] is False
        trials=receipt["candidate_stories"]
        assert isinstance(trials,list) and len(trials)<=3
        if row["status"]=="EVALUATED":assert len(trials)>0
        else:assert not trials
        for ordinal,story in enumerate(trials):
            assert isinstance(story,dict) and set(story)==STORY_KEYS
            assert story["story_ordinal"]==ordinal
            uint(story["story_utf16_length"],2**31)
            assert story["ascii_alphanumeric_count"]>=2
            uint(story["offset_utf16"],2**31)
            assert story["offset_utf16"]<story["story_utf16_length"]
            seq=story["sequence"]
            assert isinstance(seq,dict) and set(seq)==SEQ_KEYS
            cycles=seq["cycles"]
            assert isinstance(cycles,list) and 1<=len(cycles)<=8
            assert seq["source_original_unchanged"] is True
            assert seq["completed_cycles"]==sum(x["status"]=="PASS" for x in cycles)
            assert seq["reached_writer_generated_03ff"] is any(
                x["status"]=="PASS" and x.get("after_delete_header")==1023 for x in cycles)
            assert seq["reached_writer_generated_0401"] is (
                cycles[-1]["status"]=="PASS" and cycles[-1].get("after_delete_header")==1025)
            writes=0
            for position,cycle in enumerate(cycles,1):
                writes+=check_cycle(cycle,legacy,position)
                if position<len(cycles):
                    assert cycle["status"]=="PASS","no subsequent cycle after a guard/counterexample"
            assert seq["completed_writer_materializations"]==writes
            if seq["reached_writer_generated_0401"]:
                assert len(cycles)==8 and cycles[-1]["status"]=="PASS"
                assert cycles[-1]["cycle_raw"]["changed_same_offset_bytes"]==2
                assert cycles[-1]["cycle_cfb"]["quill_changed_bytes_outside_syid_first_dword"]==0
    assert report["summary"]==run.count_summary(records)
    summary=report["summary"]
    assert summary["writer_generated_0401_story_trials"]<=summary["eligible_original_stories"]
    assert summary["writer_generated_03ff_story_trials"]<=summary["eligible_original_stories"]
    assert summary["cycle_8_03ff_to_0401_full_raw_two_bytes"]<=summary["writer_generated_0401_story_trials"]
    assert summary["manual_original_SYID_byte_edits"]==0
    assert summary["native_microsoft_publisher_acceptance"]=="NOT_EVALUATED"
    print("PUB-T-993 independent original 13-member SHA verification and all Writer cycle receipts PASS:")
    print(json.dumps({"source_status":row["status"],
        "eligible_stories":summary["eligible_original_stories"],
        "true_Writer_materializations":summary["writer_actual_materializations"],
        "full_cycles":summary["writer_full_cycle_count"],
        "writer_generated_03ff":summary["writer_generated_03ff_story_trials"],
        "crossed_03ff_to_0401":summary["writer_generated_0401_story_trials"],
        "physical_two_byte_boundary":summary["cycle_8_03ff_to_0401_full_raw_two_bytes"],
        "model_counterexamples":len(summary["model_counterexamples"])
    },sort_keys=True))

if __name__=="__main__":
    assert len(sys.argv)==6,"usage: RESULTS RAR2 REF_T992 ORIGINAL_STAGE REF_T963"
    check(*(Path(x) for x in sys.argv[1:]))
