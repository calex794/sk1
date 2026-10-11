#!/usr/bin/env python3
"""PUB-T-990 independent fail-closed verifier of source-safe cross-version receipts."""
from __future__ import annotations
from collections import Counter,defaultdict
import hashlib
import json
from pathlib import Path
import re
import sys

SHA256=re.compile(r"[0-9a-f]{64}\Z")
SHA1=re.compile(r"[0-9a-f]{40}\Z")
HERE=Path(__file__).resolve().parent
SOURCE=HERE/"sources.json"
PIN="703808408fd919e564a90cdc236e81db3c04af8b"
PRIOR="2b0dcbeb60ae4d5dbe05648e17231be36858b73a92c75c1eae27825e21eca113"
REPOS={
    "pronom":("digital-preservation/pronom-research-week","10d3c0afea0863a7c0acaa01344cb576e9b1ac18",30),
    "poi":("apache/poi","c85c6918858ea279de2c33df70518c105064df41",15),
    "libmspub":("fosnola/libmspub-test","33d8f78db8b8b319098c3d5ba3ad3e952369b323",21),
}
BTEC_NUM={"fdpc_pages","fdpc_records","btec_descriptors","btec_rows",
    "nonzero_flags_descriptors","zero_sentinel_rows","targets_found",
    "targets_missing","pages_one_target","pages_zero_targets",
    "pages_multiple_targets","row_end_matches_page","row_end_mismatches_page",
    "cross_page_seams","cross_page_linked","cross_page_distinct_rows",
    "cross_page_boundary_join","raw_equal_seams","equal_linked","equal_distinct_rows",
    "equal_boundary_join","equal_same_btec_descriptor",
    "equal_different_btec_descriptor"}
WITNESS_NUM={"boundary_absolute","before_fdpc_page","after_fdpc_page",
    "before_fdpc_target","after_fdpc_target"}
WITNESS_ROW={"before_btec_row","after_btec_row"}
WITNESS_BOOL={"fully_linked","distinct_target_rows","logical_boundary_join"}
ROW_KEYS={"group","git_blob_sha1","expected_bytes","source_sha256","status",
    "reason","contents_family","contents_revision","probe_status",
    "btec_status","metrics","equal_witnesses"}
PROBE_STATUS={"ANALYZED","ANALYSIS_BLOCKED","NO_QUILL_STREAM_OR_CFB_ERROR",
    "QUILL_CATALOG_BLOCKED","TEXT_DESCRIPTOR_NOT_UNIQUE","TEXT_SPAN_INVALID",
    "FDPP_STRUCTURE_BLOCKED","FDPC_STRUCTURE_BLOCKED","STORY_SPAN_INVALID",
    "FDPC_RAW_STYLE_BLOCKED","PROBE_UNAVAILABLE"}
STATUS={"NOT_EVALUATED","SHA_VERIFIED","NOT_CFB","NO_CONTENTS","NO_QUILL",
    "OUTSIDE_PINNED_COHORT","DUPLICATE_SOURCE","READ_ERROR","ANALYZED",
    "PROBE_UNAVAILABLE"}
REASONS={"NOT_STARTED","OK","SOURCE_BLOB_OR_SIZE_DRIFT","FETCH_UNAVAILABLE",
    "ALREADY_T985_SOURCE","NO_QUILL","NOT_CFB","NO_CONTENTS","READ_ERROR",
    "PROBE_UNAVAILABLE","DUPLICATE_SHA256"}
BTEC_STATUS={"COMPLETE","PARTIAL","ABSENT","STRUCTURE_BLOCKED"}
SUMMARY_KEYS={"attempted","source_sha_verified","prior_t985_sha_overlap",
    "status_counts","probe_counts","btec_status_counts",
    "by_repo","by_family","by_family_revision","btec_metrics",
    "complete_by_family","complete_origin_groups","complete_distinct_source_sha",
    "equal_witnesses","complete_with_topology_faults"}

def validate(folder:Path):
    assert {x.name for x in folder.iterdir()}=={"plan.json","records.json","report.json"}
    data=SOURCE.read_bytes()
    file_git_blob_sha=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\x00"+data).hexdigest()
    assert file_git_blob_sha=="368a05078aa319d73048385b705d17f2913565b8"
    manifest=json.loads(data)
    assert set(manifest)=={"schema","repos","expected_sources","expected_bytes","source_rows"}
    assert manifest["schema"]=="sk1.pub-cross-version-btec.source-manifest.v1"
    assert manifest["expected_sources"]==66 and manifest["expected_bytes"]==6176540
    assert manifest["repos"]=={k:{"repo":v[0],"commit":v[1]} for k,v in REPOS.items()}
    mr=manifest["source_rows"]
    assert len(mr)==66 and len({(x["group"],x["path"]) for x in mr})==66
    assert Counter(x["group"] for x in mr)==Counter({k:v[2] for k,v in REPOS.items()})
    assert sum(x["size"] for x in mr)==manifest["expected_bytes"]
    assert all(set(x)=={"group","path","size","git_blob_sha1"} and
        SHA1.fullmatch(x["git_blob_sha1"]) and
        type(x["size"]) is int and 0<x["size"]<3_000_000 and
        isinstance(x["path"],str) and x["path"] and not x["path"].startswith("/") and
        ".." not in x["path"].split("/") for x in mr)
    plan=json.loads((folder/"plan.json").read_text())
    rows=json.loads((folder/"records.json").read_text())
    report=json.loads((folder/"report.json").read_text())
    assert set(plan)=={"schema","rar2_pin","prior_t985_zip_sha256",
        "prior_selection_git_sha","prior_sha_count",
        "source_manifest_git_sha","planned","planned_bytes",
        "by_repo","repos","source_git_blob_sha1","source_sizes",
        "read_only","native_publisher_acceptance"}
    assert plan["schema"]=="sk1.pub-t-990.plan.v1"
    assert plan["rar2_pin"]==PIN
    assert plan["prior_t985_zip_sha256"]==PRIOR
    assert plan["prior_selection_git_sha"]=="cd38c8d6a545737f9f99821076340505db5e149c"
    assert plan["prior_sha_count"]==47
    assert plan["source_manifest_git_sha"]==file_git_blob_sha
    assert plan["planned"]==66 and plan["planned_bytes"]==6176540
    assert plan["by_repo"]=={k:v[2] for k,v in REPOS.items()}
    assert plan["repos"]=={k:{"repo":v[0],"revision_sha":v[1]} for k,v in REPOS.items()}
    assert plan["source_git_blob_sha1"]==[r["git_blob_sha1"] for r in mr]
    assert plan["source_sizes"]==[r["size"] for r in mr]
    assert plan["read_only"] is True and plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert isinstance(rows,list) and len(rows)==66
    assert set(report)=={"schema","rar2_pin","native_publisher_acceptance",
      "quill_writer_invocations","product_pub_download_authorized","summary","records"}
    assert report["schema"]=="sk1.pub-t-990.report.v1"
    assert report["rar2_pin"]==PIN and report["records"]==rows
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["quill_writer_invocations"]==0
    assert report["product_pub_download_authorized"] is False

    status=Counter();probe=Counter();links=Counter();groups=defaultdict(Counter)
    by_family=defaultdict(Counter);by_rev=defaultdict(Counter)
    metrics=Counter();complete_families=Counter();complete_groups=set()
    complete_sha=set(); seen_sha=set(); count_valid_sha=overlap=total_witness=failures=0
    for r,x in zip(rows,mr):
        assert set(r)==ROW_KEYS
        assert r["group"]==x["group"] and r["git_blob_sha1"]==x["git_blob_sha1"]
        assert r["expected_bytes"]==x["size"] and type(r["expected_bytes"]) is int
        assert r["status"] in STATUS and r["reason"] in REASONS
        assert r["source_sha256"] is None or (isinstance(r["source_sha256"],str)
            and SHA256.fullmatch(r["source_sha256"]))
        assert r["contents_family"] is None or (type(r["contents_family"]) is int
            and 0<=r["contents_family"]<=65535)
        assert r["contents_revision"] is None or (type(r["contents_revision"]) is int
            and 0<=r["contents_revision"]<=65535)
        assert r["probe_status"] is None or r["probe_status"] in PROBE_STATUS
        assert r["btec_status"] is None or r["btec_status"] in BTEC_STATUS
        assert isinstance(r["equal_witnesses"],list) and len(r["equal_witnesses"])<=50000
        sha=r["source_sha256"]
        if sha is None:
            assert r["status"]=="NOT_EVALUATED" and r["contents_family"] is None
            assert r["contents_revision"] is None
        else:
            count_valid_sha+=1
            if r["status"]=="OUTSIDE_PINNED_COHORT":
                overlap+=1
                assert r["reason"]=="ALREADY_T985_SOURCE"
            if r["status"]=="DUPLICATE_SOURCE":
                assert sha in seen_sha and r["reason"]=="DUPLICATE_SHA256"
            seen_sha.add(sha)
        if r["status"] in ("ANALYZED","PROBE_UNAVAILABLE"):
            assert r["contents_family"] is not None and r["probe_status"] is not None
        if r["status"]=="NO_QUILL":assert r["probe_status"] is None
        if r["probe_status"] is not None:
            probe[r["probe_status"]]+=1
        if r["btec_status"] is not None:
            assert r["probe_status"]=="ANALYZED"
            links[r["btec_status"]]+=1
        if r["probe_status"]!="ANALYZED":
            assert r["btec_status"] is None and r["metrics"] is None and r["equal_witnesses"]==[]
        if r["btec_status"] in ("COMPLETE","PARTIAL"):
            z=r["metrics"]
            assert isinstance(z,dict) and set(z)==BTEC_NUM
            assert all(type(z[k]) is int and 0<=z[k]<=1_000_000 for k in BTEC_NUM)
            assert z["targets_found"]+z["targets_missing"]==z["btec_rows"]
            assert z["pages_one_target"]+z["pages_zero_targets"]+z["pages_multiple_targets"]==z["fdpc_pages"]
            assert z["row_end_matches_page"]+z["row_end_mismatches_page"]==z["targets_found"]
            assert z["cross_page_linked"]<=z["cross_page_seams"]
            assert z["cross_page_distinct_rows"]<=z["cross_page_linked"]
            assert z["cross_page_boundary_join"]<=z["cross_page_linked"]
            assert z["equal_linked"]<=z["raw_equal_seams"]
            assert z["equal_distinct_rows"]<=z["equal_linked"]
            assert z["equal_boundary_join"]<=z["equal_linked"]
            assert z["equal_same_btec_descriptor"]+z["equal_different_btec_descriptor"]==z["equal_linked"]
            assert z["nonzero_flags_descriptors"]<=z["btec_descriptors"]
            assert len(r["equal_witnesses"])==z["raw_equal_seams"]
            witness_linked=witness_distinct=witness_joined=0
            for w in r["equal_witnesses"]:
                assert set(w)==WITNESS_NUM|WITNESS_ROW|WITNESS_BOOL
                assert all(type(w[k]) is int and 0<=w[k]<1_000_000 for k in WITNESS_NUM)
                assert all(type(w[k]) is bool for k in WITNESS_BOOL)
                assert w["before_fdpc_page"]!=w["after_fdpc_page"]
                assert w["before_fdpc_target"]!=w["after_fdpc_target"]
                for k in WITNESS_ROW:
                    assert w[k] is None or (type(w[k]) is int and w[k]<z["btec_rows"])
                if w["fully_linked"]:
                    witness_linked+=1
                    assert all(w[k] is not None for k in WITNESS_ROW)
                if w["distinct_target_rows"]:
                    assert w["fully_linked"] and w["before_btec_row"]!=w["after_btec_row"]
                    witness_distinct+=1
                if w["logical_boundary_join"]:
                    assert w["fully_linked"]
                    witness_joined+=1
            assert witness_linked==z["equal_linked"]
            assert witness_distinct==z["equal_distinct_rows"]
            assert witness_joined==z["equal_boundary_join"]
            metrics.update(z);total_witness+=len(r["equal_witnesses"])
            if r["btec_status"]=="COMPLETE":
                assert z["targets_missing"]==0 and z["pages_zero_targets"]==0
                assert z["pages_multiple_targets"]==0 and z["row_end_mismatches_page"]==0
                assert z["btec_rows"]==z["fdpc_pages"]
                complete_families[f"0x{r['contents_family']:04x}"]+=1
                complete_groups.add(r["group"])
                complete_sha.add(sha)
                failures+=int(any(z[k] for k in (
                    "targets_missing","pages_zero_targets","pages_multiple_targets",
                    "row_end_mismatches_page")))
        else:
            assert r["metrics"] is None and r["equal_witnesses"]==[]
        status[r["status"]]+=1;groups[r["group"]][r["status"]]+=1
        if r["contents_family"] is not None:
            f=f"0x{r['contents_family']:04x}"
            by_family[f][r["status"]]+=1
            v=f"{f}:0x{r['contents_revision']:04x}" if r["contents_revision"] is not None else f+":unknown"
            by_rev[v][r["btec_status"] or r["status"]]+=1
    s=report["summary"]
    assert isinstance(s,dict) and set(s)==SUMMARY_KEYS
    expected={"attempted":len(rows),"source_sha_verified":count_valid_sha,
      "prior_t985_sha_overlap":overlap,"status_counts":dict(sorted(status.items())),
      "probe_counts":dict(sorted(probe.items())),"btec_status_counts":dict(sorted(links.items())),
      "by_repo":{k:dict(sorted(v.items())) for k,v in sorted(groups.items())},
      "by_family":{k:dict(sorted(v.items())) for k,v in sorted(by_family.items())},
      "by_family_revision":{k:dict(sorted(v.items())) for k,v in sorted(by_rev.items())},
      "btec_metrics":dict(sorted(metrics.items())),
      "complete_by_family":dict(sorted(complete_families.items())),
      "complete_origin_groups":sorted(complete_groups),
      "complete_distinct_source_sha":len(complete_sha),
      "equal_witnesses":total_witness,
      "complete_with_topology_faults":failures}
    assert s==expected,[(k,s.get(k),v) for k,v in expected.items() if s.get(k)!=v]
    print("PUB-T-990 safe verified:",s["attempted"],"planned /",s["complete_distinct_source_sha"],
        "complete; families",s["complete_by_family"],"old overlap",overlap)
    return True

if __name__=="__main__":validate(Path(sys.argv[1]))
