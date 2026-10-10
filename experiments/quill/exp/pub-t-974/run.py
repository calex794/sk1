#!/usr/bin/env python3
"""PUB-T-974: disjoint SHA holdout for source-only FD membership vs +1 Writer code."""
from __future__ import annotations
from collections import Counter, defaultdict
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

PIN="703808408fd919e564a90cdc236e81db3c04af8b"
LALAMU="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
HOST_QUOTAS={
    "www.mathematicshed.com": 7,
    "www.compass.dorset.sch.uk": 3,
    "www.amherst.ny.us": 2,
    "www.christie.nhs.uk": 2,
    "www.surreyschools.ca": 2,
    "www.includewales.org.uk": 2,
    "media.svsd.ca": 1,
    "secure1.nbed.nb.ca": 1,
    "www.liturgyoffice.org.uk": 1,
    "www.ci.king.nc.us": 1,
    "fradragoljevar.com": 1,
    "www.resourcecentre.org.uk": 1,
    "www.algomapubliclibrary.org": 1,
    "www.hccfl.edu": 1,
    "www.sterlingne.com": 1,
    "www.bluevalleyk12.org": 1
}
EXCLUDED_969_QUOTAS={"www.mathematicshed.com":20,
    "cmapspublic2.ihmc.us":2,"secure1.nbed.nb.ca":2,"fradragoljevar.com":3}
EXCLUDED_968_QUOTAS={
    "www.mathematicshed.com":16,
    "storage.googleapis.com":3,
    "cmapspublic2.ihmc.us":5,
    "www.ci.king.nc.us":3
}
EXCLUDED_970_QUOTAS={"www.mathematicshed.com":18,
    "www.woodside-medical-practice.org.uk":3,
    "www.leonschools.net":3,
    "www.biblioteki.org":2,
    "www.liturgyoffice.org.uk":1}
EXPECTED=sum(HOST_QUOTAS.values())
SAFE=re.compile(r"^[a-z_]{1,64}$")
OLD_EXPECTED=35
PRIOR_EXPECTED=62
HERE=Path(__file__).resolve().parent
EXISTING=HERE.parents[2]/"sk1-exp-005"/"run.py"
SOURCE_STATES={"EVALUATED","SOURCE_OPEN_BLOCKED","NO_ELIGIBLE_STORY",
    "QUILL_READ_BLOCKED","QUILL_PARSE_BLOCKED","FD_STRUCTURE_BLOCKED",
    "STORY_ID_AMBIGUOUS","STATIC_PROBE_BLOCKED"}
WRITER_STATES={"HOSTED_PASS","WRITER_BLOCKED","SOURCE_REOPEN_FAILED",
    "TARGET_ID_UNAVAILABLE","STORY_ID_MISMATCH","CANONICAL_EDIT_REJECTED",
    "INVALID_CANDIDATE","READER_REOPEN_FAILED","OUTPUT_ID_UNAVAILABLE",
    "TARGET_SEMANTIC_MISMATCH","SYID_OR_SIBLING_MISMATCH",
    "PROJECT_SOURCE_OPEN_FAILED","PROJECT_APPLY_FAILED",
    "PROJECT_WRITER_FAILED","PROJECT_BYTE_MISMATCH"}
VALID_SLOTS={"first","second","middle","last"}
DOSES=(16,64,192)
VALID_GROWTH={"PASS","CAPACITY","GROWTH_UNKNOWN","GROWTH_DESCRIPTOR"}

def fetcher():
    spec=importlib.util.spec_from_file_location("sk1_fixed_exp005_public_fetcher",EXISTING)
    if spec is None or spec.loader is None:
        raise RuntimeError("pinned legacy source importer unavailable")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    assert mod.RAR2_PIN==PIN and mod.EXPECTED_ATTEMPTED==PRIOR_EXPECTED
    return mod

def select(src):
    old=src.load_manifest(src.OLD_MANIFEST,100_000)
    new=src.load_manifest(src.NEW_MANIFEST,400_000)
    prior=src.candidates()
    if (not isinstance(old,dict) or old.get("schema")!="rar2-lalamu-materialized-35-input-v1"
        or not isinstance(new,list) or len(new)!=370 or len(prior)!=PRIOR_EXPECTED):
        raise ValueError("manifest schema / prior source selection mismatch")
    old_hashes={x["sha256"] for x in old["files"]}
    used_hashes={x["sha256"] for x in prior}
    if len(old_hashes)!=OLD_EXPECTED or len(used_hashes)!=PRIOR_EXPECTED:
        raise ValueError("35/62 exclusion denominator drift")
    if old_hashes & used_hashes:
        raise ValueError("prior 62 are not independent of older 35")
    used968=set()
    for host,count in EXCLUDED_968_QUOTAS.items():
        available=[x for x in new if isinstance(x,dict)
          and isinstance(x.get("sha256"),str) and isinstance(x.get("size_bytes"),int)
          and isinstance(x.get("direct_url"),str)
          and 0<x["size_bytes"]<=src.MAX_FILE and src.source_url_valid(x["direct_url"],host)
          and x["sha256"] not in old_hashes and x["sha256"] not in used_hashes]
        available.sort(key=lambda x:x["sha256"])
        if len(available)<count:raise ValueError("historical 968 selection drift")
        used968.update(x["sha256"] for x in available[:count])
    if len(used968)!=27:raise ValueError("historical 968 SHA duplicate")
    used969=set()
    for host,count in EXCLUDED_969_QUOTAS.items():
        available=[x for x in new if isinstance(x,dict)
          and isinstance(x.get("sha256"),str) and isinstance(x.get("size_bytes"),int)
          and isinstance(x.get("direct_url"),str)
          and 0<x["size_bytes"]<=src.MAX_FILE and src.source_url_valid(x["direct_url"],host)
          and x["sha256"] not in old_hashes and x["sha256"] not in used_hashes
          and x["sha256"] not in used968]
        available.sort(key=lambda x:x["sha256"])
        if len(available)<count:raise ValueError("prior 969 selection drift")
        used969.update(x["sha256"] for x in available[:count])
    if len(used969)!=27:raise ValueError("prior 969 cohort duplicate")
    used970=set()
    for host,count in EXCLUDED_970_QUOTAS.items():
        available=[x for x in new if isinstance(x,dict)
          and isinstance(x.get("sha256"),str) and isinstance(x.get("size_bytes"),int)
          and isinstance(x.get("direct_url"),str)
          and 0<x["size_bytes"]<=src.MAX_FILE and src.source_url_valid(x["direct_url"],host)
          and x["sha256"] not in old_hashes and x["sha256"] not in used_hashes
          and x["sha256"] not in used968 and x["sha256"] not in used969]
        available.sort(key=lambda x:x["sha256"])
        if len(available)<count:raise ValueError("historical 970 selection drift")
        used970.update(x["sha256"] for x in available[:count])
    if len(used970)!=27:raise ValueError("historical 970 SHA duplicate")
    rows=[]
    for host,count in HOST_QUOTAS.items():
        matching=[]
        for x in new:
            if not isinstance(x,dict):continue
            sha,size,url=x.get("sha256"),x.get("size_bytes"),x.get("direct_url")
            if (not isinstance(sha,str) or not re.fullmatch(r"[0-9a-f]{64}",sha)
                or not isinstance(size,int) or not 0<size<=src.MAX_FILE
                or not isinstance(url,str) or not src.source_url_valid(url,host)
                or sha in old_hashes or sha in used_hashes or sha in used968 or sha in used969 or sha in used970):
                continue
            matching.append(x)
        matching.sort(key=lambda x:x["sha256"])
        if len(matching)<count:
            raise ValueError("preselected eligible host stratum insufficient: "+host)
        rows.extend({"sha256":x["sha256"],"size":x["size_bytes"],
                     "host":host,"url":x["direct_url"]} for x in matching[:count])
    if (len(rows)!=EXPECTED or len({x["sha256"] for x in rows})!=EXPECTED
        or sum(x["size"] for x in rows)>50*1024*1024):
        raise ValueError("fixed disjoint holdout overflow or duplicate")
    return rows

def run_case(row,src,binary:Path):
    r={"source_sha256":row["sha256"],"host":row["host"],
       "expected_source_bytes":row["size"],"status":"NOT_EVALUATED",
       "reason":"NOT_STARTED","probe":None}
    try:
        data=src.download(row)
    except Exception as exc:
        r["reason"]=src.safe_error(exc)
        return r
    r["status"]="SHA_VERIFIED";r["reason"]="OK"
    with tempfile.TemporaryDirectory(prefix="sk1-t974-") as tmp:
        folder=Path(tmp)
        inp=folder/"source.pub";rec=folder/"receipt.json"
        inp.write_bytes(data)
        try:
            command=subprocess.run([str(binary),str(inp),row["sha256"],str(rec)],
               stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300,check=False)
        except (OSError,subprocess.TimeoutExpired):
            r["status"]="PROBE_UNAVAILABLE";r["reason"]="PROCESS_OR_TIMEOUT"
            return r
        if command.returncode!=0 or not rec.is_file():
            r["status"]="PROBE_UNAVAILABLE";r["reason"]="EXECUTION_FAILED"
            return r
        try:
            proof=json.loads(rec.read_text(encoding="utf-8"))
            if (proof.get("schema")!="sk1.pub-t-974.source.v1"
                or proof.get("source_sha256")!=row["sha256"]
                or proof.get("source_bytes")!=len(data)
                or proof.get("publisher_native_acceptance")!="NOT_EVALUATED"
                or proof.get("product_pub_download_authorized") is not False
                or proof.get("status") not in SOURCE_STATES):
                raise ValueError("unsafe or invalid probe header")
            if proof["status"]=="EVALUATED":
                if (proof.get("static_predictions_built_before_writer") is not True
                    or proof.get("source_immutable") is not True
                    or not isinstance(proof.get("writer_arm_count"),int)
                    or proof["writer_arm_count"]<=0
                    or not isinstance(proof.get("stories"),list)):
                    raise ValueError("invalid static/provenance flags")
                n=0;used=set()
                for story in proof["stories"]:
                    if (not isinstance(story,dict)
                        or type(story.get("story_ordinal")) is not int
                        or type(story.get("syid")) is not int
                        or type(story.get("story_utf16_length")) is not int
                        or not isinstance(story.get("arms"),list)):
                        raise ValueError("bad Story numeric metadata")
                    for arm in story["arms"]:
                        if (arm.get("slot") not in VALID_SLOTS
                            or type(arm.get("at_utf16")) is not int
                            or arm["at_utf16"]>=story["story_utf16_length"]
                            or type(arm.get("ascii_rank")) is not int
                            or type(arm.get("source_tokn_hit")) is not bool
                            or arm.get("dose_utf16") not in DOSES
                            or arm.get("source_growth_class") not in VALID_GROWTH
                            or arm.get("predicted_first_class") != ("TOKN" if arm["source_tokn_hit"] else "FD" if arm["predicted_fd_hit"] else arm["source_growth_class"])
                            or type(arm.get("predicted_fd_hit")) is not bool
                            or type(arm.get("fdpp_hit")) is not bool
                            or type(arm.get("fdpc_hit")) is not bool
                            or arm.get("predicted_fd_hit")!=(
                                arm["fdpp_hit"] or arm["fdpc_hit"])
                            or type(arm.get("story_utf16_length")) is not int
                            or arm["story_utf16_length"]!=story["story_utf16_length"]):
                            raise ValueError("malformed arm")
                        key=(story["story_ordinal"],arm["at_utf16"],arm["dose_utf16"])
                        if key in used:raise ValueError("duplicate physical offset")
                        used.add(key)
                        w=arm.get("writer",{})
                        if not isinstance(w,dict) or w.get("status") not in WRITER_STATES:
                            raise ValueError("bad Writer category")
                        if w["status"]=="WRITER_BLOCKED" and not (
                            isinstance(w.get("code"),str) and SAFE.fullmatch(w["code"])):
                            raise ValueError("unsafe Writer error code")
                        n+=1
                if n!=proof["writer_arm_count"]:
                    raise ValueError("wrong physical arm count")
            r["probe"]=proof
            r["reason"]="OK"
        except (ValueError,TypeError,KeyError,AssertionError):
            r["status"]="PROBE_UNAVAILABLE";r["reason"]="INVALID_RECEIPT"
    return r

def summarize(rows):
    source_status=Counter(x["status"] if x["status"]!="SHA_VERIFIED"
                          else x["probe"]["status"] for x in rows)
    host_status=defaultdict(Counter)
    matrix=Counter();blocked=Counter();origins=set();fd_story_pairs=set()
    unique_stories=set();anomalies=[];attempts=passes=fdpp_hits=fdpc_hits=both_hits=0
    skip=0;label_counts=Counter();not_tested=Counter()
    priority=Counter();priority_mismatch=[]
    per_dose=defaultdict(Counter)
    for row in rows:
        host_status[row["host"]][row["status"]]+=1
        if row["probe"] is None:continue
        d=row["probe"]
        for st in d["stories"]:
            unique_stories.add((row["source_sha256"],st["syid"]))
            for arm in st["arms"]:
                attempts+=1
                predicted=arm["predicted_fd_hit"]
                fdpp_hits+=int(arm["fdpp_hit"]);fdpc_hits+=int(arm["fdpc_hit"])
                both_hits+=int(arm["fdpp_hit"] and arm["fdpc_hit"])
                w=arm["writer"]
                state=w["status"]
                pred=arm["predicted_first_class"]
                actual=("TOKN" if state=="WRITER_BLOCKED" and w.get("code")=="quill_token_layer" else
                        "FD" if state=="WRITER_BLOCKED" and w.get("code")=="quill_insertion_at_fd_boundary" else
                        "GROWTH_UNKNOWN" if state=="WRITER_BLOCKED" and w.get("code")=="quill_growth_would_discard_unknown" else
                        "GROWTH_DESCRIPTOR" if state=="WRITER_BLOCKED" and w.get("code")=="quill_growth_would_discard_descriptor" else
                        "CAPACITY" if state=="WRITER_BLOCKED" and w.get("code")=="quill_insufficient_capacity" else
                        "PASS" if state=="HOSTED_PASS" else "OTHER_GUARD")
                if state in {"HOSTED_PASS","WRITER_BLOCKED"}:
                    priority[pred+"->"+actual]+=1
                    per_dose[str(arm["dose_utf16"])][pred+"->"+actual]+=1
                    if pred!=actual:
                        priority_mismatch.append({"source_sha256":row["source_sha256"],
                          "syid":st["syid"],"at_utf16":arm["at_utf16"],
                          "dose_utf16":arm["dose_utf16"],
                          "predicted":pred,"actual":actual,"code":w.get("code")})
                if state not in {"HOSTED_PASS","WRITER_BLOCKED"}:
                    skip+=1;not_tested[state]+=1
                    continue
                is_fd=(state=="WRITER_BLOCKED"
                       and w.get("code")=="quill_insertion_at_fd_boundary")
                label_counts["FD" if is_fd else "NOT_FD"]+=1
                if state=="HOSTED_PASS":passes+=1
                else:blocked[w["code"]]+=1
                key=("TP" if predicted and is_fd else
                     "FP" if predicted else
                     "FN" if is_fd else "TN")
                matrix[key]+=1
                if is_fd:
                    origins.add(row["source_sha256"])
                    fd_story_pairs.add((row["source_sha256"],st["syid"]))
                if key in ("FP","FN"):
                    anomalies.append({"source_sha256":row["source_sha256"],
                       "story_ordinal":st["story_ordinal"],"syid":st["syid"],
                       "offset_utf16":arm["at_utf16"],"slot":arm["slot"],
                       "predicted_fd_hit":predicted,"fdpp_hit":arm["fdpp_hit"],
                       "fdpc_hit":arm["fdpc_hit"],"actual":state,
                       "actual_code":w.get("code")})
    return {"attempted_sources":len(rows),
      "sha_verified_sources":sum(row["status"]=="SHA_VERIFIED" for row in rows),
      "source_status":dict(sorted(source_status.items())),
      "per_host":{k:dict(sorted(v.items())) for k,v in sorted(host_status.items())},
      "evaluated_source_count":source_status["EVALUATED"],
      "evaluated_story_count":len(unique_stories),
      "unique_position_attempts":attempts,
      "comparable_writer_arms":sum(matrix.values()),
      "hosted_pass_arms":passes,"writer_nonstandard_arms":skip,
      "writer_nonstandard_reasons":dict(sorted(not_tested.items())),
      "writer_guard_counts":dict(sorted(blocked.items())),
      "fdpp_hit_arms":fdpp_hits,"fdpc_hit_arms":fdpc_hits,
      "both_fd_hit_arms":both_hits,"sources_with_actual_fd_refusal":len(origins),
      "stories_with_actual_fd_refusal":len(fd_story_pairs),
      "code_specific_confusion":{k:matrix[k] for k in ("TP","FP","FN","TN")},
      "actual_label_counts":dict(sorted(label_counts.items())),
      "mismatch_witnesses":anomalies,
      "priority_confusion":dict(sorted(priority.items())),
      "priority_mismatch_witnesses":priority_mismatch,
      "per_dose_confusion":{k:dict(sorted(v.items())) for k,v in sorted(per_dose.items())}}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--rar2",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    rar2=args.rar2.resolve()
    src=fetcher();rows=select(src)
    binary=rar2/"tools/native-pub-candidate-cli/target/release/examples/sk1_pub_t_974_fd"
    if not binary.is_file():ap.error("pinned original Writer inspector binary missing")
    dest=args.output.resolve();dest.mkdir(parents=True,exist_ok=True)
    plan={"schema":"sk1.pub-t-974.plan.v1","rar2_pin":PIN,"lalamu_pin":LALAMU,
        "source_manifest":src.NEW_MANIFEST,"old_manifest":src.OLD_MANIFEST,
        "excluded_original_35":OLD_EXPECTED,"excluded_existing_62":PRIOR_EXPECTED,
        "excluded_968_sources":27,"excluded_968_quotas":EXCLUDED_968_QUOTAS,
        "excluded_969_sources":27,"excluded_969_quotas":EXCLUDED_969_QUOTAS,
        "excluded_970_sources":27,"excluded_970_quotas":EXCLUDED_970_QUOTAS,
        "host_quotas":HOST_QUOTAS,
        "preselected_sha256":[r["sha256"] for r in rows],
        "preselected_source_bytes":sum(r["size"] for r in rows),
        "source_count":EXPECTED,
        "slots":["first","second","middle","last"],"doses_utf16":list(DOSES),
        "max_eligible_stories_per_source":3,"operation":"insert_n_ascii",
        "prediction":"source-only TOKN then FD then growth source geometry or PASS",
        "native_publisher_acceptance":"NOT_EVALUATED"}
    (dest/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    records=[]
    for row in rows:
        records.append(run_case(row,src,binary))
        (dest/"records.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
    report={"schema":"sk1.pub-t-974.report.v1","rar2_pin":PIN,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":False,
        "summary":summarize(records),"records":records}
    (dest/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    z=report["summary"]
    print(json.dumps({k:z[k] for k in (
       "attempted_sources","sha_verified_sources","evaluated_source_count",
       "unique_position_attempts","comparable_writer_arms","priority_confusion","per_dose_confusion")},sort_keys=True))
    return 0 if z["evaluated_source_count"]>=10 and z["comparable_writer_arms"]>=60 else 2

if __name__=="__main__":raise SystemExit(main())
