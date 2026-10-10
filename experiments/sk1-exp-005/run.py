#!/usr/bin/env python3
"""SK1-EXP-005: independently sourced SHA-pinned Quill +1 growth-guard holdout.

Reuses EXP-003 and EXP-004 Rust probes, never replaces the canonical Writer.
Raw PUB/Story/Quill bytes remain ephemeral and NEVER enter public receipts.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request

RAR2_PIN = "703808408fd919e564a90cdc236e81db3c04af8b"
LALAMU_PIN = "f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
NEW_MANIFEST = ("https://raw.githubusercontent.com/Lalalalendia/lalamu/" + LALAMU_PIN
                + "/pub-corpus/data/rar-cc-rehydrate/rehydrated-manifest.json")
OLD_MANIFEST = ("https://raw.githubusercontent.com/Lalalalendia/rar2/" + RAR2_PIN
                + "/tools/corpus/receipts/lalamu-materialized-35-input-2026-09-29.json")
QUOTAS = {
    "www.mathematicshed.com": 30,
    "www.anyssa.org": 8,
    "storage.googleapis.com": 8,
    "law.duke.edu": 6,
    "www.greville.surrey.sch.uk": 5,
    "cdn.instructables.com": 3,
    "www.bnssports.us": 2,
}
EXPECTED_ATTEMPTED = sum(QUOTAS.values())
MAX_FILE = 2_500_000
MAX_TOTAL_PLANNED = 100 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 12
PROBE_TIMEOUT_SECONDS = 150
HEX64 = re.compile(r"^[0-9a-f]{64}$")
ALLOWED_ERROR = {
    "NOT_STARTED", "HTTP_UNAVAILABLE", "REQUEST_TIMEOUT", "FETCH_ERROR",
    "UNSAFE_REDIRECT", "SHA_OR_SIZE_DRIFT", "NON_CFB_INPUT",
    "INSPECTOR_FAILED", "WRITER_PROBE_FAILED", "INSPECTOR_RECEIPT_INVALID",
    "WRITER_RECEIPT_INVALID", "OK",
}

def load_manifest(url: str, limit: int) -> object:
    # URL is an immutable pinned GitHub raw-content path hardcoded in this script.
    with urllib.request.urlopen(
        urllib.request.Request(url, headers={"User-Agent":"sk1-exp005-public-research/1.0"}),
        timeout=FETCH_TIMEOUT_SECONDS
    ) as response:
        raw = response.read(limit + 1)
    if len(raw) > limit:
        raise RuntimeError("pinned manifest size exceeded")
    return json.loads(raw)

def source_url_valid(url: str, host: str) -> bool:
    try:
        u=urllib.parse.urlsplit(url)
        if (u.scheme != "https" or u.hostname != host or
            u.username or u.password or u.query or u.fragment or
            u.port not in (None,443) or not u.path.lower().endswith(".pub")):
            return False
    except ValueError:
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False

class GuardedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        original_host = urllib.parse.urlsplit(req.full_url).hostname
        if not original_host or not source_url_valid(newurl, original_host):
            raise ValueError("UNSAFE_REDIRECT")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def candidates() -> list[dict]:
    older = load_manifest(OLD_MANIFEST, 100_000)
    fresh = load_manifest(NEW_MANIFEST, 400_000)
    if not isinstance(older,dict) or older.get("schema") != "rar2-lalamu-materialized-35-input-v1":
        raise RuntimeError("old intake authority drift")
    if not isinstance(fresh,list) or len(fresh)!=370:
        raise RuntimeError("new holdout manifest shape drift")
    excluded = {x["sha256"] for x in older["files"]}
    if len(excluded)!=35:
        raise RuntimeError("old corpus denominator drift")
    selected=[]
    seen=set()
    for host,count in QUOTAS.items():
        acceptable=[]
        for row in fresh:
            if not isinstance(row,dict):
                continue
            sha,size,url=row.get("sha256"),row.get("size_bytes"),row.get("direct_url")
            if (not isinstance(sha,str) or not HEX64.fullmatch(sha)
                or not isinstance(size,int) or not (1<=size<=MAX_FILE)
                or not isinstance(url,str) or not source_url_valid(url,host)
                or sha in excluded):
                continue
            acceptable.append(row)
        acceptable.sort(key=lambda r:r["sha256"])
        for item in acceptable[:count]:
            sha=item["sha256"]
            if sha in seen:
                raise RuntimeError("holdout SHA duplicate")
            seen.add(sha)
            selected.append({"sha256":sha,"size":item["size_bytes"],
                             "host":host,"url":item["direct_url"]})
        if len(acceptable)<count:
            raise RuntimeError("not enough pre-registered holdout rows: "+host)
    if len(selected)!=EXPECTED_ATTEMPTED or sum(x["size"] for x in selected)>MAX_TOTAL_PLANNED:
        raise RuntimeError("holdout file or byte budget mismatch")
    return selected

def download(row:dict)->bytes:
    url=row["url"]
    if not source_url_valid(url,row["host"]):
        raise ValueError("UNSAFE_REDIRECT")
    opener=urllib.request.build_opener(GuardedRedirect())
    with opener.open(
        urllib.request.Request(url,headers={"User-Agent":"sk1-exp005-public-research/1.0"}),
        timeout=FETCH_TIMEOUT_SECONDS
    ) as response:
        if not source_url_valid(response.geturl(),row["host"]):
            raise ValueError("UNSAFE_REDIRECT")
        length=response.headers.get("Content-Length")
        if length and int(length)>MAX_FILE:
            raise ValueError("SIZE_LIMIT")
        body=response.read(MAX_FILE+1)
    if len(body)!=row["size"] or hashlib.sha256(body).hexdigest()!=row["sha256"]:
        raise ValueError("SHA_OR_SIZE_DRIFT")
    if not body.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
        raise ValueError("NON_CFB_INPUT")
    return body

def safe_error(exc:Exception)->str:
    if isinstance(exc,urllib.error.HTTPError): return "HTTP_UNAVAILABLE"
    if isinstance(exc,(TimeoutError,urllib.error.URLError)): return "REQUEST_TIMEOUT"
    s=str(exc)
    if s=="UNSAFE_REDIRECT": return "UNSAFE_REDIRECT"
    if s in ("SHA_OR_SIZE_DRIFT","NON_CFB_INPUT"): return s
    return "FETCH_ERROR"

def run_binary(binary:Path,src:Path,sha:str,dest:Path,max_stories:bool)->dict|None:
    cmd=[str(binary),str(src),sha,str(dest)]
    if max_stories: cmd.append("3")
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         timeout=PROBE_TIMEOUT_SECONDS,check=False)
        if p.returncode!=0 or not dest.exists():
            return None
        return json.loads(dest.read_text(encoding="utf-8"))
    except (OSError,subprocess.TimeoutExpired,json.JSONDecodeError):
        return None

def code_for_attempt(arm:dict)->str:
    kind=arm.get("result")
    if kind=="writer_blocked":
        token=arm.get("writer_blocker_code")
        if isinstance(token,str) and re.fullmatch(r"[a-z_]{1,64}",token):
            return token
        return "UNCLASSIFIED_WRITER_BLOCK"
    names={
        "HOSTED_PASS","CANONICAL_EDIT_REJECTED","reader_or_editor_reopen_blocked",
        "project_replay_blocked","bounded_candidate_validation_failed",
        "SYID_OR_UNRELATED_STORY_MISMATCH","SYID_VERIFICATION_UNAVAILABLE",
        "NOT_EVALUATED"
    }
    return kind if kind in names else "UNCLASSIFIED_HARNESS_OUTCOME"

def run_case(row:dict,static_bin:Path,writer_bin:Path)->dict:
    out={"source_sha256":row["sha256"],"host":row["host"],
         "expected_source_bytes":row["size"],"status":"NOT_EVALUATED",
         "reason":"NOT_STARTED","static_outcome":"NOT_EVALUATED",
         "writer_outcome":"NOT_EVALUATED","second_pairs":[]}
    try:
        data=download(row)
    except Exception as exc:
        out["reason"]=safe_error(exc)
        return out
    out["status"]="SHA_VERIFIED"
    out["reason"]="OK"
    with tempfile.TemporaryDirectory(prefix="sk1-exp005-") as temp:
        src=Path(temp)/"input.pub"
        static_path=Path(temp)/"static.json"
        writer_path=Path(temp)/"writer.json"
        src.write_bytes(data)
        a=run_binary(static_bin,src,row["sha256"],static_path,False)
        if a is None or a.get("schema")!="sk1.exp004.quill-anchor-envelope.v1" or a.get("source_sha256")!=row["sha256"]:
            out["static_outcome"]="INSPECTOR_FAILED"
            return out
        out["static_outcome"]=a.get("outcome","UNKNOWN")
        if a.get("outcome")!="INSPECTED":
            return out
        out["tail2_nonzero_count"]=a.get("tail2_nonzero_count")
        out["gap_before_anchor_bytes"]=a.get("gap_before_anchor_bytes")
        out["descriptor_payload_overlaps_tail2"]=a.get("descriptor_payload_overlaps_tail2")
        out["predicted_plus_one_gate"]=a.get("predicted_plus_one_gate")
        b=run_binary(writer_bin,src,row["sha256"],writer_path,True)
        if b is None or b.get("schema")!="sk1.same-offset-growth.v1" or b.get("source_sha256")!=row["sha256"]:
            out["writer_outcome"]="WRITER_PROBE_FAILED"
            return out
        out["writer_outcome"]=b.get("result","UNKNOWN")
        out["eligible_story_attempts"]=b.get("eligible_story_attempts",0)
        for story in b.get("stories",[]):
            att=story.get("attempts",[])
            second=[x for x in att if x.get("slot")=="second"]
            if len(second)!=2: continue
            d=next((a for a in second if a.get("operation")=="delete_one"),None)
            ins=next((a for a in second if a.get("operation")=="insert_one"),None)
            if d is None or ins is None or d.get("offset_utf16")!=ins.get("offset_utf16"):
                out["writer_outcome"]="PAIR_INVALID"
                out["second_pairs"]=[]
                return out
            out["second_pairs"].append({
                "story_ordinal":story.get("story_ordinal"),
                "offset_utf16":d["offset_utf16"],
                "delete_result":code_for_attempt(d),
                "insert_result":code_for_attempt(ins),
            })
    return out

def classify_pair(p:dict)->str:
    if p["delete_result"]!="HOSTED_PASS":
        return "NOT_COMPARABLE_DELETION"
    if p["insert_result"]=="HOSTED_PASS":
        return "INSERTION_PASS"
    if p["insert_result"]=="quill_growth_would_discard_unknown":
        return "PROTECTED_TAIL_GUARD"
    return "OTHER_INSERTION_REJECTION"

def summarize(rows:list[dict])->dict:
    diag=Counter()
    pair_matrix=Counter()
    source_matrix=Counter()
    host_counts=defaultdict(Counter)
    witnesses=[]
    for r in rows:
        host_counts[r["host"]][r["status"]]+=1
        if r["status"]!="SHA_VERIFIED":
            diag["not_evaluated_"+r["reason"]]+=1
            continue
        diag["source_verified"]+=1
        if r["static_outcome"]=="INSPECTED":
            diag["static_inspected"]+=1
        else:
            diag["static_"+r["static_outcome"]]+=1
            continue
        if r["writer_outcome"]!="EVALUATED":
            diag["writer_"+r["writer_outcome"]]+=1
            continue
        diag["writer_evaluated"]+=1
        obs=set()
        pred_nonzero=r["predicted_plus_one_gate"]=="NONZERO_UNKNOWN_ANCHOR_TAIL"
        for p in r["second_pairs"]:
            label=classify_pair(p)
            diag["pair_"+label]+=1
            if label not in ("INSERTION_PASS","PROTECTED_TAIL_GUARD"):
                continue
            blocked=(label=="PROTECTED_TAIL_GUARD")
            pair_matrix["TP" if pred_nonzero and blocked else
                        "FN" if blocked else
                        "FP" if pred_nonzero else "TN"]+=1
            obs.add(label)
            if pred_nonzero!=blocked and len(witnesses)<80:
                witnesses.append({
                    "source_sha256":r["source_sha256"],
                    "story_ordinal":p["story_ordinal"],
                    "offset_utf16":p["offset_utf16"],
                    "predicted_tail_nonzero":pred_nonzero,
                    "observed":label})
        if len(obs)==1:
            blocked=("PROTECTED_TAIL_GUARD" in obs)
            source_matrix["TP" if pred_nonzero and blocked else
                          "FN" if blocked else
                          "FP" if pred_nonzero else "TN"]+=1
        elif len(obs)>1:
            source_matrix["MIXED_OUTCOMES"]+=1
        else:
            source_matrix["NO_DISCRIMINATING_STORY"]+=1
    return {
        "attempted_sources":len(rows),
        "observed":dict(sorted(diag.items())),
        "primary_independent_source_matrix":dict(sorted(source_matrix.items())),
        "correlated_story_pair_matrix":dict(sorted(pair_matrix.items())),
        "verified_by_host":{k:dict(sorted(v.items())) for k,v in sorted(host_counts.items())},
        "contradiction_witnesses":witnesses,
    }

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--rar2",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    root=args.rar2.resolve(strict=True)
    static_bin=root/"tools/native-pub-candidate-cli/target/release/examples/sk1_exp_004_anchor_census"
    writer_bin=root/"tools/native-pub-candidate-cli/target/release/examples/sk1_exp_003_same_offset"
    if not static_bin.is_file() or not writer_bin.is_file():
        p.error("pinned Rust probe executables are missing")
    rows=candidates()
    out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    (out/"plan.json").write_text(json.dumps({
        "schema":"sk1.exp005.holdout-plan.v1",
        "rar2_pin":RAR2_PIN,"lalamu_pin":LALAMU_PIN,
        "new_manifest":NEW_MANIFEST,"prior_manifest":OLD_MANIFEST,
        "host_quotas":QUOTAS,
        "source_sha256":[x["sha256"] for x in rows],
        "byte_budget":MAX_TOTAL_PLANNED,
        "scope":"holdout source-level correlation of nonzero 2-byte Quill tail with growth guard",
    },indent=2)+"\n",encoding="utf-8")
    observed=[]
    for row in rows:
        observed.append(run_case(row,static_bin,writer_bin))
        (out/"records.json").write_text(json.dumps(observed,indent=2)+"\n",encoding="utf-8")
    stats=summarize(observed)
    report={
        "schema":"sk1.exp005.holdout-report.v1",
        "rar2_pin":RAR2_PIN,"lalamu_pin":LALAMU_PIN,
        "source_manifest":NEW_MANIFEST,"prior_manifest":OLD_MANIFEST,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":False,
        "summary":stats,"records":observed,
    }
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    comparable=sum(stats["primary_independent_source_matrix"].get(k,0) for k in ("TP","TN","FP","FN"))
    verified=stats["observed"].get("source_verified",0)
    print(json.dumps({"attempted":len(rows),"verified":verified,
                      "independent_comparable":comparable,
                      "source_matrix":stats["primary_independent_source_matrix"],
                      "pair_matrix":stats["correlated_story_pair_matrix"]},sort_keys=True))
    if verified<15 or comparable<10:
        return 2  # Experimental gate: insufficient real held-out evidence.
    return 0

if __name__=="__main__":
    sys.exit(main())
