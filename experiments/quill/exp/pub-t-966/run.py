#!/usr/bin/env python3
"""PUB-T-966: measure real-source positive ASCII-growth envelopes, never write PUB to artifacts."""
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
 "REPLAY_BYTES_MISMATCH","DUPLICATE_SECOND_POSITION",
 "DUPLICATE_OTHER_POSITION"}

def source_import():
    spec=importlib.util.spec_from_file_location("sk1_exp005_pinned_source",EXP005)
    if spec is None or spec.loader is None:raise RuntimeError("source fetcher missing")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    if mod.RAR2_PIN!=PIN or mod.EXPECTED_ATTEMPTED!=62:
        raise RuntimeError("pinned source import drift")
    return mod

SLOTS=("first","middle","last")
PRIOR_ZIP_SHA="ab73d6206663523929843616e196287563468b0ac8988005842349afc206aeb9"
BASELINE=HERE/"baseline.json"

def select_with_prior(src,baseline):
    old_pool=src.candidates()
    if len(old_pool)!=62 or len({x["sha256"] for x in old_pool})!=62:
        raise ValueError("pinned public manifest changed")
    old_selection=[]
    for host,count in HOST_SIZES.items():
        rows=sorted((x for x in old_pool if x["host"]==host),key=lambda x:x["sha256"])
        if len(rows)<count:raise ValueError("old host count not reproducible")
        old_selection.extend(rows[:count])
    if len(old_selection)!=EXPECTED or len({r["sha256"] for r in old_selection})!=EXPECTED:
        raise ValueError("original 27-SHA selection drift")
    lookup={x["sha256"]:x for x in old_selection}
    by_sha=baseline["records"]
    if len(by_sha)!=14 or len({x["sha256"] for x in by_sha})!=14:
        raise ValueError("original T962 qualifying 14 not unique")
    matched=[]
    for b in by_sha:
        x=lookup.get(b["sha256"])
        if x is None or x["size"]!=b["source_bytes"] or x["host"]!=b["host"]:
            raise ValueError("T962 SHA/host/size not part of immutable selected cohort")
        if b["previous_first_fail"]!=b["previous_last_pass"]+1:
            raise ValueError("T962 previous measured bracket not adjacent")
        matched.append((x,b))
    return matched

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

def invoke(binary:Path,source_file:Path,row:dict,n:int,slot:str,folder:Path,original:bytes)->dict:
    candidate=folder/"candidate.pub";receipt=folder/"receipt.json"
    candidate.unlink(missing_ok=True);receipt.unlink(missing_ok=True)
    item={"growth_utf16":n,"slot":slot,"status":"PROBE_UNAVAILABLE","reason":"NOT_STARTED"}
    try:
        p=subprocess.run([str(binary),str(source_file),row["sha256"],
                          str(candidate),str(receipt),str(n),slot],
                         stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,check=False)
    except (OSError,subprocess.TimeoutExpired):
        item["reason"]="PROCESS_OR_TIMEOUT";return item
    if p.returncode!=0 or not receipt.is_file():
        item["reason"]="PROCESS_FAILED";return item
    try:
        proof=json.loads(receipt.read_text(encoding="utf-8"))
        status=proof.get("status")
        if status not in WRITER_STATUSES or proof.get("growth_utf16")!=n or proof.get("slot")!=slot:
            raise ValueError("unexpected slot or status")
        if status=="WRITER_BLOCKED":
            code=proof.get("writer_code")
            if not isinstance(code,str) or not SAFE_CODES.fullmatch(code):
                raise ValueError("unsafe blocker code")
            item["writer_code"]=code
        if "story_ordinal" in proof:
            required=("story_ordinal","offset_utf16","before_utf16",
                      "after_utf16","baseline_second_offset_utf16","ascii_count")
            if not all(type(proof.get(k)) is int and 0<=proof[k]<1_000_000 for k in required):
                raise ValueError("bad Story numerical metadata")
            if proof["after_utf16"]!=proof["before_utf16"]+n or proof["ascii_count"]<1:
                raise ValueError("growth units mismatch")
            item.update({k:proof[k] for k in required})
        if status=="HOSTED_PASS":
            if not candidate.is_file():raise ValueError("missing candidate")
            result=candidate.read_bytes()
            if (proof.get("source_sha256")!=row["sha256"] or
                proof.get("candidate_sha256")!=hashlib.sha256(result).hexdigest() or
                proof.get("candidate_bytes")!=len(result) or
                not all(proof.get(k) is True for k in (
                    "reader_reopened","syid_siblings_preserved",
                    "project_replay_byte_equal","source_immutable")) or
                proof.get("native_publisher_acceptance")!="NOT_EVALUATED"):
                raise ValueError("invalid PASS proof")
            item["candidate_sha256"]=proof["candidate_sha256"]
            item["cfb"]=physical(original,result)
        item["status"]=status;item["reason"]="OK"
    except (ValueError,KeyError,TypeError,ImportError,AssertionError):
        item={"growth_utf16":n,"slot":slot,"status":"PROBE_UNAVAILABLE",
              "reason":"BAD_RECEIPT_OR_CFB"}
    finally:
        candidate.unlink(missing_ok=True);receipt.unlink(missing_ok=True)
    return item

def run_case(row:dict,b:dict,source,binary:Path)->dict:
    r={"source_sha256":row["sha256"],"host":row["host"],"source_bytes":row["size"],
       "previous_second":{"story_ordinal":b["story_ordinal"],"offset_utf16":b["second_offset_utf16"],
        "before_utf16":b["story_utf16"],"last_pass":b["previous_last_pass"],
        "first_fail":b["previous_first_fail"],"first_guard":b["previous_guard"]},
       "status":"NOT_EVALUATED","reason":"NOT_STARTED","positions":[]}
    try:
        original=source.download(row)
    except Exception as exc:
        r["reason"]=source.safe_error(exc)
        return r
    r["status"]="SHA_VERIFIED";r["reason"]="OK"
    with tempfile.TemporaryDirectory(prefix="sk1-t966-") as tmp:
        folder=Path(tmp);inp=folder/"source.pub";inp.write_bytes(original)
        for slot in SLOTS:
            entry={"slot":slot,"status":"NOT_EVALUATED","reason":"NOT_STARTED",
                   "arms":[],"bracket":None,"nonmonotone_detected":False,
                   "delta_from_second":None}
            last_pass=0;first_fail=None;shape=None;unexpected=False
            def call(n:int,phase:str)->dict:
                nonlocal shape,unexpected
                item=invoke(binary,inp,row,n,slot,folder,original);item["phase"]=phase
                entry["arms"].append(item)
                if "story_ordinal" in item:
                    actual=(item["story_ordinal"],item["baseline_second_offset_utf16"],
                            item["before_utf16"])
                    expected=(b["story_ordinal"],b["second_offset_utf16"],b["story_utf16"])
                    if actual!=expected:unexpected=True
                    posshape=(item["story_ordinal"],item["offset_utf16"],
                              item["before_utf16"],item["ascii_count"])
                    if shape is None:shape=posshape
                    elif shape!=posshape:unexpected=True
                elif item["status"] not in {"PROBE_UNAVAILABLE","SOURCE_OPEN_BLOCKED","NO_ELIGIBLE_STORY"}:
                    unexpected=True
                if item["status"]=="HOSTED_PASS":
                    p=item["cfb"]
                    if (not p["quill_logical_changed"] or
                        p["nonquill_stream_changes"]!=0 or
                        p["cfb_size_before"]!=p["cfb_size_after"] or
                        p["quill_stream_size_before"]!=p["quill_stream_size_after"] or
                        not all(p[k] for k in ("sector_count_equal","fat_table_equal",
                            "minifat_table_equal","directory_sector_ids_equal","root_chain_equal"))):
                        unexpected=True
                return item

            for n in LADDER:
                item=call(n,"ladder")
                if item["status"]=="HOSTED_PASS":last_pass=n
                else:first_fail=n;break
            if (first_fail is not None and last_pass and
                entry["arms"][-1]["status"]=="WRITER_BLOCKED"):
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
                        entry["nonmonotone_detected"]=True;unexpected=True
            entry["bracket"]={"last_tested_pass":last_pass,"first_tested_fail":first_fail}
            if not entry["arms"]:
                entry["status"]="INCOMPLETE";entry["reason"]="NO_ATTEMPTS"
            elif unexpected:
                entry["status"]="ANOMALY";entry["reason"]="CONTEXT_OR_CFB_INVARIANT"
            elif entry["arms"][0]["status"] in ("DUPLICATE_SECOND_POSITION","DUPLICATE_OTHER_POSITION"):
                entry["status"]=entry["arms"][0]["status"];entry["reason"]="ALNUM_SLOT_COLLISION"
            elif entry["arms"][0]["status"]!="HOSTED_PASS":
                if entry["arms"][0]["status"]=="WRITER_BLOCKED":
                    entry["status"]="NO_BASELINE_PASS";entry["reason"]="WRITER_BLOCKED"
                else:
                    entry["status"]="INCOMPLETE";entry["reason"]=entry["arms"][0]["status"]
            elif first_fail is None:
                entry["status"]="CENSORED_PASS";entry["reason"]="CAP_8192"
            elif first_fail>0 and first_fail==last_pass+1 and all(a["status"]!="PROBE_UNAVAILABLE" for a in entry["arms"]):
                entry["status"]="BRACKET_MEASURED";entry["reason"]="OBSERVED_GUARD"
                entry["delta_from_second"]=last_pass-b["previous_last_pass"]
            else:
                entry["status"]="INCOMPLETE";entry["reason"]="UNRESOLVED_BOUNDARY"
            r["positions"].append(entry)
        r["status"]="MEASURED_WITH_EXCLUSIONS" if any(
            p["status"] not in ("BRACKET_MEASURED","CENSORED_PASS") for p in r["positions"]
            ) else "ALL_POSITIONS_MEASURED"
        if any(p["status"]=="ANOMALY" for p in r["positions"]):
            r["status"]="ANOMALY";r["reason"]="POSITION_INVARIANT_FAILED"
    return r

def summarize(records:list[dict])->dict:
    sources=Counter(x["status"] for x in records)
    positions=Counter();by_slot=defaultdict(Counter)
    guard_codes=Counter();first_codes=defaultdict(Counter)
    first_total=0;passes=0;blocked=0;arms=0
    physical_failures=0
    comparison=Counter();comparison_by_slot=defaultdict(Counter)
    for r in records:
        for p in r["positions"]:
            positions[p["status"]]+=1;by_slot[p["slot"]][p["status"]]+=1
            if p["status"]=="BRACKET_MEASURED":
                d=p["delta_from_second"]
                label="same" if d==0 else "higher" if d>0 else "lower"
                comparison[label]+=1;comparison_by_slot[p["slot"]][label]+=1
                first=p["bracket"]["first_tested_fail"]
                codes=[a.get("writer_code") for a in p["arms"]
                    if a["growth_utf16"]==first and a["status"]=="WRITER_BLOCKED"]
                if codes:first_codes[p["slot"]][codes[0]]+=1
                first_total+=1
            for a in p["arms"]:
                arms+=1
                if a["status"]=="WRITER_BLOCKED":
                    blocked+=1;guard_codes[a["writer_code"]]+=1
                if a["status"]=="HOSTED_PASS":
                    passes+=1;cfb=a["cfb"]
                    physical_failures+=int(not (
                        cfb["nonquill_stream_changes"]==0 and cfb["quill_logical_changed"] and
                        cfb["cfb_size_before"]==cfb["cfb_size_after"] and
                        cfb["quill_stream_size_before"]==cfb["quill_stream_size_after"] and
                        all(cfb[k] for k in ("sector_count_equal","fat_table_equal",
                         "minifat_table_equal","directory_sector_ids_equal","root_chain_equal"))))
    return {"source_attempts":len(records),"source_verified":sum(r["status"]!="NOT_EVALUATED" for r in records),
      "source_statuses":dict(sorted(sources.items())),
      "total_positions":sum(positions.values()),"position_statuses":dict(sorted(positions.items())),
      "by_slot":{k:dict(sorted(v.items())) for k,v in sorted(by_slot.items())},
      "arms":arms,"hosted_pass_arms":passes,"writer_blocked_arms":blocked,
      "guard_codes":dict(sorted(guard_codes.items())),
      "first_guard_codes_by_slot":{k:dict(sorted(v.items())) for k,v in sorted(first_codes.items())},
      "measured_comparisons":first_total,"comparison":dict(sorted(comparison.items())),
      "comparison_by_slot":{k:dict(sorted(v.items())) for k,v in sorted(comparison_by_slot.items())},
      "pass_cfb_invariant_failures":physical_failures,
      "sources_with_anomaly":sources["ANOMALY"]}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--rar2",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    rar2=args.rar2.resolve();sys.path.insert(0,str(rar2/"tools/corpus"))
    import olefile # noqa:F401
    baseline=json.loads(BASELINE.read_text(encoding="utf-8"))
    if (baseline.get("schema")!="sk1.pub-t-966.baseline.v1" or
        baseline.get("source_zip_sha256")!=PRIOR_ZIP_SHA or
        baseline.get("source_scientific_sha")!="4ed320411bb5bebf23ea5a4c31c336d3fba74ce1"):
        raise ValueError("original T962 baseline provenance mismatch")
    source=source_import()
    rows=select_with_prior(source,baseline)
    binary=rar2/"tools/native-pub-candidate-cli/target/release/examples/sk1_pub_t_966_positions"
    if not binary.is_file():ap.error("pinned Writer-based probe missing")
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    plan={"schema":"sk1.pub-t-966.plan.v1","rar2_pin":PIN,
        "prior_t962_zip_sha256":PRIOR_ZIP_SHA,"prior_t962_science_sha":baseline["source_scientific_sha"],
        "source_manifest":source.NEW_MANIFEST,"lalamu_pin":source.LALAMU_PIN,
        "preselected_sha256":[b["sha256"] for _,b in rows],"planned_source_bytes":sum(x["size"] for x,_ in rows),
        "slots":SLOTS,"growth_ladder":LADDER,
        "scope":"same Story, source and ASCII glyph class as T962, independent first/middle/last positions vs its second position; not native Publisher",
        "native_publisher_acceptance":"NOT_EVALUATED"}
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    records=[]
    for row,b in rows:
        records.append(run_case(row,b,source,binary))
        (out/"records.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
    summary=summarize(records)
    report={"schema":"sk1.pub-t-966.report.v1","rar2_pin":PIN,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":False,"summary":summary,"records":records}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"source_verified":summary["source_verified"],
        "measured_comparisons":summary["measured_comparisons"],
        "comparison":summary["comparison"],
        "pass_cfb_invariant_failures":summary["pass_cfb_invariant_failures"],
        "sources_with_anomaly":summary["sources_with_anomaly"]},sort_keys=True))
    # Honest partial failures preserved in receipts, but require enough new eligible
    # positions and no false success if any previously known source changes identity.
    return 0 if (summary["source_verified"]>=10 and
      summary["measured_comparisons"]>=5 and
      summary["pass_cfb_invariant_failures"]==0 and
      summary["sources_with_anomaly"]==0) else 2

if __name__=="__main__":raise SystemExit(main())
