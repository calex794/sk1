#!/usr/bin/env python3
"""PUB-T-995: 29 exact source originals, Quill/SYID live-ID high-water census.

No Writer. No PUB edits. Immutable source files stay in a private worker
directory and are never uploaded. All Quill decoding goes through pinned
pub_quill::parse_confirmed_story_catalog (production Rust library).
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,subprocess
from pathlib import Path
from collections import Counter

SCIENCE_T992="cfcce7f3f9c425210ee28265d4dbdf79bf742dcc"
RAR2_PIN="703808408fd919e564a90cdc236e81db3c04af8b"
TRAINING_DIGEST="eb2cd6ad8f21860f93d33763a8f630135c12c128e0160e0d1909c0c3ae228ae8"
T992_SOURCE_SAFE_ARCHIVE_SHA="9c9ce7bb23ed525b1867c3e2b889d2a597d9f5603fb8dfc8691d556a65109f1e"
ORIGINAL_A="b4b005a7e6f662546cf07bdd155a1cf936293e6ceb6ac7f424456fee87051f1b"
ORIGINAL_B="3562f0fe51e5e1dbf42f81f574cea831b0734f6d08a9a1a9cc610c84f44caeff"
SCHEMA="sk1.quill-diag-pub-t-995.live-ids.v1"
PARSED="NATURAL_SYID_PARSED"
STATES={"NATURAL_SYID_PARSED","QUILL_SYID_PARSE_BLOCKED","QUILL_STREAM_UNAVAILABLE","NOT_CFB"}

def sha(data:bytes):return hashlib.sha256(data).hexdigest()
def sha_file(path:Path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):h.update(part)
    return h.hexdigest()
def git(root:Path,*args):
    return subprocess.check_output(["git",*args],cwd=root,text=True).strip()
def mod(path:Path,name:str):
    spec=importlib.util.spec_from_file_location(name,path)
    assert spec and spec.loader
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
def tally(rows):
    status=Counter(x["status"] for x in rows)
    p=[x for x in rows if x["status"]==PARSED]
    gaps=Counter(x["header_minus_max_live"] for x in p if x["max_live"] is not None)
    return {
      "original_SHA_verified":len(rows),
      "original_Quill_parsed":len(p),
      "quill_status":dict(sorted(status.items())),
      "parsed_with_header_ge_max_live":sum(x["header_ge_live_max"] is True for x in p),
      "parsed_with_header_lt_max_live":sum(x["header_ge_live_max"] is False for x in p),
      "parsed_with_duplicate_live_ids":sum(x["duplicate_id_count"]>0 for x in p),
      "numeric_header_gap_distribution":dict(sorted((str(k),v) for k,v in gaps.items())),
      "total_current_live_ids":sum(x["count"] for x in p),
      "max_natural_header":max((x["header"] for x in p),default=None),
      "max_natural_gap":max((x["header_minus_max_live"] for x in p
                             if x["header_minus_max_live"] is not None),default=None),
      "sources_in_original_rar_1556":29,
      "original_source_bytes_exported":False,
      "writer_run":False,
      "native_microsoft_publisher_saveas":"NOT_EVALUATED"
    }

def main()->int:
    ap=argparse.ArgumentParser()
    for name in ("rar2","reference_992","reference_992_safe","source_stage","output"):
        ap.add_argument("--"+name.replace("_","-"),required=True,type=Path)
    a=ap.parse_args()
    rar=a.rar2.resolve(strict=True);ref=a.reference_992.resolve(strict=True)
    safe=a.reference_992_safe.resolve(strict=True)
    stage=a.source_stage.resolve();stage.mkdir(parents=True,exist_ok=True)
    output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    assert not list(stage.iterdir()),"source-stage must be empty before original downloads"
    assert not list(output.iterdir()),"output must start empty"
    assert git(rar,"rev-parse","HEAD")==RAR2_PIN
    assert git(ref,"rev-parse","HEAD")==SCIENCE_T992
    old=mod(ref/"experiments/cfb/diag/pub-t-992/run.py","t992_pinned_producer")
    packages,entries=old.frozen_training(rar)
    frozen={x["sha256"]:x for _,x in entries}
    assert len(frozen)==29 and len(entries)==33
    assert old.canonical_shas(frozen)==TRAINING_DIGEST
    for p in packages:
        status,zip_sha=old.retrieve_package(p,stage)
        if status!="VERIFIED":raise RuntimeError(f"frozen external source package cannot be verified: {p['key']} {status}")
        assert zip_sha and len(zip_sha)==64
    originals=sorted(stage.glob("*.pub"))
    assert len(originals)==29 and {x.stem for x in originals}==set(frozen)
    for x in originals:
        assert sha_file(x)==x.stem and x.stat().st_size==frozen[x.stem]["size"]
    old_receipts=json.loads((safe/"records.json").read_text())
    assert len(old_receipts)==29
    old_rows={x["source_sha256"]:x for x in old_receipts}
    assert set(old_rows)==set(frozen)
    assert old.canonical_shas(old_rows)==TRAINING_DIGEST
    scanner=rar/"tools/native-pub-candidate-cli/target/release/examples/sk1_pub_t_995_natural_live_ids"
    assert scanner.is_file(),"trusted Quill numeric-scanner executable absent"
    scan=output/"source-safe-census.json"
    p=subprocess.run([str(scanner),str(stage),str(scan)],capture_output=True,timeout=750,check=False)
    if p.returncode!=0 or not scan.is_file():
        raise RuntimeError("frozen original Quill numeric ID parser failed")
    c=json.loads(scan.read_text())
    assert set(c["rows"][0])=={
        "source_sha256","source_bytes","status","original_immutable","header","count",
        "max_live","ids","unique_id_count","duplicate_id_count",
        "header_minus_max_live","header_ge_live_max"}
    assert c["schema"]==SCHEMA
    assert c["registered_original_sources"]==c["source_sha_verified"]==29
    rows=c["rows"]
    assert len(rows)==29 and {r["source_sha256"] for r in rows}==set(frozen)
    for row in rows:
        key=row["source_sha256"]
        base=old_rows[key]["quill"]
        assert row["status"]==base["status"]
        assert row["source_bytes"]==base["source_bytes"]==frozen[key]["size"]
        assert row["original_immutable"] is True
        if row["status"]==PARSED:
            assert (row["header"],row["count"],row["max_live"])==(
                base["syid_header"],base["syid_count"],base["syid_max_live"])
        else:
            assert row["ids"] is None and row["header"] is None
    for field in ("source_sha_verified","original_Quill_parsed",
                  "parsed_with_header_ge_max_live","parsed_with_header_lt_max_live",
                  "parsed_with_duplicate_live_ids","numeric_header_gap_distribution"):
        expected={
            "source_sha_verified":29,
            "original_Quill_parsed":tally(rows)["original_Quill_parsed"],
            "parsed_with_header_ge_max_live":tally(rows)["parsed_with_header_ge_max_live"],
            "parsed_with_header_lt_max_live":tally(rows)["parsed_with_header_lt_max_live"],
            "parsed_with_duplicate_live_ids":tally(rows)["parsed_with_duplicate_live_ids"],
            "numeric_header_gap_distribution":tally(rows)["numeric_header_gap_distribution"]
        }[field]
        assert c[field]==expected,field
    plan={
       "schema":"sk1.quill-diag-pub-t-995.plan.v1",
       "rar2_pin":RAR2_PIN,"source_t992_science_pin":SCIENCE_T992,
       "original_training_29_sha_lf_digest":TRAINING_DIGEST,
       "t992_source_safe_archive_sha":T992_SOURCE_SAFE_ARCHIVE_SHA,
       "all_original_source_sha":29,"original_archive_member_observations":33,
       "frozen_pair_sha":[ORIGINAL_A,ORIGINAL_B],
       "original_pair_expected_headers":[1009,1027],
       "original_pair_expected_count":[65,65],
       "original_pair_expected_max_live":[965,1020],
       "all_numeric_SYID_ids_safe":True,
       "original_pub_bytes_artifact_export":False,"writer_run":False,
       "native_microsoft_publisher_saveas":"NOT_EVALUATED"
    }
    scan.unlink()
    (output/"plan.json").write_text(json.dumps(plan,indent=2)+"\n")
    (output/"records.json").write_text(json.dumps(rows,indent=2)+"\n")
    report={
       "schema":"sk1.quill-diag-pub-t-995.report.v1",
       "plan_sha256":sha((output/"plan.json").read_bytes()),
       "rows":rows,
       "pair":c["pair"],
       "summary":tally(rows),
       "original_pub_bytes_artifact_export":False,
       "writer_run":False,
       "native_microsoft_publisher_saveas":"NOT_EVALUATED"
    }
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({
        "original_SHA_checked":len(rows),
        "original_Quill_parsed":report["summary"]["original_Quill_parsed"],
        "live_ID_duplicates":report["summary"]["parsed_with_duplicate_live_ids"],
        "highwater_invariant_violations":report["summary"]["parsed_with_header_lt_max_live"],
        "pair":report["pair"]["comparison"]
    },sort_keys=True))
    return 0
if __name__=="__main__":raise SystemExit(main())
