#!/usr/bin/env python3
"""PUB-T-992 independent receipt admission of immutable 29-source T720 originals.

A package unavailable or Quill unparseable is NOT a zero FE/FF witness.
Scientific model may be falsified by a legitimate Writer final; do not force
our physical SYID-only hypothesis to pass as an assert.
"""
from __future__ import annotations
from collections import Counter,defaultdict
import hashlib,importlib.util,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
SHA_CHARS=set("0123456789abcdef")
RAW_QUILL_KEYS={"source_sha256","source_bytes","status","syid_header","syid_count",
   "syid_max_live","low_byte","is_fe_ff_boundary","original_bytes_immutable"}
REC_KEYS={"source_sha256","package_key","source_member_occurrence_count",
   "expected_source_bytes","source_admission_status","source_archive_sha256",
   "overlap_625","overlap_991","member_rar_1556","quill","writer"}
PACKAGE_CODES={"VERIFIED","ARCHIVE_UNAVAILABLE","ARCHIVE_INVALID","MEMBERS_DRIFT",
               "SOURCE_BYTES_DRIFT"}
SCAN_STATES={"NATURAL_SYID_PARSED","QUILL_STREAM_UNAVAILABLE",
             "QUILL_SYID_PARSE_BLOCKED","NOT_CFB"}
def m(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    assert spec and spec.loader
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);return v
def sha(data):return hashlib.sha256(data).hexdigest()
def source_sha(x):
    assert isinstance(x,str) and len(x)==64 and set(x)<=SHA_CHARS
def u32(v):
    assert type(v) is int and 0<=v<=0xffffffff
def git(repo,*args):
    return subprocess.check_output(["git",*args],cwd=repo,text=True).strip()
def check(out,rar2,donor,ref987,ref991safe,ref991checker,ref963):
    for ref in (out,rar2,donor,ref987,ref991safe,ref991checker,ref963):
        assert ref.is_dir()
    rar2=rar2.resolve(strict=True);donor=donor.resolve(strict=True)
    ref987=ref987.resolve(strict=True);ref991safe=ref991safe.resolve(strict=True)
    ref991checker=ref991checker.resolve(strict=True);ref963=ref963.resolve(strict=True)
    out=out.resolve(strict=True)
    assert {f.name for f in out.iterdir()}=={"plan.json","records.json","report.json"}
    run=m(HERE/"run.py","registered_t992")
    t991=m(ref991checker/"experiments/cfb/diag/pub-t-991/check_report.py","scientific_991_audit")
    legacy=m(ref963/"experiments/cfb/val/pub-t-963/check_report.py","pinned_963_audit")
    assert git(rar2,"rev-parse","HEAD")==run.RAR_PIN
    assert git(donor,"rev-parse","HEAD")==run.DONOR_PIN
    assert git(donor,"rev-parse","HEAD:pub-corpus/corpus/native/unclassified")==run.DONOR_TREE
    assert git(ref987,"rev-parse","HEAD")==run.T987_PIN
    assert git(ref991checker,"rev-parse","HEAD")=="42fa771a4640207d2d615d6f09f6a3bbd4fc6d6c"
    assert git(ref963,"rev-parse","HEAD")==run.T963_PIN
    plan=json.loads((out/"plan.json").read_text(encoding="utf-8"))
    assert set(plan)=={
      "schema","source_rar2_git_pin","training_spec_path",
      "original_training_29_sha_lf_digest","package_order",
      "package_observation_counts","package_unique_sha_counts",
      "expected_member_observations","expected_sha_distinct",
      "prior_625_commit","prior_625_tree",
      "prior_991_27_source_sha_lf_digest","prior_991_source_safe_artifact_sha256",
      "pinned_original_reader_T987","pinned_real_writer_T984",
      "pinned_writer_helpers_T963","pinned_writer_sources_T971",
      "upstream_product_code_unchanged",
      "native_microsoft_publisher_acceptance","original_PUB_bytes_exported"}
    assert plan["schema"]=="sk1.cfb-diag-pub-t-992.plan.v1"
    assert plan["source_rar2_git_pin"]==run.RAR_PIN
    assert plan["training_spec_path"]=="tools/corpus/receipts/version-labelled-training-29-input-2026-09-25.json"
    assert plan["original_training_29_sha_lf_digest"]==run.TRAINING_SHA_DIGEST
    assert plan["package_order"]==list(run.PACKAGE_KEYS)
    assert plan["package_observation_counts"]==list(run.PACKAGE_ROWS)
    assert plan["package_unique_sha_counts"]==list(run.PACKAGE_UNIQUE)
    assert (plan["expected_member_observations"],plan["expected_sha_distinct"])==(33,29)
    assert (plan["prior_625_commit"],plan["prior_625_tree"])==(run.DONOR_PIN,run.DONOR_TREE)
    assert plan["prior_991_27_source_sha_lf_digest"]==run.T991_SHA_DIGEST
    assert plan["prior_991_source_safe_artifact_sha256"]==run.T991_ARTIFACT_SHA
    assert plan["pinned_original_reader_T987"]==run.T987_PIN
    assert plan["pinned_real_writer_T984"]==run.T984_PIN
    assert plan["pinned_writer_helpers_T963"]==run.T963_PIN
    assert plan["pinned_writer_sources_T971"]==run.T971_PIN
    assert plan["upstream_product_code_unchanged"] is True
    assert plan["original_PUB_bytes_exported"] is False
    assert plan["native_microsoft_publisher_acceptance"]=="NOT_EVALUATED"
    all_packages,inputs=run.frozen_training(rar2)
    # The complete same before/after 625/991/1556 population is independently
    # reread by our own Python rather than trusting package receipt fields.
    prior625={f.stem for f in (donor/"pub-corpus/corpus/native/unclassified").glob("*.pub")}
    assert len(prior625)==625
    prior991=json.loads((ref991safe/"records.json").read_text(encoding="utf-8"))
    assert len(prior991)==27
    shas991={r["source_sha256"] for r in prior991}
    assert len(shas991)==27 and run.canonical_shas(shas991)==run.T991_SHA_DIGEST
    authority={x for x in (rar2/"tools/corpus/receipts/current-rar-1556.sha256.txt").read_text().splitlines() if x.strip()}
    assert len(authority)==1556
    # Ref-T991 artifact also authenticates the exact SHA-set independent of input.
    prior991report=json.loads((ref991safe/"report.json").read_text())
    assert prior991report["records"]==prior991
    assert prior991report["source_bytes_artifact_exported"] is False
    assert prior991report["summary"]["source_paths"]==27
    expected=defaultdict(list)
    for key,entry in inputs:expected[entry["sha256"]].append((key,entry))
    assert len(expected)==29
    assert set(expected).isdisjoint(prior625)
    assert set(expected).isdisjoint(shas991)
    assert set(expected).issubset(authority)
    rows=json.loads((out/"records.json").read_text(encoding="utf-8"))
    report=json.loads((out/"report.json").read_text(encoding="utf-8"))
    assert set(report)=={
      "schema","plan_sha256","summary","records",
      "original_PUB_bytes_exported","native_microsoft_publisher_acceptance"}
    assert report["schema"]=="sk1.cfb-diag-pub-t-992.report.v1"
    assert report["plan_sha256"]==sha((out/"plan.json").read_bytes())
    assert report["records"]==rows and len(rows)==29
    assert report["original_PUB_bytes_exported"] is False
    assert report["native_microsoft_publisher_acceptance"]=="NOT_EVALUATED"
    assert [r["source_sha256"] for r in rows]==sorted(expected)
    by_pack=defaultdict(list)
    parsed=[];high=[];fe=[];admitted=[]
    for record in rows:
        assert isinstance(record,dict) and set(record)==REC_KEYS
        origin=record["source_sha256"]
        source_sha(origin)
        spec=expected[origin]
        assert len({s[0] for s in spec})==1
        key=spec[0][0]
        assert key==record["package_key"]
        assert key in run.PACKAGE_KEYS
        assert record["source_member_occurrence_count"]==len(spec)
        assert type(record["expected_source_bytes"]) is int
        assert 0<record["expected_source_bytes"]<=run.MAX_MEMBER_BYTES
        assert all(x[1]["size"]==record["expected_source_bytes"] for x in spec)
        assert record["source_admission_status"] in PACKAGE_CODES
        assert record["overlap_625"] is False and origin not in prior625
        assert record["overlap_991"] is False and origin not in shas991
        assert record["member_rar_1556"] is True and origin in authority
        if record["source_admission_status"]=="VERIFIED":
            source_sha(record["source_archive_sha256"])
            assert record["quill"] is not None
            admitted.append(origin)
        else:
            assert record["source_archive_sha256"] is None
            assert record["quill"] is None
            assert record["writer"] is None
        by_pack[key].append(record)
        q=record["quill"]
        if q is None:continue
        assert isinstance(q,dict) and set(q)==RAW_QUILL_KEYS
        assert q["source_sha256"]==origin
        assert q["source_bytes"]==record["expected_source_bytes"]
        assert q["original_bytes_immutable"] is True
        assert q["status"] in SCAN_STATES
        if q["status"]!="NATURAL_SYID_PARSED":
            assert all(q[k] is None for k in
                       ("syid_header","syid_count","syid_max_live","low_byte"))
            assert q["is_fe_ff_boundary"] is False
            assert record["writer"] is None
            continue
        parsed.append(record)
        u32(q["syid_header"]);u32(q["syid_count"])
        if q["syid_max_live"] is not None:u32(q["syid_max_live"])
        assert type(q["low_byte"]) is int and q["low_byte"]==(q["syid_header"]&0xff)
        assert q["is_fe_ff_boundary"] is (q["low_byte"] in (0xfe,0xff))
        if q["syid_header"]>=254:high.append(record)
        if q["is_fe_ff_boundary"]:
            fe.append(record)
            # Reuse independently proven complete T991 per-story Writer
            # receipts (including frozen T963 step+CFB validators).
            assert record["writer"] is not None
            t991.check_writer(record["writer"],{
               "source_sha256":origin,
               "source_bytes":record["expected_source_bytes"],
               "census":q
            },legacy)
        else:
            assert record["writer"] is None
    assert set(by_pack)==set(run.PACKAGE_KEYS)
    package_status={}
    for p in all_packages:
        a=by_pack[p["key"]]
        assert len(a)==p["expected_unique_sha_count"]
        statuses={r["source_admission_status"] for r in a}
        assert len(statuses)==1
        package_status[p["key"]]=next(iter(statuses))
        if package_status[p["key"]]=="VERIFIED":
            assert len({r["source_archive_sha256"] for r in a})==1
    assert report["summary"]==run.summary(rows,package_status)
    summary=report["summary"]
    assert summary["planned_original_sha"]==29
    assert summary["original_SHA_verified"]==len(admitted)
    assert summary["original_SYID_parsed"]==len(parsed)
    assert summary["original_SYID_header_ge_254"]==len(high)
    assert summary["original_low_byte_FE_FF"]==len(fe)
    assert summary["original_low_byte_ge_240"]==sum(x["quill"]["low_byte"]>=240 for x in parsed)
    assert summary["sources_already_registered_rar_1556"]==29
    assert summary["science_completed_all_29_original_SHA"] is (len(admitted)==29)
    assert summary["source_duplicate_625"]==summary["source_duplicate_991"]==0
    assert sum(r["source_member_occurrence_count"] for r in rows)==33
    assert summary["writer_completed_exact_only_first_SYID_DWORD_plus_2"]<=summary["writer_completed_final_PUB"]
    print("PUB-T-992 independently checked 4 known archives 33 fixed slots/29 fixed original SHA:")
    print(json.dumps({"verified_original_sha":len(admitted),
      "quill_SYID_parsed":len(parsed),
      "original_high_header_ge_254":len(high),
      "original_FE_FF":len(fe),
      "writer_true_inverse_final":summary["writer_completed_final_PUB"],
      "writer_counterexamples":len(summary["writer_counterexamples"]),
      "partial_source_unavailable":len(admitted)!=29},sort_keys=True))

if __name__=="__main__":
    assert len(sys.argv)==8,"usage: REPORT RAR2 DONOR REFT987 PREV991SAFE REFT991CHECKER REFT963"
    check(*(Path(x) for x in sys.argv[1:]))
