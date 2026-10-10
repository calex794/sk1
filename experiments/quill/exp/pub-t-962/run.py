#!/usr/bin/env python3
"""PUB-T-962: measure real-source positive ASCII-growth envelopes, never write PUB to artifacts."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PIN="703808408fd919e564a90cdc236e81db3c04af8b"
HOST_SIZES={"www.mathematicshed.com":10,"www.anyssa.org":4,
            "storage.googleapis.com":4,"law.duke.edu":3,
            "www.greville.surrey.sch.uk":2,"cdn.instructables.com":2,
            "www.bnssports.us":2}
EXPECTED=sum(HOST_SIZES.values())
LADDER=[1<<i for i in range(14)]
MAX_N=LADDER[-1]
HERE=Path(__file__).resolve().parent
EXP005=HERE.parents[2]/"sk1-exp-005"/"run.py"
SAFE_CODES=re.compile(r"^[a-z_]{1,64}$")
WRITER_STATUSES={"HOSTED_PASS","WRITER_BLOCKED","SOURCE_OPEN_BLOCKED",
 "NO_ELIGIBLE_STORY","CANONICAL_EDIT_REJECTED","INVALID_CANDIDATE_HASH",
 "REOPEN_FAILED","TARGET_SEMANTIC_MISMATCH","SYID_OR_SIBLING_MISMATCH",
 "REPLAY_OPEN_FAILED","REPLAY_APPLY_FAILED","REPLAY_WRITE_FAILED",
 "REPLAY_BYTES_MISMATCH"}

def source_import():
    spec=importlib.util.spec_from_file_location("sk1_exp005_pinned_source",EXP005)
    if spec is None or spec.loader is None:raise RuntimeError("source fetcher missing")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    if mod.RAR2_PIN!=PIN or mod.EXPECTED_ATTEMPTED!=62:
        raise RuntimeError("pinned source import drift")
    return mod

def selected(src):
    pool=src.candidates()
    if len(pool)!=62 or len({r["sha256"] for r in pool})!=62:
        raise ValueError("EXP005 corpus authority changed")
    chosen=[]
    for host,count in HOST_SIZES.items():
        rows=sorted((r for r in pool if r["host"]==host),key=lambda r:r["sha256"])
        if len(rows)<count:raise ValueError("preselected host quota unavailable")
        chosen.extend(rows[:count])
    if len(chosen)!=EXPECTED or len({x["sha256"] for x in chosen})!=EXPECTED:
        raise ValueError("preselected source count drift")
    if sum(r["size"] for r in chosen)>50*1024*1024:
        raise ValueError("preselected source byte budget exceeded")
    return chosen

def physical(source:bytes,output:bytes)->dict:
    # Source-safe: no CFB names, payload, or text are returned.
    from cfb_physical import CFB
    from cfb_physical_diff import logical
    import olefile
    left=CFB(source);right=CFB(output)
    before=logical(source);after=logical(output)
    quill="/Quill/QuillSub/CONTENTS"
    if quill not in before or quill not in after:
        raise ValueError("missing canonical Quill")
    with olefile.OleFileIO(io.BytesIO(source)) as old:
        old_size=old.get_size(["Quill","QuillSub","CONTENTS"])
    with olefile.OleFileIO(io.BytesIO(output)) as new:
        new_size=new.get_size(["Quill","QuillSub","CONTENTS"])
    return {
        "cfb_size_before":len(source),"cfb_size_after":len(output),
        "quill_stream_size_before":old_size,"quill_stream_size_after":new_size,
        "nonquill_stream_changes":sum(before.get(k)!=after.get(k) for k in (set(before)|set(after)) if k!=quill),
        "quill_logical_changed":before[quill]!=after[quill],
        "sector_count_equal":left.nsec==right.nsec,
        "fat_table_equal":left.fat==right.fat,
        "minifat_table_equal":left.minifat==right.minifat,
        "directory_sector_ids_equal":left.dirsecs==right.dirsecs,
        "root_chain_equal":left.rootchain==right.rootchain,
    }

def invoke(binary:Path,source_file:Path,row:dict,n:int,folder:Path,original:bytes)->dict:
    candidate=folder/"candidate.pub"
    receipt=folder/"receipt.json"
    candidate.unlink(missing_ok=True);receipt.unlink(missing_ok=True)
    item={"growth_utf16":n,"status":"PROBE_UNAVAILABLE","reason":"NOT_STARTED"}
    try:
        p=subprocess.run([str(binary),str(source_file),row["sha256"],
                          str(candidate),str(receipt),str(n)],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         timeout=180,check=False)
    except (OSError,subprocess.TimeoutExpired):
        item["reason"]="PROCESS_OR_TIMEOUT";return item
    if p.returncode!=0 or not receipt.is_file():
        item["reason"]="PROCESS_FAILED";return item
    try:
        proof=json.loads(receipt.read_text(encoding="utf-8"))
        status=proof.get("status")
        if status not in WRITER_STATUSES or proof.get("growth_utf16")!=n:
            raise ValueError("unrecognized probe status")
        if status=="WRITER_BLOCKED":
            code=proof.get("writer_code")
            if not isinstance(code,str) or not SAFE_CODES.fullmatch(code):
                raise ValueError("unsafe guard code")
            item["writer_code"]=code
        if "story_ordinal" in proof:
            if not all(type(proof.get(k)) is int and 0<=proof[k]<1_000_000
                for k in ("story_ordinal","offset_utf16","before_utf16","after_utf16")):
                raise ValueError("invalid offset")
            if proof["after_utf16"]!=proof["before_utf16"]+n:
                raise ValueError("growth units mismatch")
            item.update({k:proof[k] for k in ("story_ordinal","offset_utf16","before_utf16","after_utf16")})
        if status=="HOSTED_PASS":
            if not candidate.is_file():
                raise ValueError("candidate unavailable")
            output=candidate.read_bytes()
            if (proof.get("source_sha256")!=row["sha256"] or
                proof.get("candidate_sha256")!=hashlib.sha256(output).hexdigest() or
                proof.get("candidate_bytes")!=len(output) or
                not all(proof.get(k) is True for k in (
                    "reader_reopened","syid_siblings_preserved",
                    "project_replay_byte_equal","source_immutable")) or
                proof.get("native_publisher_acceptance")!="NOT_EVALUATED"):
                raise ValueError("bad PASS receipt")
            item["candidate_sha256"]=proof["candidate_sha256"]
            item["cfb"]=physical(original,output)
        item["status"]=status;item["reason"]="OK"
    except (ValueError,KeyError,TypeError,ImportError,AssertionError):
        item={"growth_utf16":n,"status":"PROBE_UNAVAILABLE","reason":"BAD_RECEIPT_OR_CFB"}
    finally:
        candidate.unlink(missing_ok=True);receipt.unlink(missing_ok=True)
    return item

def run_case(row:dict,source,binary:Path)->dict:
    r={"source_sha256":row["sha256"],"host":row["host"],"source_bytes":row["size"],
       "status":"NOT_EVALUATED","reason":"NOT_STARTED","arms":[],
       "bracket":None,"censored_at":None,"nonmonotone_detected":False}
    try:
        original=source.download(row)
    except Exception as e:
        r["reason"]=source.safe_error(e)
        return r
    r["status"]="SHA_VERIFIED";r["reason"]="OK"
    with tempfile.TemporaryDirectory(prefix="sk1-t962-") as tmp:
        folder=Path(tmp);inp=folder/"source.pub";inp.write_bytes(original)
        last_pass=0;first_fail=None;shape=None;unexpected=False
        def call(n:int,phase:str)->dict:
            nonlocal shape,unexpected
            item=invoke(binary,inp,row,n,folder,original);item["phase"]=phase
            r["arms"].append(item)
            if "story_ordinal" in item:
                cur=tuple(item[k] for k in ("story_ordinal","offset_utf16","before_utf16"))
                if shape is None:shape=cur
                elif cur!=shape:unexpected=True
            if item["status"]=="HOSTED_PASS":
                p=item["cfb"]
                if (not p["quill_logical_changed"] or p["nonquill_stream_changes"]!=0):
                    unexpected=True
            return item
        for n in LADDER:
            item=call(n,"ladder")
            if item["status"]=="HOSTED_PASS":
                last_pass=n
            else:
                first_fail=n;break
        if first_fail is not None and last_pass and r["arms"][-1]["status"]=="WRITER_BLOCKED":
            lo,hi=last_pass,first_fail
            while hi-lo>1:
                mid=(lo+hi)//2
                arm=call(mid,"refine")
                if arm["status"]=="HOSTED_PASS":lo=mid
                elif arm["status"]=="WRITER_BLOCKED":hi=mid
                else:
                    unexpected=True;break
            last_pass,first_fail=lo,hi
            if hi<MAX_N:
                neighbor=call(hi+1,"after_failure_control")
                if neighbor["status"]=="HOSTED_PASS":
                    r["nonmonotone_detected"]=True;unexpected=True
        r["bracket"]={"last_tested_pass":last_pass,"first_tested_fail":first_fail}
        if first_fail is None:r["censored_at"]=MAX_N
        if not r["arms"]:r["status"]="PROBE_UNAVAILABLE"
        elif r["arms"][0]["status"]!="HOSTED_PASS":
            r["status"]="NO_BASELINE_PASS";r["reason"]=r["arms"][0]["status"]
        elif unexpected:
            r["status"]="ANOMALY";r["reason"]="INVARIANT_OR_MONOTONICITY"
        elif first_fail is None:
            r["status"]="CENSORED_PASS";r["reason"]="CAP_8192"
        elif last_pass>0 and any(a["status"]=="PROBE_UNAVAILABLE" for a in r["arms"]):
            r["status"]="INCOMPLETE";r["reason"]="PROBE_UNAVAILABLE"
        else:
            r["status"]="BRACKET_MEASURED";r["reason"]="OBSERVED_GUARD"
    return r

def summarize(records:list[dict])->dict:
    statuses=Counter(r["status"] for r in records)
    host_counts=defaultdict(Counter)
    reasons=Counter();fail_codes=Counter()
    changed_nonquill=0;changed_file_sizes=0;changed_quill_sizes=0;changed_cfb_chains=0
    passed=0;guards=0;attempts=0
    for r in records:
        host_counts[r["host"]][r["status"]]+=1
        reasons[r["reason"]]+=1
        for a in r["arms"]:
            attempts+=1
            if a["status"]=="WRITER_BLOCKED":
                guards+=1;fail_codes[a["writer_code"]]+=1
            if a["status"]=="HOSTED_PASS":
                passed+=1;p=a["cfb"]
                changed_nonquill+=int(p["nonquill_stream_changes"]!=0)
                changed_file_sizes+=int(p["cfb_size_before"]!=p["cfb_size_after"])
                changed_quill_sizes+=int(p["quill_stream_size_before"]!=p["quill_stream_size_after"])
                changed_cfb_chains+=int(not all(p[k] for k in (
                    "sector_count_equal","fat_table_equal","minifat_table_equal",
                    "directory_sector_ids_equal","root_chain_equal")))
    return {
      "attempted_sources":len(records),
      "sha_verified_sources":sum(r["status"]!="NOT_EVALUATED" for r in records),
      "with_baseline_pass":sum(bool(r["arms"]) and r["arms"][0]["status"]=="HOSTED_PASS" for r in records),
      "status_counts":dict(sorted(statuses.items())),
      "source_reason_counts":dict(sorted(reasons.items())),
      "per_host_statuses":{k:dict(sorted(v.items())) for k,v in sorted(host_counts.items())},
      "arm_attempts":attempts,"hosted_pass_arms":passed,
      "writer_guard_arms":guards,"guard_codes":dict(sorted(fail_codes.items())),
      "pass_with_nonquill_change":changed_nonquill,
      "pass_with_pub_length_change":changed_file_sizes,
      "pass_with_quill_length_change":changed_quill_sizes,
      "pass_with_cfb_chain_change":changed_cfb_chains,
      "measured_brackets":statuses["BRACKET_MEASURED"],
      "censored_pass_sources":statuses["CENSORED_PASS"],
      "anomaly_sources":statuses["ANOMALY"]
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--rar2",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    rar2=args.rar2.resolve();sys.path.insert(0,str(rar2/"tools/corpus"))
    import olefile # noqa:F401
    source=source_import();rows=selected(source)
    binary=rar2/"tools/native-pub-candidate-cli/target/release/examples/sk1_pub_t_962_growth"
    if not binary.is_file():ap.error("pinned Writer probe missing")
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    plan={"schema":"sk1.pub-t-962.plan.v1","rar2_pin":PIN,
        "lalamu_pin":source.LALAMU_PIN,"source_manifest":source.NEW_MANIFEST,
        "excluded_source_manifest":source.OLD_MANIFEST,
        "preselected_sha256":[r["sha256"] for r in rows],"host_quotas":HOST_SIZES,
        "planned_source_bytes":sum(r["size"] for r in rows),
        "growth_ladder":LADDER,"max_growth_utf16":MAX_N,
        "scope":"independent insert N ASCII into one deterministic Story; real public PUB growth envelope, not CFB reallocator",
        "native_publisher_acceptance":"NOT_EVALUATED"}
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n")
    records=[]
    for row in rows:
        records.append(run_case(row,source,binary))
        (out/"records.json").write_text(json.dumps(records,indent=2)+"\n")
    report={"schema":"sk1.pub-t-962.report.v1","rar2_pin":PIN,
      "native_publisher_acceptance":"NOT_EVALUATED",
      "product_pub_download_authorized":False,
      "summary":summarize(records),"records":records}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    s=report["summary"]
    print(json.dumps({k:s[k] for k in ("attempted_sources","sha_verified_sources",
        "with_baseline_pass","measured_brackets","censored_pass_sources",
        "anomaly_sources","hosted_pass_arms")},sort_keys=True))
    return 0 if s["with_baseline_pass"]>=5 else 2

if __name__=="__main__":raise SystemExit(main())
