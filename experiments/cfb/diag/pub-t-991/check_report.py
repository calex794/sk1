#!/usr/bin/env python3
"""PUB-T-991 independent 27-path SHA, git-blob, 625/1556 overlap, full Writer receipt audit.
The science can return zero FE/FF original witnesses: that is a bounded result.
"""
from __future__ import annotations
import hashlib,importlib.util,json,subprocess,sys
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
RECORD_KEYS={
 "category","source_sha256","source_bytes","source_git_blob_sha1",
 "poi_manifest_verified","duplicate_within_batch","overlap_625",
 "overlap_rar_1556","census","writer"}
CENSUS_KEYS={
 "source_sha256","source_bytes","status","syid_header",
 "syid_count","syid_max_live","low_byte","is_fe_ff_boundary",
 "original_bytes_immutable"}
WRITER_STATUS={
 "SOURCE_SHA_DRIFT","WRITER_PROCESS_UNAVAILABLE","WRITER_PROCESS_FAILED",
 "WRITER_RECEIPT_UNREADABLE","WRITER_RECEIPT_INVALID",
 "WRITER_SOURCE_SYID_DRIFT","RECEIPT_AVAILABLE"}
STORY_KEYS={"story_ordinal","story_utf16_length","ascii_total","pairs"}
PAIR_KEYS={
 "slot","ascii_rank","ascii_total","offset_utf16","story_utf16_length",
 "ambiguous_reverse_delete_insert_offset","single_insert","single_delete",
 "both_single_pass","insert_then_delete","delete_then_insert",
 "insert_delete_returns_original_bytes","delete_insert_returns_original_bytes",
 "both_final_byte_equal","insert_delete_cfb","delete_insert_cfb",
 "insert_delete_raw","delete_insert_raw"}
RAW_KEYS={"source_file_length","final_file_length","equal_length",
          "changed_same_offset_bytes","extra_bytes","whole_file_equal"}
SAFE_STATES={"NATURAL_SYID_PARSED","QUILL_STREAM_UNAVAILABLE",
             "QUILL_SYID_PARSE_BLOCKED","NOT_CFB"}
SHA_CHARS=set("0123456789abcdef")
def mod(path,name):
    sp=importlib.util.spec_from_file_location(name,path)
    assert sp and sp.loader
    m=importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m
def git(root,*args):
    return subprocess.check_output(["git",*args],cwd=root,text=True).strip()
def ssha(data):return hashlib.sha256(data).hexdigest()
def u32(x):
    assert type(x) is int and 0<=x<=0xffffffff
def sha_str(x):
    assert isinstance(x,str) and len(x)==64 and set(x)<=SHA_CHARS
def diff4(a,b):
    return sum(x!=y for x,y in zip(a.to_bytes(4,"little"),b.to_bytes(4,"little")))
def check_raw(r):
    assert isinstance(r,dict) and set(r)==RAW_KEYS
    for k in ("source_file_length","final_file_length","changed_same_offset_bytes","extra_bytes"):
        assert type(r[k]) is int and 0<=r[k]<=256*1024*1024
    assert type(r["equal_length"]) is type(r["whole_file_equal"]) is bool
    assert r["equal_length"]==(r["source_file_length"]==r["final_file_length"])
    assert r["extra_bytes"]==abs(r["source_file_length"]-r["final_file_length"])
    assert r["whole_file_equal"]==(r["equal_length"] and r["changed_same_offset_bytes"]==0)
    assert r["changed_same_offset_bytes"]<=min(r["source_file_length"],r["final_file_length"])

def check_writer(probe,source,legacy):
    if probe is None:return
    assert isinstance(probe,dict) and set(probe)=={"status","probe"}
    assert probe["status"] in WRITER_STATUS
    if probe["status"]!="RECEIPT_AVAILABLE":
        assert probe["probe"] is None
        return
    p=probe["probe"]
    assert isinstance(p,dict)
    assert p["schema"]=="sk1.cfb-diag-pub-t-984.inverse.v1"
    assert p["source_sha256"]==source["source_sha256"]
    assert p["source_bytes"]==source["source_bytes"]
    assert p["publisher_native_acceptance"]=="NOT_EVALUATED"
    assert p["product_pub_download_authorized"] is False
    assert p["result"] in {"EVALUATED","NO_PLAIN_EDITABLE_STORY",
                            "SOURCE_QUILL_PARSE_BLOCKED","SOURCE_EDITOR_OPEN_BLOCKED"}
    # The Writer receipt's original header must match the source-only census.
    if p.get("source_syid_first_dword") is not None:
        assert p["source_syid_first_dword"]==source["census"]["syid_header"]
        assert p["source_syid_count"]==source["census"]["syid_count"]
        assert p["source_syid_max_live_id"]==source["census"]["syid_max_live"]
    if p["result"]!="EVALUATED":
        assert p["stories"]==[]
        return
    assert len(p["stories"]) in (1,2,3)
    for ordinal,story in enumerate(p["stories"]):
        assert isinstance(story,dict) and set(story)==STORY_KEYS
        assert story["story_ordinal"]==ordinal
        assert type(story["ascii_total"]) is int and story["ascii_total"]>=2
        assert type(story["story_utf16_length"]) is int and story["story_utf16_length"]>1
        assert isinstance(story["pairs"],list) and len(story["pairs"])==1
        pair=story["pairs"][0]
        assert set(pair)==PAIR_KEYS
        assert pair["slot"]=="second" and pair["ascii_rank"]==1
        assert pair["ascii_total"]==story["ascii_total"]
        assert pair["story_utf16_length"]==story["story_utf16_length"]
        assert type(pair["offset_utf16"]) is int and 0<=pair["offset_utf16"]<story["story_utf16_length"]
        assert type(pair["ambiguous_reverse_delete_insert_offset"]) is bool
        for k in ("single_insert","single_delete"):legacy.check_step(pair[k])
        both=pair["single_insert"]["status"]==pair["single_delete"]["status"]=="HOSTED_PASS"
        assert pair["both_single_pass"] is both
        if not both:
            assert pair["insert_then_delete"]=={"status":"NOT_EVALUATED_BASELINE_NOT_BOTH_PASS"}
            assert pair["delete_then_insert"]=={"status":"NOT_EVALUATED_BASELINE_NOT_BOTH_PASS"}
            for k in ("insert_delete_cfb","delete_insert_cfb","insert_delete_raw",
                       "delete_insert_raw","insert_delete_returns_original_bytes",
                       "delete_insert_returns_original_bytes","both_final_byte_equal"):
                assert pair[k] is None
            continue
        complete=0
        for arm,key in (("insert_then_delete","insert_delete"),
                        ("delete_then_insert","delete_insert")):
            step=pair[arm]
            legacy.check_step(step)
            raw=pair[key+"_raw"];cfb=pair[key+"_cfb"]
            if step["status"]!="HOSTED_PASS":
                assert raw is None and cfb is None and pair[key+"_returns_original_bytes"] is None
                continue
            complete+=1
            check_raw(raw)
            assert raw["source_file_length"]==source["source_bytes"]
            assert isinstance(cfb,dict)
            d=cfb.copy()
            assert d["schema"]=="sk1.cfb-diag-pub-t-984.diff.v1"
            d["schema"]="sk1.cfb-diag-pub-t-963.diff.v1"
            legacy.check_diff(d)
            assert cfb["source_syid_first_dword"]==source["census"]["syid_header"]
            assert cfb["source_file_bytes"]==source["source_bytes"]
            assert cfb["final_file_bytes"]==raw["final_file_length"]
            assert type(pair[key+"_returns_original_bytes"]) is bool
            assert pair[key+"_returns_original_bytes"] is raw["whole_file_equal"]
            old=source["census"]["syid_header"]
            n=diff4(old,old+2) if old<=0xfffffffd else None
            assert n is None or 1<=n<=4
        if complete==2:assert type(pair["both_final_byte_equal"]) is bool
        else: assert pair["both_final_byte_equal"] is None

def check(result:Path,poi:Path,aspose:Path,filefmt:Path,
          lalamu:Path,rar2:Path,ref963:Path):
    result=result.resolve(strict=True)
    poi=poi.resolve(strict=True)
    aspose=aspose.resolve(strict=True)
    filefmt=filefmt.resolve(strict=True)
    lalamu=lalamu.resolve(strict=True)
    rar2=rar2.resolve(strict=True)
    ref963=ref963.resolve(strict=True)
    run=mod(HERE/"run.py","source_pinned_991")
    legacy=mod(ref963/"experiments/cfb/val/pub-t-963/check_report.py","original_check_t963")
    assert {p.name for p in result.iterdir()}=={"plan.json","records.json","report.json"}
    plan=json.loads((result/"plan.json").read_text())
    report=json.loads((result/"report.json").read_text())
    rows=json.loads((result/"records.json").read_text())
    assert set(plan)=={
      "schema","sources","all_source_paths","original_quill_scanner_from_t987",
      "original_writer_from_t984","original_t963_helper","original_t971_source_selector",
      "upstream_pub_writer","previous_625_donor","previous_625_tree",
      "previous_full_rar_authority_count","source_immutable",
      "writer_only_on_sha_disjoint_natural_FE_FF","synthetic_SYID_header_patch",
      "native_publisher_saveas","source_bytes_artifact_exported"}
    assert plan["schema"]=="sk1.cfb-diag-pub-t-991.plan.v1"
    assert plan["sources"]==[
        {"category":"apache_poi","commit":run.POI_PIN,"tree":run.POI_TREE,"count":21},
        {"category":"aspose_dotnet","commit":run.ASPOSE_PIN,"count":5},
        {"category":"file_format","commit":run.FILE_FORMAT_PIN,"count":1}]
    assert plan["all_source_paths"]==27
    assert plan["original_quill_scanner_from_t987"]==run.T987_PIN
    assert plan["original_writer_from_t984"]==run.T984_PIN
    assert plan["original_t963_helper"]==run.T963_PIN
    assert plan["original_t971_source_selector"]==run.T971_PIN
    assert plan["upstream_pub_writer"]==run.RAR2_PIN
    assert plan["previous_625_donor"]==run.LALAMU_PIN
    assert plan["previous_625_tree"]==run.LALAMU_TREE
    assert plan["previous_full_rar_authority_count"]==1556
    assert plan["source_immutable"] is True
    assert plan["writer_only_on_sha_disjoint_natural_FE_FF"] is True
    assert plan["synthetic_SYID_header_patch"] is False
    assert plan["native_publisher_saveas"]=="NOT_EVALUATED"
    assert plan["source_bytes_artifact_exported"] is False
    assert len(rows)==27
    assert set(report)=={"schema","plan_sha256","summary","records",
                         "source_bytes_artifact_exported","native_publisher_saveas"}
    assert report["schema"]=="sk1.cfb-diag-pub-t-991.report.v1"
    assert report["plan_sha256"]==ssha((result/"plan.json").read_bytes())
    assert report["records"]==rows
    assert report["source_bytes_artifact_exported"] is False
    assert report["native_publisher_saveas"]=="NOT_EVALUATED"

    for root,pin in [(poi,run.POI_PIN),(aspose,run.ASPOSE_PIN),
                     (filefmt,run.FILE_FORMAT_PIN),(lalamu,run.LALAMU_PIN),
                     (rar2,run.RAR2_PIN),(ref963,run.T963_PIN)]:
        assert git(root,"rev-parse","HEAD")==pin
    assert git(poi,"rev-parse","HEAD:test-data/publisher")==run.POI_TREE
    assert git(lalamu,"rev-parse","HEAD:pub-corpus/corpus/native/unclassified")==run.LALAMU_TREE
    prior={f.stem for f in (lalamu/"pub-corpus/corpus/native/unclassified").glob("*.pub")}
    assert len(prior)==625
    rar_sha={s for s in (rar2/"tools/corpus/receipts/current-rar-1556.sha256.txt").read_text().split()
             if len(s)==64 and set(s)<=SHA_CHARS}
    assert len(rar_sha)==1556
    original_poi=run.read_poi_manifest(rar2)
    seen=set()
    all_orig=run.source_paths(poi,aspose,filefmt)
    assert len(all_orig)==len(rows)==27
    for (category,root,relative),entry in zip(all_orig,rows):
        assert isinstance(entry,dict) and set(entry)==RECORD_KEYS
        source=root/relative
        raw=source.read_bytes()
        blob=git(root,"rev-parse","HEAD:"+relative)
        assert git(root,"hash-object",str(source))==blob
        val=ssha(raw);sha_str(val)
        assert entry["category"]==category
        assert entry["source_sha256"]==val
        assert entry["source_git_blob_sha1"]==blob
        assert entry["source_bytes"]==len(raw)
        assert entry["duplicate_within_batch"] is (val in seen)
        assert entry["overlap_625"] is (val in prior)
        assert entry["overlap_rar_1556"] is (val in rar_sha)
        if category=="apache_poi":
            assert entry["poi_manifest_verified"] is True
            assert original_poi[source.name]["sha256"]==val
            assert original_poi[source.name]["byte_len"]==len(raw)
        else:assert entry["poi_manifest_verified"] is None
        c=entry["census"]
        assert isinstance(c,dict) and set(c)==CENSUS_KEYS
        assert c["source_sha256"]==val and c["source_bytes"]==len(raw)
        assert c["original_bytes_immutable"] is True
        assert c["status"] in SAFE_STATES
        if c["status"]=="NATURAL_SYID_PARSED":
            u32(c["syid_header"]);u32(c["syid_count"])
            assert c["syid_max_live"] is None or (
                type(c["syid_max_live"]) is int and 0<=c["syid_max_live"]<=0xffffffff)
            assert type(c["low_byte"]) is int and c["low_byte"]==c["syid_header"]&255
            assert c["is_fe_ff_boundary"] is (c["low_byte"] in (254,255))
        else:
            assert all(c[k] is None for k in ("syid_header","syid_count",
                        "syid_max_live","low_byte"))
            assert c["is_fe_ff_boundary"] is False
        eligible=(val not in seen and val not in prior
                and c["status"]=="NATURAL_SYID_PARSED"
                and c["is_fe_ff_boundary"])
        if eligible:assert entry["writer"] is not None
        else:assert entry["writer"] is None
        check_writer(entry["writer"],entry,legacy)
        seen.add(val)
    assert report["summary"]==run.summarize(rows),"independent report summary mismatch"
    sm=report["summary"]
    assert sm["source_paths"]==27
    print("PUB-T-991 independent pinned-27 exact SHA, original Quill census, Writer & full CFB receipt checks:")
    print(json.dumps({
      "unique_SHA":len(seen),
      "outside_625":sm["overlap_census"].get("outside_625_unique_sha",0),
      "quill":sm["distinct_non625_original_syid_parsed"],
      "new_natural_FE_FF":sm["distinct_non625_original_low_FE_FF"],
      "writer_finals":sm["writer_inverse_materialized_final_files"],
      "raw_syid_only":sm["writer_inverse_exact_only_syid_plus_2"],
      "physical_counterexamples":len(sm["writer_inverse_physical_counterexamples"])
    },sort_keys=True))

if __name__=="__main__":
    assert len(sys.argv)==8, "usage: RESULT POI ASPOSE FILE_FORMAT LALAMU RAR2 REF_T963"
    check(*(Path(p) for p in sys.argv[1:]))
