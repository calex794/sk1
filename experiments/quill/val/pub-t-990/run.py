#!/usr/bin/env python3
"""PUB-T-990: disjoint 0x22 / 0x2C read-only BTEC→FDPC source study.

Original PUB bytes, Quill and style bodies never enter artifacts or console.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import concurrent.futures
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request

PIN="703808408fd919e564a90cdc236e81db3c04af8b"
HIST="cd38c8d6a545737f9f99821076340505db5e149c"
PRIOR_ZIP="2b0dcbeb60ae4d5dbe05648e17231be36858b73a92c75c1eae27825e21eca113"
HERE=Path(__file__).resolve().parent
SOURCE=HERE/"sources.json"
REPOS={
    "pronom":("digital-preservation/pronom-research-week","10d3c0afea0863a7c0acaa01344cb576e9b1ac18",30),
    "poi":("apache/poi","c85c6918858ea279de2c33df70518c105064df41",15),
    "libmspub":("fosnola/libmspub-test","33d8f78db8b8b319098c3d5ba3ad3e952369b323",21),
}
ALLOWED_PROBE={"ANALYZED","ANALYSIS_BLOCKED","NO_QUILL_STREAM_OR_CFB_ERROR",
    "QUILL_CATALOG_BLOCKED","TEXT_DESCRIPTOR_NOT_UNIQUE","TEXT_SPAN_INVALID",
    "FDPP_STRUCTURE_BLOCKED","FDPC_STRUCTURE_BLOCKED","STORY_SPAN_INVALID",
    "FDPC_RAW_STYLE_BLOCKED"}
ALLOWED_BTEC={"COMPLETE","PARTIAL","ABSENT","STRUCTURE_BLOCKED"}
ALLOWED_STATUS={"NOT_EVALUATED","SHA_VERIFIED","NOT_CFB","NO_CONTENTS",
    "NO_QUILL","OUTSIDE_PINNED_COHORT","DUPLICATE_SOURCE","READ_ERROR",
    "ANALYZED","PROBE_UNAVAILABLE"}
BTEC_NUM=("fdpc_pages","fdpc_records","btec_descriptors","btec_rows",
    "nonzero_flags_descriptors","zero_sentinel_rows","targets_found",
    "targets_missing","pages_one_target","pages_zero_targets",
    "pages_multiple_targets","row_end_matches_page","row_end_mismatches_page",
    "cross_page_seams","cross_page_linked","cross_page_distinct_rows",
    "cross_page_boundary_join","raw_equal_seams","equal_linked","equal_distinct_rows",
    "equal_boundary_join","equal_same_btec_descriptor",
    "equal_different_btec_descriptor")
CFB_MAGIC=bytes.fromhex("d0cf11e0a1b11ae1")

def pinned_old(path:Path)->set[str]:
    f=path.resolve()/"experiments/quill/val/pub-t-971/run.py"
    if not f.is_file():raise RuntimeError("historic selector unavailable")
    spec=importlib.util.spec_from_file_location("immutable_t971_old47",f)
    if spec is None or spec.loader is None:raise RuntimeError("old selector import unavailable")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    if (mod.PIN!=PIN or mod.EXPECTED_REMNANT!=47 or
        mod.EXPECTED_BYTES!=28191744 or mod.EXPECTED_HOSTS!=37):
        raise RuntimeError("old SHA cohort selection drift")
    old=mod.select_all_unused(mod.fetcher())
    shas={r["sha256"] for r in old}
    if len(shas)!=47:raise RuntimeError("historic 47 SHA selection changed")
    return shas

def plan_sources()->dict:
    raw=SOURCE.read_bytes()
    data=json.loads(raw)
    if (data.get("schema")!="sk1.pub-cross-version-btec.source-manifest.v1" or
        data.get("expected_sources")!=66 or data.get("expected_bytes")!=6176540):
        raise ValueError("external manifest plan drift")
    assert data["repos"]=={k:{"repo":r,"commit":sha} for k,(r,sha,_) in REPOS.items()}
    rows=data["source_rows"]
    assert isinstance(rows,list) and len(rows)==66
    assert Counter(r["group"] for r in rows)==Counter({k:n for k,(_,_,n) in REPOS.items()})
    assert len({(r["group"],r["path"]) for r in rows})==66
    assert sum(r["size"] for r in rows)==6176540
    assert all(set(r)=={"group","path","size","git_blob_sha1"} and
        isinstance(r["path"],str) and
        not r["path"].startswith("/") and ".." not in Path(r["path"]).parts and
        re.fullmatch(r"[a-f0-9]{40}",r["git_blob_sha1"]) and
        type(r["size"]) is int and 0<r["size"]<3_000_000 for r in rows)
    return data

def download(row:dict)->bytes:
    repo,ref,_=REPOS[row["group"]]
    p=urllib.parse.quote(row["path"],safe="/")
    url=f"https://raw.githubusercontent.com/{repo}/{ref}/{p}"
    req=urllib.request.Request(url,headers={"User-Agent":"SK1-pinned-source-only-Quill-reader/1.0"})
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req,timeout=30) as result:
                content=result.read(row["size"]+1)
            if len(content)!=row["size"]:
                raise ValueError("SIZE_DRIFT")
            git_blob=hashlib.sha1(b"blob "+str(len(content)).encode()+b"\x00"+content).hexdigest()
            if git_blob!=row["git_blob_sha1"]:
                raise ValueError("BLOB_DRIFT")
            return content
        except (urllib.error.URLError,TimeoutError,OSError):
            if attempt==1:raise RuntimeError("FETCH_UNAVAILABLE") from None
    raise RuntimeError("FETCH_UNAVAILABLE")

def classify_cfb(original:bytes):
    if not original.startswith(CFB_MAGIC):
        return "NOT_CFB",None,None,False
    import olefile
    try:
        ole=olefile.OleFileIO(io.BytesIO(original))
        try:
            if not ole.exists(["Contents"]):
                return "NO_CONTENTS",None,None,False
            contents=ole.openstream(["Contents"]).read(16)
            family=int.from_bytes(contents[2:4],"little") if len(contents)>=4 else None
            revision=int.from_bytes(contents[12:14],"little") if len(contents)>=14 else None
            has_quill=ole.exists(["Quill","QuillSub","CONTENTS"])
            return "SHA_VERIFIED",family,revision,has_quill
        finally:ole.close()
    except (OSError,IOError,ValueError,TypeError):
        return "READ_ERROR",None,None,False

def probe(original:bytes,sha:str,binary:Path)->dict:
    with tempfile.TemporaryDirectory(prefix="sk1-t990-") as tmp:
        base=Path(tmp);source=base/"input.pub";out=base/"receipt.json"
        source.write_bytes(original)
        try:
            proc=subprocess.run([str(binary),str(source),sha,str(out)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                timeout=180,check=False)
        except (OSError,subprocess.TimeoutExpired):
            return {"probe_status":"PROBE_UNAVAILABLE","btec_status":None,
                    "metrics":None,"equal_witnesses":[]}
        if proc.returncode!=0 or not out.exists():
            return {"probe_status":"PROBE_UNAVAILABLE","btec_status":None,
                    "metrics":None,"equal_witnesses":[]}
        try:
            receipt=json.loads(out.read_text(encoding="utf-8"))
            if (receipt.get("schema")!="sk1.pub-t-990.source.v1" or
                receipt.get("source_sha256")!=sha or
                receipt.get("source_bytes")!=len(original) or
                receipt.get("status") not in ALLOWED_PROBE or
                receipt.get("quill_writer_invocations")!=0 or
                receipt.get("native_publisher_acceptance")!="NOT_EVALUATED" or
                receipt.get("source_immutable") is not True or
                receipt.get("product_pub_download_authorized") is not False):
                raise ValueError("unexpected Rust proof")
            if receipt["status"]!="ANALYZED":
                if receipt.get("stats") is not None:raise ValueError("unexpected partial statistics")
                return {"probe_status":receipt["status"],"btec_status":None,
                        "metrics":None,"equal_witnesses":[]}
            stats=receipt["stats"];link=stats["btec_link"]
            status=link["status"]
            if status not in ALLOWED_BTEC:raise ValueError("unknown BTEC class")
            raw=stats["fdpc_raw_style"]
            if status in ("ABSENT","STRUCTURE_BLOCKED"):
                if link["metrics"] is not None or link["equal_witnesses"]!=[]:
                    raise ValueError("malformed blocked class")
                metrics=None;witness=[]
            else:
                metrics={k:link["metrics"][k] for k in BTEC_NUM}
                if len(metrics)!=len(link["metrics"]) or any(type(x) is not int or x<0 for x in metrics.values()):
                    raise ValueError("bad BTEC metric")
                if (metrics["fdpc_pages"]!=stats["fdpc_page_count"] or
                    metrics["fdpc_records"]!=stats["fdpc_entry_count"] or
                    metrics["cross_page_seams"]!=raw["cross_page"] or
                    metrics["raw_equal_seams"]!=raw["equal_cross_page"]):
                    raise ValueError("fdpc independent pass disagrees")
                witness=[]
                for x in link["equal_witnesses"]:
                    # No style raw bytes/hashes: only numeric page identifiers and
                    # BTEC pointer truth values survive.
                    keep=("boundary_absolute","before_fdpc_page","after_fdpc_page",
                          "before_fdpc_target","after_fdpc_target",
                          "before_btec_row","after_btec_row","fully_linked",
                          "distinct_target_rows","logical_boundary_join")
                    if set(x)!=set(keep):raise ValueError("unexpected witness shape")
                    witness.append({k:x[k] for k in keep})
            return {"probe_status":receipt["status"],"btec_status":status,
                "metrics":metrics,"equal_witnesses":witness}
        except (KeyError,AssertionError,ValueError,TypeError):
            return {"probe_status":"PROBE_UNAVAILABLE","btec_status":None,
                    "metrics":None,"equal_witnesses":[]}

def one(row:dict,binary:Path,old:set[str])->dict:
    r={"group":row["group"],"git_blob_sha1":row["git_blob_sha1"],
       "expected_bytes":row["size"],"source_sha256":None,
       "status":"NOT_EVALUATED","reason":"NOT_STARTED",
       "contents_family":None,"contents_revision":None,
       "probe_status":None,"btec_status":None,"metrics":None,"equal_witnesses":[]}
    try:original=download(row)
    except ValueError:
        r["reason"]="SOURCE_BLOB_OR_SIZE_DRIFT";return r
    except RuntimeError:
        r["reason"]="FETCH_UNAVAILABLE";return r
    r["source_sha256"]=hashlib.sha256(original).hexdigest()
    if r["source_sha256"] in old:
        r["status"]="OUTSIDE_PINNED_COHORT";r["reason"]="ALREADY_T985_SOURCE";return r
    st,family,revision,has_quill=classify_cfb(original)
    r["status"]=st;r["contents_family"]=family;r["contents_revision"]=revision;r["reason"]="OK"
    if st!="SHA_VERIFIED":r["reason"]=st;return r
    if not has_quill:
        r["status"]="NO_QUILL";r["reason"]="NO_QUILL";return r
    inspected=probe(original,r["source_sha256"],binary)
    r.update(inspected)
    if inspected["probe_status"]=="PROBE_UNAVAILABLE":
        r["status"]="PROBE_UNAVAILABLE";r["reason"]="PROBE_UNAVAILABLE"
    else:r["status"]="ANALYZED";r["reason"]="OK"
    return r

def totals(records:list[dict])->dict:
    statuses=Counter(r["status"] for r in records)
    probe_states=Counter(r["probe_status"] for r in records if r["probe_status"] is not None)
    links=Counter(r["btec_status"] for r in records if r["btec_status"] is not None)
    by_group=defaultdict(Counter);by_family=defaultdict(Counter)
    by_revision=defaultdict(Counter);metric_totals=Counter()
    for r in records:
        by_group[r["group"]][r["status"]]+=1
        if r["contents_family"] is not None:
            family=f"0x{r['contents_family']:04x}"
            by_family[family][r["status"]]+=1
            by_revision[f"{family}:0x{r['contents_revision']:04x}" if r["contents_revision"] is not None else family+":unknown"][r["btec_status"] or r["status"]]+=1
        if r["btec_status"] in ("COMPLETE","PARTIAL"):
            metric_totals.update(r["metrics"])
    complete=[r for r in records if r["btec_status"]=="COMPLETE"]
    complete_by_family=Counter(f"0x{r['contents_family']:04x}" for r in complete)
    complete_groups=sorted({r["group"] for r in complete})
    covered_distinct=len({r["source_sha256"] for r in complete})
    return {"attempted":len(records),"source_sha_verified":sum(r["source_sha256"] is not None for r in records),
        "prior_t985_sha_overlap":sum(r["status"]=="OUTSIDE_PINNED_COHORT" for r in records),
        "status_counts":dict(sorted(statuses.items())),
        "probe_counts":dict(sorted(probe_states.items())),
        "btec_status_counts":dict(sorted(links.items())),
        "by_repo":{k:dict(sorted(v.items())) for k,v in sorted(by_group.items())},
        "by_family":{k:dict(sorted(v.items())) for k,v in sorted(by_family.items())},
        "by_family_revision":{k:dict(sorted(v.items())) for k,v in sorted(by_revision.items())},
        "btec_metrics":dict(sorted(metric_totals.items())),
        "complete_by_family":dict(sorted(complete_by_family.items())),
        "complete_origin_groups":complete_groups,
        "complete_distinct_source_sha":covered_distinct,
        "equal_witnesses":sum(len(r["equal_witnesses"]) for r in records),
        "complete_with_topology_faults":sum(
            any(r["metrics"][k]!=0 for k in (
                "targets_missing","pages_zero_targets","pages_multiple_targets","row_end_mismatches_page"))
            for r in complete)}

def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--historic-t971",type=Path,required=True)
    parser.add_argument("--rar2",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    old=pinned_old(args.historic_t971)
    manifest=plan_sources()
    binary=args.rar2.resolve()/"tools/native-pub-candidate-cli/target/release/examples/sk1_pub_t_990_cross_version"
    if not binary.is_file():parser.error("pinned source-only Rust binary missing")
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    plan={"schema":"sk1.pub-t-990.plan.v1","rar2_pin":PIN,
       "prior_t985_zip_sha256":PRIOR_ZIP,
       "prior_selection_git_sha":HIST,
       "prior_sha_count":len(old),
       "source_manifest_git_sha":"368a05078aa319d73048385b705d17f2913565b8",
       "planned":66,"planned_bytes":6176540,
       "by_repo":{k:n for k,(_,_,n) in REPOS.items()},
       "repos":{k:{"repo":repo,"revision_sha":ref} for k,(repo,ref,_) in REPOS.items()},
       "source_git_blob_sha1":[r["git_blob_sha1"] for r in manifest["source_rows"]],
       "source_sizes":[r["size"] for r in manifest["source_rows"]],
       "read_only":True,"native_publisher_acceptance":"NOT_EVALUATED"}
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        records=list(pool.map(lambda x:one(x,binary,old),manifest["source_rows"]))
    # Preserve independent denominator, but count duplicate source bytes only once.
    seen={}
    for r in records:
        sha=r["source_sha256"]
        if sha is not None and sha in seen and r["status"]=="ANALYZED":
            r["status"]="DUPLICATE_SOURCE";r["reason"]="DUPLICATE_SHA256"
            r["probe_status"]=None;r["btec_status"]=None
            r["metrics"]=None;r["equal_witnesses"]=[]
        elif sha and r["status"]!="OUTSIDE_PINNED_COHORT":
            seen[sha]=True
    report={"schema":"sk1.pub-t-990.report.v1","rar2_pin":PIN,
       "native_publisher_acceptance":"NOT_EVALUATED",
       "quill_writer_invocations":0,"product_pub_download_authorized":False,
       "summary":totals(records),"records":records}
    (out/"records.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    s=report["summary"]
    print(json.dumps({k:s[k] for k in ("attempted","source_sha_verified",
        "prior_t985_sha_overlap","complete_by_family",
        "complete_distinct_source_sha","btec_status_counts",
        "complete_with_topology_faults")},sort_keys=True))
    return 0 if (s["complete_distinct_source_sha"]>=15 and
        s["complete_by_family"].get("0x0022",0)>=3 and
        s["complete_by_family"].get("0x002c",0)>=3 and
        len(s["complete_origin_groups"])>=2 and
        s["prior_t985_sha_overlap"]==0 and s["complete_with_topology_faults"]==0) else 2

if __name__=="__main__":raise SystemExit(main())
