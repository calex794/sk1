#!/usr/bin/env python3
"""PUB-T-992: 29 exact historic public Publisher training PUB from 4 frozen ZIPs.

Only sha-addressed, immutable original bytes enter the frozen T987 Quill reader.
Original content never leaves the runner; no high/FE selection or manual mutation.
Only pinned original-FE/FF sources may invoke inherited, unchanged real Writer.
"""
from __future__ import annotations
from collections import Counter,defaultdict
import argparse,hashlib,importlib.util,io,json,subprocess,tempfile,urllib.request,zipfile
from pathlib import Path

RAR_PIN="703808408fd919e564a90cdc236e81db3c04af8b"
DONOR_PIN="87094c23e2a9eaa2aa9e95d72ec52f72ef109f11"
DONOR_TREE="8146fa9fdd2f577ebe02bc7205a61bb14e20d3e7"
T987_PIN="fa714fe958999325649430dad53c10edac42246a"
T984_PIN="14ac75ae0346b3bdbeeada110e1f463dda6cbb27"
T963_PIN="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
T971_PIN="cd38c8d6a545737f9f99821076340505db5e149c"
T991_SHA_DIGEST="f20c891cfbe04a517f0298372d5d407cf9dce78915c28a48da7a799749dcedb3"
T991_ARTIFACT_SHA="85e844909b89a7f8966b86914f6e7edbb0d687fc20f3645306636391101e756a"
TRAINING_SHA_DIGEST="eb2cd6ad8f21860f93d33763a8f630135c12c128e0160e0d1909c0c3ae228ae8"
SCAN_SCHEMA="sk1.cfb-diag-pub-t-992.census.v1"
WRITER_SCHEMA="sk1.cfb-diag-pub-t-984.inverse.v1"
PACKAGE_KEYS=("publisher2007_sbs","publisher2010_sbs","office2013_sbs","office2003_sbs")
PACKAGE_ROWS=(13,2,11,7)
PACKAGE_UNIQUE=(13,2,9,5)
MAX_ARCHIVE_BYTES=512*1024*1024
MAX_MEMBER_BYTES=40*1024*1024
SHA_CHARS=set("0123456789abcdef")
STATUS_VALUES={"VERIFIED","ARCHIVE_UNAVAILABLE","ARCHIVE_INVALID","MEMBERS_DRIFT","SOURCE_BYTES_DRIFT"}
PUB_CFB_MAGIC=bytes.fromhex("d0cf11e0a1b11ae1")

def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def canonical_shas(shas):return sha(("\n".join(sorted(shas))+"\n").encode("ascii"))
def git(p:Path,*args:str)->str:
    return subprocess.check_output(["git",*args],cwd=p,text=True).strip()
def pinned(p:Path,commit:str):
    if git(p,"rev-parse","HEAD")!=commit:raise RuntimeError("immutable repo pin drift")
def import_py(path:Path,name:str):
    sp=importlib.util.spec_from_file_location(name,path)
    assert sp and sp.loader
    m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m

def frozen_training(rar2:Path):
    doc=rar2/"tools/corpus/receipts/version-labelled-training-29-input-2026-09-25.json"
    assert doc.is_file()
    spec=json.loads(doc.read_text(encoding="utf-8"))
    assert spec["schema"]=="chaptera.corpus-version-labelled-training-register-input.v1"
    packages=spec["packages"]
    assert len(packages)==4
    all_members=[]
    for i,p in enumerate(packages):
        assert p["key"]==PACKAGE_KEYS[i]
        assert len(p["files"])==p["expected_observation_count"]==PACKAGE_ROWS[i]
        assert len({r["sha256"] for r in p["files"]})==p["expected_unique_sha_count"]==PACKAGE_UNIQUE[i]
        assert p["source_download"].startswith("https://www.microsoftpressstore.com/")
        assert len({r["source_archive_path"] for r in p["files"]})==len(p["files"])
        for row in p["files"]:
            assert type(row["size"]) is int and 0<row["size"]<=MAX_MEMBER_BYTES
            assert row["contents_revision_u16_at_2"]==44
            assert len(row["sha256"])==64 and set(row["sha256"])<=SHA_CHARS
            assert row["source_archive_path"].endswith(".pub")
            all_members.append((p["key"],row))
    assert len(all_members)==33
    assert len({r["sha256"] for _,r in all_members})==29
    assert canonical_shas({r["sha256"] for _,r in all_members})==TRAINING_SHA_DIGEST
    return packages,all_members

def prior_shas(rar2:Path,donor:Path,prior:Path):
    original=donor/"pub-corpus/corpus/native/unclassified"
    shas={p.stem for p in original.glob("*.pub")}
    assert len(shas)==625
    assert all(len(s)==64 and set(s)<=SHA_CHARS for s in shas)
    former=json.loads((prior/"records.json").read_text(encoding="utf-8"))
    assert isinstance(former,list) and len(former)==27
    prior_set={x["source_sha256"] for x in former}
    assert len(prior_set)==27 and canonical_shas(prior_set)==T991_SHA_DIGEST
    authority={
        x.strip() for x in (rar2/"tools/corpus/receipts/current-rar-1556.sha256.txt").read_text().splitlines()
        if x.strip()
    }
    assert len(authority)==1556
    return shas,prior_set,authority

def retrieve_package(p:dict,stage:Path):
    # No archive extraction. Inspect expected zip members directly; the exact
    # original bytes are cryptographically pinned in the pre-existing manifest.
    try:
        request=urllib.request.Request(p["source_download"],headers={
            "User-Agent":"sk1-fixed-cfb-source-audit/1.0","Accept":"*/*"})
        with urllib.request.urlopen(request,timeout=120) as f:
            blob=f.read(MAX_ARCHIVE_BYTES+1)
        if not blob or len(blob)>MAX_ARCHIVE_BYTES:
            return "ARCHIVE_INVALID",None
    except (OSError,ValueError,TimeoutError):
        return "ARCHIVE_UNAVAILABLE",None
    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as z:
            observed=[info.filename for info in z.infolist()
                      if not info.is_dir() and info.filename.lower().endswith(".pub")]
            expected=[row["source_archive_path"] for row in p["files"]]
            if len(observed)!=len(expected) or sorted(observed)!=sorted(expected):
                return "MEMBERS_DRIFT",None
            contents={}
            for row in p["files"]:
                f=z.getinfo(row["source_archive_path"])
                if f.file_size>MAX_MEMBER_BYTES or f.file_size!=row["size"]:
                    return "SOURCE_BYTES_DRIFT",None
                with z.open(f) as b:
                    data=b.read(MAX_MEMBER_BYTES+1)
                if (len(data)!=row["size"] or sha(data)!=row["sha256"] or
                    data[:8]!=PUB_CFB_MAGIC):
                    return "SOURCE_BYTES_DRIFT",None
                contents[row["sha256"]]=data
    except (zipfile.BadZipFile,RuntimeError,KeyError,OSError,ValueError):
        return "ARCHIVE_INVALID",None
    assert len(contents)==p["expected_unique_sha_count"]
    for source_sha,data in contents.items():
        path=stage/(source_sha+".pub")
        if path.exists():
            raise RuntimeError("cross package SHA collision is forbidden")
        path.write_bytes(data)
    return "VERIFIED",sha(blob)

def summary(rows,package_status):
    counts=Counter(r["source_admission_status"] for r in rows)
    quill=Counter(r["quill"]["status"] for r in rows if r["quill"] is not None)
    parsed=[r for r in rows if r["quill"] is not None and r["quill"]["status"]=="NATURAL_SYID_PARSED"]
    high=[r for r in parsed if r["quill"]["syid_header"]>=254]
    near=[r for r in parsed if r["quill"]["low_byte"]>=240]
    fe=[r for r in parsed if r["quill"]["is_fe_ff_boundary"]]
    wstatus=Counter();steps=Counter();finals=matches=0;final_shas=set();counterexamples=[]
    for row in fe:
        w=row["writer"]
        if w is None:continue
        wstatus[w["status"]]+=1
        p=w["probe"]
        if p is None:continue
        for st in p["stories"]:
            for pair in st["pairs"]:
                if not pair["both_single_pass"]:
                    steps["initial_pair_blocked"]+=1
                    continue
                steps["initial_both_pass"]+=1
                for arm,key in (("insert_then_delete","insert_delete"),
                                ("delete_then_insert","delete_insert")):
                    step=pair[arm]
                    steps["inverse_"+step["status"]]+=1
                    if step["status"]!="HOSTED_PASS":continue
                    finals+=1;final_shas.add(row["source_sha256"])
                    raw=pair[key+"_raw"];cfb=pair[key+"_cfb"]
                    hd=row["quill"]["syid_header"]
                    end=hd+2 if hd<=0xfffffffd else None
                    n=(sum(a!=b for a,b in zip(hd.to_bytes(4,"little"),
                         end.to_bytes(4,"little"))) if end is not None else None)
                    ok=(end is not None and raw["equal_length"] is True
                        and raw["extra_bytes"]==0 and raw["changed_same_offset_bytes"]==n
                        and cfb["source_syid_first_dword"]==hd
                        and cfb["final_syid_first_dword"]==end
                        and cfb["syid_first_dword_delta"]==2
                        and cfb["syid_first_dword_changed_bytes"]==n
                        and cfb["quill_differing_byte_positions_equal_len"]==n
                        and cfb["quill_changed_bytes_outside_syid_first_dword"]==0
                        and cfb["same_quill_TEXT_payload_bytes"] is True
                        and cfb["same_quill_story_syid_sequence"] is True
                        and cfb["matched_descriptor_sequence"] is True
                        and cfb["non_quill_streams_changed"]==0
                        and cfb["missing_cfb_paths"]==0
                        and cfb["added_cfb_paths"]==0
                        and cfb["cfb_entry_type_changes"]==0)
                    if ok:matches+=1
                    else:counterexamples.append({
                       "source_sha256":row["source_sha256"],
                       "story_ordinal":st["story_ordinal"],
                       "arm":arm,"expected_changed_byte_count":n,
                       "actual_changed_byte_count":raw["changed_same_offset_bytes"]})
    return {
      "planned_original_sha":29,
      "planned_archive_pub_members":33,
      "package_fetch_status":dict(package_status),
      "source_sha_status":dict(sorted(counts.items())),
      "original_SHA_verified":counts["VERIFIED"],
      "source_duplicate_625":sum(x["overlap_625"] for x in rows),
      "source_duplicate_991":sum(x["overlap_991"] for x in rows),
      "sources_already_registered_rar_1556":sum(x["member_rar_1556"] for x in rows),
      "original_Quill_status":dict(sorted(quill.items())),
      "original_SYID_parsed":len(parsed),
      "natural_header_min":min((r["quill"]["syid_header"] for r in parsed),default=None),
      "natural_header_max":max((r["quill"]["syid_header"] for r in parsed),default=None),
      "original_SYID_header_ge_254":len(high),
      "original_low_byte_ge_240":len(near),
      "original_low_byte_FE_FF":len(fe),
      "high_header_original_SHA":[{"sha256":r["source_sha256"],
                                  "header":r["quill"]["syid_header"],
                                  "low":r["quill"]["low_byte"]}
                            for r in high],
      "near_boundary_original_SHA":[{"sha256":r["source_sha256"],
                                     "header":r["quill"]["syid_header"],
                                     "low":r["quill"]["low_byte"]}
                                     for r in near],
      "genuine_original_FE_FF_SHA":[r["source_sha256"] for r in fe],
      "writer_status":dict(sorted(wstatus.items())),
      "writer_initial_and_inverse_status":dict(sorted(steps.items())),
      "writer_completed_final_PUB":finals,
      "writer_completed_distinct_original_SHA":len(final_shas),
      "writer_completed_exact_only_first_SYID_DWORD_plus_2":matches,
      "writer_counterexamples":counterexamples,
      "science_completed_all_29_original_SHA":counts["VERIFIED"]==29,
      "native_microsoft_publisher_acceptance":"NOT_EVALUATED"
    }

def main()->int:
    ap=argparse.ArgumentParser()
    for arg in ("rar2","donor","ref_987","ref_991_safe"):
        ap.add_argument("--"+arg.replace("_","-"),type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    rar=a.rar2.resolve(strict=True)
    donor=a.donor.resolve(strict=True)
    r987=a.ref_987.resolve(strict=True)
    r991=a.ref_991_safe.resolve(strict=True)
    out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    for r,p in ((rar,RAR_PIN),(donor,DONOR_PIN),(r987,T987_PIN)):
        pinned(r,p)
    assert git(donor,"rev-parse","HEAD:pub-corpus/corpus/native/unclassified")==DONOR_TREE
    packages,entries=frozen_training(rar)
    former,t991,authority=prior_shas(rar,donor,r991)
    uniq=sorted({row["sha256"] for _,row in entries})
    assert len(uniq)==29 and set(uniq).isdisjoint(former)
    assert set(uniq).isdisjoint(t991)
    assert set(uniq).issubset(authority)
    by_sha=defaultdict(list)
    for key,e in entries:by_sha[e["sha256"]].append((key,e))
    raw={}
    with tempfile.TemporaryDirectory(prefix="sk1-t992-natural-input-") as work:
        stage=Path(work)/"source_pub";stage.mkdir()
        package_status={}
        archive_hashes={}
        for p in packages:
            status,archive_sha=retrieve_package(p,stage)
            package_status[p["key"]]=status
            archive_hashes[p["key"]]=archive_sha
        admitted=sorted(x.stem for x in stage.glob("*.pub"))
        assert len(admitted)==len(set(admitted))
        assert set(admitted).issubset(uniq)
        census={}
        if admitted:
            scanner=rar/"tools/native-pub-candidate-cli/target/release/examples/sk1_pub_t_992_original_training_census"
            if not scanner.is_file():raise RuntimeError("approved frozen T987 scanner missing")
            receipt=Path(work)/"census.json"
            p=subprocess.run([str(scanner),str(stage),str(receipt)],
                capture_output=True,timeout=600,check=False)
            if p.returncode!=0 or not receipt.is_file():
                raise RuntimeError("frozen original Quill reader crashed/failed")
            d=json.loads(receipt.read_text())
            assert d["schema"]==SCAN_SCHEMA
            assert d["planned_pub"]==d["source_immutable_sha_verified"]==len(admitted)
            census={x["source_sha256"]:x for x in d["rows"]}
            assert len(census)==len(admitted) and set(census)==set(admitted)
        writer=rar/"tools/native-pub-candidate-cli/target/release/examples/sk1_pub_t_984_inverse_cfb"
        frozen_writer=import_py(r987/"experiments/cfb/diag/pub-t-987/run.py","frozen_987")
        records=[]
        for source_sha in uniq:
            origin=by_sha[source_sha]
            assert len({key for key,_ in origin})==1
            key=origin[0][0];e=origin[0][1]
            status=package_status[key]
            verified=source_sha in census
            assert verified==(status=="VERIFIED")
            q=census.get(source_sha)
            if q is not None:
                assert q["source_sha256"]==source_sha and q["source_bytes"]==e["size"]
            row={
              "source_sha256":source_sha,
              "package_key":key,
              "source_member_occurrence_count":len(origin),
              "expected_source_bytes":e["size"],
              "source_admission_status":status,
              "source_archive_sha256":archive_hashes[key],
              "overlap_625":source_sha in former,
              "overlap_991":source_sha in t991,
              "member_rar_1556":source_sha in authority,
              "quill":q,
              "writer":None
            }
            if q and q["status"]=="NATURAL_SYID_PARSED" and q["is_fe_ff_boundary"]:
                if not writer.is_file():raise RuntimeError("inherited real Writer binary not available")
                row["writer"]=frozen_writer.writer_probe(q,stage,writer)
            records.append(row)
    assert len(records)==29
    plan={
      "schema":"sk1.cfb-diag-pub-t-992.plan.v1",
      "source_rar2_git_pin":RAR_PIN,
      "training_spec_path":"tools/corpus/receipts/version-labelled-training-29-input-2026-09-25.json",
      "original_training_29_sha_lf_digest":TRAINING_SHA_DIGEST,
      "package_order":list(PACKAGE_KEYS),
      "package_observation_counts":list(PACKAGE_ROWS),
      "package_unique_sha_counts":list(PACKAGE_UNIQUE),
      "expected_member_observations":33,
      "expected_sha_distinct":29,
      "prior_625_commit":DONOR_PIN,
      "prior_625_tree":DONOR_TREE,
      "prior_991_27_source_sha_lf_digest":T991_SHA_DIGEST,
      "prior_991_source_safe_artifact_sha256":T991_ARTIFACT_SHA,
      "pinned_original_reader_T987":T987_PIN,
      "pinned_real_writer_T984":T984_PIN,
      "pinned_writer_helpers_T963":T963_PIN,
      "pinned_writer_sources_T971":T971_PIN,
      "upstream_product_code_unchanged":True,
      "native_microsoft_publisher_acceptance":"NOT_EVALUATED",
      "original_PUB_bytes_exported":False
    }
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n")
    (out/"records.json").write_text(json.dumps(records,indent=2)+"\n")
    report={
      "schema":"sk1.cfb-diag-pub-t-992.report.v1",
      "plan_sha256":sha((out/"plan.json").read_bytes()),
      "summary":summary(records,package_status),
      "records":records,
      "original_PUB_bytes_exported":False,
      "native_microsoft_publisher_acceptance":"NOT_EVALUATED"
    }
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    s=report["summary"]
    print(json.dumps({
        "source_sha_pinned":29,
        "original_SHA_verified":s["original_SHA_verified"],
        "parsed_original_SYID":s["original_SYID_parsed"],
        "original_high_header_ge_254":s["original_SYID_header_ge_254"],
        "original_low_FE_FF":s["original_low_byte_FE_FF"],
        "writer_final_PUB":s["writer_completed_final_PUB"],
        "status_by_package":s["package_fetch_status"]
    },sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
