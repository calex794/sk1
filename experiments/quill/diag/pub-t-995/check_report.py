#!/usr/bin/env python3
"""PUB-T-995 independent frozen-original SHA and numeric Quill ID-set audit.

This checker independently reconstructs all 29 pinned source hashes from
private worker files, verifies them against T992 original receipts and computes
each header/count/max/gap and the fixed A/B pair ID intersection.
"""
from __future__ import annotations
import hashlib,importlib.util,json,subprocess,sys
from collections import Counter,defaultdict
from pathlib import Path

HERE=Path(__file__).resolve().parent
SHA_CHARS=set("0123456789abcdef")
SCAN_KEYS={"source_sha256","source_bytes","status","original_immutable","header",
    "count","max_live","ids","unique_id_count","duplicate_id_count",
    "header_minus_max_live","header_ge_live_max"}
STATUS_CODES={"NATURAL_SYID_PARSED","QUILL_SYID_PARSE_BLOCKED","QUILL_STREAM_UNAVAILABLE","NOT_CFB"}
PAIR_FIELDS={"source_a_header","source_b_header","header_delta_b_minus_a",
    "source_a_max_live","source_b_max_live","max_live_delta_b_minus_a",
    "source_a_live_count","source_b_live_count","source_a_distinct_live_count",
    "source_b_distinct_live_count","shared_distinct_ids","a_only_distinct_ids",
    "b_only_distinct_ids","same_ordinal_id_count","source_a_header_live_gap",
    "source_b_header_live_gap"}
def sha(data):return hashlib.sha256(data).hexdigest()
def sha_file(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def mod(path,name):
    sp=importlib.util.spec_from_file_location(name,path)
    assert sp and sp.loader
    x=importlib.util.module_from_spec(sp);sp.loader.exec_module(x);return x
def git(path,*args):
    return subprocess.check_output(["git",*args],cwd=path,text=True).strip()
def uint32(n):
    assert type(n) is int and 0<=n<=0xffffffff
def count(rows):
    states=Counter(r["status"] for r in rows)
    parsed=[r for r in rows if r["status"]=="NATURAL_SYID_PARSED"]
    gaps=Counter(r["header_minus_max_live"] for r in parsed if r["max_live"] is not None)
    return {
       "original_SHA_verified":len(rows),
       "original_Quill_parsed":len(parsed),
       "quill_status":dict(sorted(states.items())),
       "parsed_with_header_ge_max_live":sum(r["header_ge_live_max"] is True for r in parsed),
       "parsed_with_header_lt_max_live":sum(r["header_ge_live_max"] is False for r in parsed),
       "parsed_with_duplicate_live_ids":sum(r["duplicate_id_count"]>0 for r in parsed),
       "numeric_header_gap_distribution":dict(sorted((str(k),v) for k,v in gaps.items())),
       "total_current_live_ids":sum(r["count"] for r in parsed),
       "max_natural_header":max((r["header"] for r in parsed),default=None),
       "max_natural_gap":max((r["header_minus_max_live"] for r in parsed
                             if r["header_minus_max_live"] is not None),default=None),
       "sources_in_original_rar_1556":29,
       "original_source_bytes_exported":False,
       "writer_run":False,
       "native_microsoft_publisher_saveas":"NOT_EVALUATED"
    }
def pair(a,b):
    assert a["status"]==b["status"]=="NATURAL_SYID_PARSED"
    av=a["ids"];bv=b["ids"]
    aa=set(av);bb=set(bv)
    return {
        "source_a_header":a["header"],"source_b_header":b["header"],
        "header_delta_b_minus_a":b["header"]-a["header"],
        "source_a_max_live":a["max_live"],"source_b_max_live":b["max_live"],
        "max_live_delta_b_minus_a":b["max_live"]-a["max_live"],
        "source_a_live_count":len(av),"source_b_live_count":len(bv),
        "source_a_distinct_live_count":len(aa),"source_b_distinct_live_count":len(bb),
        "shared_distinct_ids":len(aa&bb),
        "a_only_distinct_ids":len(aa-bb),"b_only_distinct_ids":len(bb-aa),
        "same_ordinal_id_count":sum(u==v for u,v in zip(av,bv)),
        "source_a_header_live_gap":a["header"]-a["max_live"],
        "source_b_header_live_gap":b["header"]-b["max_live"]
    }
def check(out:Path,stage:Path,rar2:Path,t992:Path,t992safe:Path):
    out=out.resolve(strict=True);stage=stage.resolve(strict=True)
    rar2=rar2.resolve(strict=True);t992=t992.resolve(strict=True)
    t992safe=t992safe.resolve(strict=True)
    assert {p.name for p in out.iterdir()}=={"plan.json","records.json","report.json"}
    run=mod(HERE/"run.py","source_retriever_t995")
    src=mod(t992/"experiments/cfb/diag/pub-t-992/run.py","pinned_t992")
    assert git(rar2,"rev-parse","HEAD")==run.RAR2_PIN
    assert git(t992,"rev-parse","HEAD")==run.SCIENCE_T992
    plan=json.loads((out/"plan.json").read_text())
    assert set(plan)=={
       "schema","rar2_pin","source_t992_science_pin",
       "original_training_29_sha_lf_digest","t992_source_safe_archive_sha",
       "all_original_source_sha","original_archive_member_observations",
       "frozen_pair_sha","original_pair_expected_headers",
       "original_pair_expected_count","original_pair_expected_max_live",
       "all_numeric_SYID_ids_safe","original_pub_bytes_artifact_export",
       "writer_run","native_microsoft_publisher_saveas"}
    assert plan["schema"]=="sk1.quill-diag-pub-t-995.plan.v1"
    assert plan["rar2_pin"]==run.RAR2_PIN
    assert plan["source_t992_science_pin"]==run.SCIENCE_T992
    assert plan["original_training_29_sha_lf_digest"]==run.TRAINING_DIGEST
    assert plan["t992_source_safe_archive_sha"]==run.T992_SOURCE_SAFE_ARCHIVE_SHA
    assert (plan["all_original_source_sha"],plan["original_archive_member_observations"])==(29,33)
    assert plan["frozen_pair_sha"]==[run.ORIGINAL_A,run.ORIGINAL_B]
    assert plan["original_pair_expected_headers"]==[1009,1027]
    assert plan["original_pair_expected_count"]==[65,65]
    assert plan["original_pair_expected_max_live"]==[965,1020]
    assert plan["all_numeric_SYID_ids_safe"] is True
    assert plan["original_pub_bytes_artifact_export"] is False
    assert plan["writer_run"] is False
    assert plan["native_microsoft_publisher_saveas"]=="NOT_EVALUATED"
    rows=json.loads((out/"records.json").read_text())
    report=json.loads((out/"report.json").read_text())
    assert set(report)=={"schema","plan_sha256","rows","pair","summary",
                       "original_pub_bytes_artifact_export","writer_run",
                       "native_microsoft_publisher_saveas"}
    assert report["schema"]=="sk1.quill-diag-pub-t-995.report.v1"
    assert report["plan_sha256"]==sha((out/"plan.json").read_bytes())
    assert report["rows"]==rows
    assert report["original_pub_bytes_artifact_export"] is False
    assert report["writer_run"] is False
    assert report["native_microsoft_publisher_saveas"]=="NOT_EVALUATED"
    assert isinstance(rows,list) and len(rows)==29
    packages,entry=src.frozen_training(rar2)
    frozen={v["sha256"]:v for _,v in entry}
    assert len(frozen)==29
    assert src.canonical_shas(frozen)==run.TRAINING_DIGEST
    old_records=json.loads((t992safe/"records.json").read_text())
    old_plan=json.loads((t992safe/"plan.json").read_text())
    old_report=json.loads((t992safe/"report.json").read_text())
    assert len(old_records)==29 and old_report["records"]==old_records
    assert old_report["plan_sha256"]==sha((t992safe/"plan.json").read_bytes())
    assert old_plan["original_training_29_sha_lf_digest"]==run.TRAINING_DIGEST
    old={r["source_sha256"]:r for r in old_records}
    assert set(old)==set(frozen)
    # Confirm each hash from actual original .pub bytes and exact initial T720 manifest.
    originals=list(stage.iterdir())
    assert len(originals)==29 and all(x.is_file() and x.suffix==".pub" for x in originals)
    assert {x.stem for x in originals}==set(frozen)
    for x in originals:
        assert sha_file(x)==x.stem
        assert x.stat().st_size==frozen[x.stem]["size"]
        assert x.read_bytes()[:8]==bytes.fromhex("d0cf11e0a1b11ae1")
    assert [r["source_sha256"] for r in rows]==sorted(frozen)
    for r in rows:
        assert type(r) is dict and set(r)==SCAN_KEYS
        key=r["source_sha256"]
        assert len(key)==64 and set(key)<=SHA_CHARS
        assert r["source_bytes"]==frozen[key]["size"]
        assert r["original_immutable"] is True
        assert r["status"] in STATUS_CODES
        original=old[key]["quill"]
        assert original["source_sha256"]==key
        assert r["status"]==original["status"]
        if r["status"]!="NATURAL_SYID_PARSED":
            for f in ("header","count","max_live","ids","unique_id_count",
                      "duplicate_id_count","header_minus_max_live","header_ge_live_max"):
                assert r[f] is None
            continue
        ids=r["ids"];h=r["header"];n=r["count"]
        assert type(ids) is list and type(n) is int and n==len(ids)
        assert type(h) is int
        uint32(h);uint32(n)
        for v in ids:uint32(v)
        assert r["max_live"]==(max(ids) if ids else None)
        assert r["unique_id_count"]==len(set(ids))
        assert r["duplicate_id_count"]==n-len(set(ids))
        if ids:
            assert r["header_minus_max_live"]==h-max(ids)
            assert r["header_ge_live_max"] is (h>=max(ids))
        else:
            assert r["header_minus_max_live"] is None
            assert r["header_ge_live_max"] is None
        assert (h,n,r["max_live"])==(
            original["syid_header"],original["syid_count"],original["syid_max_live"])
    by_sha={r["source_sha256"]:r for r in rows}
    expected_pair=pair(by_sha[run.ORIGINAL_A],by_sha[run.ORIGINAL_B])
    observed=report["pair"]
    assert set(observed)=={"source_a_sha256","source_b_sha256","both_parsed","comparison"}
    assert observed["source_a_sha256"]==run.ORIGINAL_A
    assert observed["source_b_sha256"]==run.ORIGINAL_B
    assert observed["both_parsed"] is True
    assert set(observed["comparison"])==PAIR_FIELDS
    assert observed["comparison"]==expected_pair
    assert report["summary"]==count(rows)
    assert report["summary"]["original_Quill_parsed"]==28
    print("PUB-T-995 independently rehashed exact 29 native training PUB and original live-ID vectors:")
    print(json.dumps({
       "original_SHA_verified":len(rows),
       "quill_parsed":report["summary"]["original_Quill_parsed"],
       "header_invariant_violations":report["summary"]["parsed_with_header_lt_max_live"],
       "duplicate_ID_sources":report["summary"]["parsed_with_duplicate_live_ids"],
       "pair":observed["comparison"]
    },sort_keys=True))
if __name__=="__main__":
    assert len(sys.argv)==6,"usage: RESULTS SOURCE_STAGE RAR2 REFT992 REFT992_SAFEREPORT"
    check(*(Path(s) for s in sys.argv[1:]))
