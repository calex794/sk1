#!/usr/bin/env python3
"""PUB-T-971: external source-disjoint blind exact-boundary validation; no raw PUB published."""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.parse

PIN="703808408fd919e564a90cdc236e81db3c04af8b"
LALAMU="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
HERE=Path(__file__).resolve().parent
FETCHER=HERE.parents[2]/"sk1-exp-005"/"run.py"
OLD_EXP5={"www.mathematicshed.com":30,"www.anyssa.org":8,
 "storage.googleapis.com":8,"law.duke.edu":6,
 "www.greville.surrey.sch.uk":5,"cdn.instructables.com":3,
 "www.bnssports.us":2}
OLD_968={"www.mathematicshed.com":16,"storage.googleapis.com":3,
 "cmapspublic2.ihmc.us":5,"www.ci.king.nc.us":3}
OLD_969={"www.mathematicshed.com":20,"cmapspublic2.ihmc.us":2,
 "secure1.nbed.nb.ca":2,"fradragoljevar.com":3}
OLD_970={"www.mathematicshed.com":18,
 "www.woodside-medical-practice.org.uk":3,
 "www.leonschools.net":3,"www.biblioteki.org":2,
 "www.liturgyoffice.org.uk":1}
EXPECTED_REMNANT=47
EXPECTED_BYTES=28191744
EXPECTED_HOSTS=37
SAFE=re.compile(r"^[a-z_]{1,64}$")
SOURCE_STATES={"EVALUATED","SOURCE_OPEN_BLOCKED","NO_ELIGIBLE_STORY",
    "QUILL_READ_BLOCKED","QUILL_PARSE_BLOCKED","FD_STRUCTURE_BLOCKED",
    "STORY_ID_AMBIGUOUS","STATIC_PROBE_BLOCKED"}
WRITER_STATES={"HOSTED_PASS","WRITER_BLOCKED","SOURCE_REOPEN_FAILED",
    "TARGET_ID_UNAVAILABLE","STORY_ID_MISMATCH","CANONICAL_EDIT_REJECTED",
    "INVALID_CANDIDATE","READER_REOPEN_FAILED","OUTPUT_ID_UNAVAILABLE",
    "TARGET_SEMANTIC_MISMATCH","SYID_OR_SIBLING_MISMATCH",
    "PROJECT_SOURCE_OPEN_FAILED","PROJECT_APPLY_FAILED",
    "PROJECT_WRITER_FAILED","PROJECT_BYTE_MISMATCH"}
PREDICTED={"PASS","CAPACITY","GROWTH_UNKNOWN","GROWTH_DESCRIPTOR","TOKN","FD"}
GROWTH={"PASS","CAPACITY","GROWTH_UNKNOWN","GROWTH_DESCRIPTOR"}

def fetcher():
    spec=importlib.util.spec_from_file_location("sk1_fixed_exp005_fetch",FETCHER)
    if not spec or not spec.loader:raise RuntimeError("pinned EXP005 helper unavailable")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    if module.RAR2_PIN!=PIN or module.EXPECTED_ATTEMPTED!=62:
        raise RuntimeError("pinned source manifest drift")
    return module

def select_all_unused(src):
    prior=src.load_manifest(src.OLD_MANIFEST,100000)
    manifest=src.load_manifest(src.NEW_MANIFEST,400000)
    if not isinstance(prior,dict) or prior.get("schema")!="rar2-lalamu-materialized-35-input-v1":
        raise ValueError("old manifest changed")
    if not isinstance(manifest,list) or len(manifest)!=370:
        raise ValueError("new manifest shape changed")
    old={x["sha256"] for x in prior["files"]}
    if len(old)!=35:raise ValueError("original 35 denominator changed")
    used=set(old)
    def select_quota(q,name):
        nonlocal used
        chosen=[]
        for host,n in q.items():
            avail=sorted((r for r in manifest if isinstance(r,dict)
                and isinstance(r.get("sha256"),str)
                and re.fullmatch(r"[0-9a-f]{64}",r["sha256"])
                and isinstance(r.get("size_bytes"),int)
                and 0<r["size_bytes"]<=src.MAX_FILE
                and isinstance(r.get("direct_url"),str)
                and src.source_url_valid(r["direct_url"],host)
                and r["sha256"] not in used),key=lambda r:r["sha256"])
            if len(avail)<n:raise ValueError("prior cohort drift: "+name)
            chosen.extend(avail[:n])
        hashes={r["sha256"] for r in chosen}
        if len(hashes)!=sum(q.values()) or hashes & used:
            raise ValueError("duplicate historical SHA in "+name)
        used.update(hashes)
    select_quota(OLD_EXP5,"EXP005")
    select_quota(OLD_968,"T968")
    select_quota(OLD_969,"T969")
    select_quota(OLD_970,"T970")
    if len(used)!=178:raise ValueError("historical 178-SHA exclusion drift")
    rows=[]
    for x in manifest:
        if not isinstance(x,dict):continue
        sha,size,url=x.get("sha256"),x.get("size_bytes"),x.get("direct_url")
        if (not isinstance(sha,str) or not re.fullmatch(r"[0-9a-f]{64}",sha)
            or not isinstance(size,int) or not 0<size<=src.MAX_FILE
            or not isinstance(url,str) or sha in used):continue
        host=urllib.parse.urlsplit(url).hostname
        if host and src.source_url_valid(url,host):
            rows.append({"sha256":sha,"size":size,"host":host,"url":url})
    rows.sort(key=lambda r:(r["host"],r["sha256"]))
    if (len(rows)!=EXPECTED_REMNANT or len({r["sha256"] for r in rows})!=len(rows)
        or sum(r["size"] for r in rows)!=EXPECTED_BYTES
        or len({r["host"] for r in rows})!=EXPECTED_HOSTS):
        raise ValueError("all-unused set changed; fail closed")
    return rows

def run_case(src,row,binary:Path):
    out={"source_sha256":row["sha256"],"host":row["host"],
         "expected_source_bytes":row["size"],
         "status":"NOT_EVALUATED","reason":"NOT_STARTED","probe":None}
    try:
        original=src.download(row)
    except Exception as exc:
        out["reason"]=src.safe_error(exc)
        return out
    out["status"]="SHA_VERIFIED";out["reason"]="OK"
    with tempfile.TemporaryDirectory(prefix="sk1-t971-") as folder:
        folder=Path(folder);input_path=folder/"source.pub";receipt=folder/"receipt.json"
        input_path.write_bytes(original)
        try:
            p=subprocess.run([str(binary),str(input_path),row["sha256"],str(receipt)],
                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300,check=False)
        except (OSError,subprocess.TimeoutExpired):
            out["status"]="PROBE_UNAVAILABLE";out["reason"]="PROCESS_OR_TIMEOUT";return out
        if p.returncode!=0 or not receipt.is_file():
            out["status"]="PROBE_UNAVAILABLE";out["reason"]="PROCESS_FAILED";return out
        try:
            proof=json.loads(receipt.read_text(encoding="utf-8"))
            if (proof.get("schema")!="sk1.pub-t-971.source.v1"
                or proof.get("source_sha256")!=row["sha256"]
                or proof.get("source_bytes")!=len(original)
                or proof.get("status") not in SOURCE_STATES
                or proof.get("publisher_native_acceptance")!="NOT_EVALUATED"
                or proof.get("product_pub_download_authorized") is not False):
                raise ValueError("bad source proof header")
            if proof["status"]=="EVALUATED":
                if (proof.get("static_predictions_built_before_writer") is not True
                    or proof.get("source_immutable") is not True
                    or not isinstance(proof.get("stories"),list)
                    or not isinstance(proof.get("writer_arm_count"),int)):
                    raise ValueError("no static preflight")
                count=0
                for story in proof["stories"]:
                    if (story.get("static_class") not in ("TOKN","FD","GROWTH")
                        or not isinstance(story.get("arms"),list)):raise ValueError("static class invalid")
                    for arm in story["arms"]:
                        if (not isinstance(arm,dict)
                            or not isinstance(arm.get("dose_utf16"),int)
                            or not 1<=arm["dose_utf16"]<=8194
                            or arm.get("predicted_first_class") not in PREDICTED
                            or arm.get("source_growth_class") not in GROWTH|{"NOT_EVALUATED_PRIORITY"}
                            or not isinstance(arm.get("writer"),dict)
                            or arm["writer"].get("status") not in WRITER_STATES):
                            raise ValueError("unsafe arm receipt")
                        w=arm["writer"]
                        if w["status"]=="WRITER_BLOCKED" and (
                            not isinstance(w.get("code"),str) or not SAFE.fullmatch(w["code"])):
                            raise ValueError("bad machine code")
                        count+=1
                if count!=proof["writer_arm_count"] or count==0:
                    raise ValueError("arm accounting mismatch")
            out["probe"]=proof
        except (KeyError,TypeError,ValueError,AssertionError):
            out["status"]="PROBE_UNAVAILABLE";out["reason"]="INVALID_RECEIPT"
    return out

def observed_class(w):
    if w["status"]=="HOSTED_PASS":return "PASS"
    if w["status"]!="WRITER_BLOCKED":return "OTHER_STATUS"
    return {"quill_token_layer":"TOKN",
      "quill_insertion_at_fd_boundary":"FD",
      "quill_growth_would_discard_unknown":"GROWTH_UNKNOWN",
      "quill_growth_would_discard_descriptor":"GROWTH_DESCRIPTOR",
      "quill_insufficient_capacity":"CAPACITY"}.get(w["code"],"OTHER_GUARD")

def summarize(records):
    src_counts=Counter();reasons=Counter();class_matrix=Counter()
    guard_codes=Counter();first_guards=Counter()
    misses=[];threshold_details=[]
    sources_good=set();evaluated=set()
    storystates=Counter();writer_total=0;pass_total=0;writer_fail=0;unusual=0
    verified=sum(r["status"]=="SHA_VERIFIED" for r in records)
    for r in records:
        status=r["probe"]["status"] if r["probe"] is not None else r["status"]
        src_counts[status]+=1;reasons[r["reason"]]+=1
        if not r["probe"] or status!="EVALUATED":continue
        evaluated.add(r["source_sha256"])
        for st in r["probe"]["stories"]:
            static=st["static_class"];storystates[static]+=1
            n=st["predicted_max_pass_utf16"]
            measures={}
            for arm in st["arms"]:
                dose=arm["dose_utf16"];w=arm["writer"]
                expected=arm["predicted_first_class"];observed=observed_class(w)
                writer_total+=1;class_matrix[expected+"->"+observed]+=1
                measures[dose]=observed
                if observed=="PASS":pass_total+=1
                elif w["status"]=="WRITER_BLOCKED":
                    writer_fail+=1;guard_codes[w["code"]]+=1
                else:unusual+=1
                if expected!=observed:
                    misses.append({"source_sha256":r["source_sha256"],
                      "story_ordinal":st["story_ordinal"],"syid":st["syid"],
                      "offset_utf16":st["insert_at_utf16"],"dose_utf16":dose,
                      "predicted":expected,"observed":observed,
                      "writer_code":w.get("code")})
            if static=="GROWTH":
                if n is not None and 0<n<8192:
                    first=st["predicted_first_growth_guard"]
                    first_guards[first]+=1
                    match=(measures.get(n)=="PASS"
                        and measures.get(n+1)==first
                        and measures.get(n+2)==next(
                          a["predicted_first_class"] for a in st["arms"] if a["dose_utf16"]==n+2)
                        and all(measures[a["dose_utf16"]]==a["predicted_first_class"] for a in st["arms"]))
                    if match:sources_good.add(r["source_sha256"])
                    threshold_details.append({
                     "source_sha256":r["source_sha256"],"syid":st["syid"],
                     "story_ordinal":st["story_ordinal"],"offset_utf16":st["insert_at_utf16"],
                     "predicted_last_pass":n,"predicted_first_fail":n+1,
                     "predicted_first_code":first,
                     "observed_at_n":measures.get(n),"observed_at_n_plus_1":measures.get(n+1),
                     "observed_at_n_plus_2":measures.get(n+2),
                     "full_threshold_match":match
                    })
    thresholds=[r["predicted_last_pass"] for r in threshold_details]
    return {"attempted_source_sha":len(records),"sha_verified":verified,
      "source_status_counts":dict(sorted(src_counts.items())),
      "source_reason_counts":dict(sorted(reasons.items())),
      "evaluated_sources":len(evaluated),
      "evaluated_story_count":sum(storystates.values()),
      "story_class_counts":dict(sorted(storystates.items())),
      "writer_arms":writer_total,"pass_arms":pass_total,
      "blocked_arms":writer_fail,"nonstandard_arms":unusual,
      "machine_guard_codes":dict(sorted(guard_codes.items())),
      "first_threshold_guard_codes":dict(sorted(first_guards.items())),
      "first_class_matrix":dict(sorted(class_matrix.items())),
      "first_class_mismatch_witnesses":misses,
      "threshold_story_count":len(threshold_details),
      "threshold_full_matches":sum(t["full_threshold_match"] for t in threshold_details),
      "threshold_source_count":len({t["source_sha256"] for t in threshold_details}),
      "threshold_matching_distinct_sources":len(sources_good),
      "threshold_min_pass":min(thresholds) if thresholds else None,
      "threshold_max_pass":max(thresholds) if thresholds else None,
      "threshold_details":threshold_details,
      "right_censored_at_8192":sum(1 for r in records if r["probe"] and
         r["probe"]["status"]=="EVALUATED" for s in r["probe"]["stories"]
           if s["static_class"]=="GROWTH" and s["predicted_max_pass_utf16"]==8192),
      "zero_positive_capacity":sum(1 for r in records if r["probe"] and
         r["probe"]["status"]=="EVALUATED" for s in r["probe"]["stories"]
           if s["static_class"]=="GROWTH" and s["predicted_max_pass_utf16"]==0)
    }

def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--rar2",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    src=fetcher();rows=select_all_unused(src)
    binpath=args.rar2.resolve()/"tools/native-pub-candidate-cli/target/release/examples/sk1_pub_t_971_threshold"
    if not binpath.is_file():parser.error("pinned Reader/Writer control binary missing")
    dest=args.output.resolve();dest.mkdir(parents=True,exist_ok=True)
    plan={"schema":"sk1.pub-t-971.plan.v1","rar2_pin":PIN,
      "lalamu_pin":LALAMU,"manifest_url":src.NEW_MANIFEST,
      "original_35_excluded":35,"exp005_62_excluded":62,
      "t968_27_excluded":27,"t969_27_excluded":27,"t970_27_excluded":27,
      "source_count":47,"source_bytes":EXPECTED_BYTES,
      "host_count":EXPECTED_HOSTS,
      "source_sha256":[r["sha256"] for r in rows],
      "max_stories_per_source":3,
      "insertion_position":"second_ascii_alnum",
      "max_static_growth_utf16":8192,
      "doses_policy":"TOKN/FD +1; growth +1,N,N+1,N+2 sorted dedup, N=0 +1/+2; N=8192 +1/8192",
      "native_publisher_acceptance":"NOT_EVALUATED"}
    (dest/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    records=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for r in pool.map(lambda row:run_case(src,row,binpath),rows):
            records.append(r)
            (dest/"records.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
    report={"schema":"sk1.pub-t-971.report.v1","rar2_pin":PIN,
      "native_publisher_acceptance":"NOT_EVALUATED",
      "product_pub_download_authorized":False,
      "summary":summarize(records),"records":records}
    (dest/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    z=report["summary"]
    print(json.dumps({k:z[k] for k in ("attempted_source_sha","sha_verified",
        "evaluated_sources","threshold_story_count","threshold_full_matches",
        "threshold_matching_distinct_sources","first_class_mismatch_witnesses")},sort_keys=True))
    return 0 if z["evaluated_sources"]>=10 and z["threshold_story_count"]>=10 else 2

if __name__=="__main__":raise SystemExit(main())
