#!/usr/bin/env python3
"""PUB-T-976: source-only original PUB CR→FDPP and FDPC census.

Inputs are the exactly pinned 47-SHA T971 cohort. No Writer code is called.
Only source-safe receipts are persisted; raw PUB remains in ephemeral memory/tmp.
"""
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

PIN="703808408fd919e564a90cdc236e81db3c04af8b"
LALAMU="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
T971="cd38c8d6a545737f9f99821076340505db5e149c"
EXPECTED_SOURCES=47
EXPECTED_BYTES=28191744
EXPECTED_HOSTS=37
QUILL_STATUSES={"ANALYZED","ANALYSIS_BLOCKED","NO_QUILL_STREAM_OR_CFB_ERROR",
                "QUILL_CATALOG_BLOCKED","TEXT_DESCRIPTOR_NOT_UNIQUE",
                "TEXT_SPAN_INVALID","FDPP_STRUCTURE_BLOCKED",
                "FDPC_STRUCTURE_BLOCKED","STORY_SPAN_INVALID"}
SOURCE_ERRORS={"NOT_STARTED","OK","HTTP_UNAVAILABLE","UNSAFE_REDIRECT",
               "REQUEST_TIMEOUT","FETCH_ERROR","SHA_OR_SIZE_DRIFT",
               "NON_CFB_INPUT","PROCESS_OR_TIMEOUT","PROCESS_FAILED",
               "INVALID_RECEIPT"}
HERE=Path(__file__).resolve().parent
MIN_PARSED=15
MIN_STORIES=100
MIN_CR=200

def historical(source_root:Path):
    old=source_root.resolve()/"experiments/quill/val/pub-t-971/run.py"
    if not old.is_file():raise RuntimeError("immutable T971 cohort selector missing")
    spec=importlib.util.spec_from_file_location("sk1_pinned_t971_selection",old)
    if spec is None or spec.loader is None:raise RuntimeError("T971 import blocked")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    if mod.PIN!=PIN or mod.LALAMU!=LALAMU or mod.EXPECTED_REMNANT!=EXPECTED_SOURCES \
            or mod.EXPECTED_BYTES!=EXPECTED_BYTES or mod.EXPECTED_HOSTS!=EXPECTED_HOSTS:
        raise RuntimeError("T971 import drift")
    return mod

def one(source,row,binary:Path):
    info={"source_sha256":row["sha256"],"host":row["host"],
          "expected_source_bytes":row["size"],"status":"NOT_EVALUATED",
          "reason":"NOT_STARTED","probe":None}
    try:
        original=source.download(row)
    except Exception as ex:
        info["reason"]=source.safe_error(ex)
        return info
    info["status"]="SHA_VERIFIED"
    info["reason"]="OK"
    with tempfile.TemporaryDirectory(prefix="sk1-t976-") as tmp:
        root=Path(tmp)
        inp=root/"origin.pub"
        receipt=root/"source-safe.json"
        inp.write_bytes(original)
        try:
            p=subprocess.run([str(binary),str(inp),row["sha256"],str(receipt)],
                             stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                             timeout=180,check=False)
        except (OSError,subprocess.TimeoutExpired):
            info["status"]="PROBE_UNAVAILABLE"
            info["reason"]="PROCESS_OR_TIMEOUT"
            return info
        if p.returncode!=0 or not receipt.is_file():
            info["status"]="PROBE_UNAVAILABLE"
            info["reason"]="PROCESS_FAILED"
            return info
        try:
            candidate=json.loads(receipt.read_text(encoding="utf-8"))
            if (not isinstance(candidate,dict)
                or candidate.get("schema")!="sk1.pub-t-976.source.v1"
                or candidate.get("source_sha256")!=row["sha256"]
                or candidate.get("source_bytes")!=len(original)
                or candidate.get("quill_writer_invocations")!=0
                or candidate.get("native_publisher_acceptance")!="NOT_EVALUATED"
                or candidate.get("product_pub_download_authorized") is not False
                or candidate.get("source_immutable") is not True
                or candidate.get("status") not in QUILL_STATUSES):
                raise ValueError("unexpected probe header")
            if candidate["status"]=="ANALYZED" and not isinstance(candidate.get("stats"),dict):
                raise ValueError("stats missing")
            if candidate["status"]!="ANALYZED" and candidate.get("stats") is not None:
                raise ValueError("incomplete source cannot have stats")
            info["probe"]=candidate
        except (ValueError,TypeError,KeyError,AssertionError):
            info["status"]="PROBE_UNAVAILABLE"
            info["reason"]="INVALID_RECEIPT"
    return info

def totals(rows):
    source_states=Counter()
    source_reasons=Counter()
    per_host=defaultdict(Counter)
    n=Counter()
    terminal=Counter()
    internal=Counter()
    mismatches=[]
    parsed=0
    for x in rows:
        status=x["probe"]["status"] if x["probe"] else x["status"]
        source_states[status]+=1
        source_reasons[x["reason"]]+=1
        per_host[x["host"]][status]+=1
        if status!="ANALYZED":continue
        parsed+=1
        z=x["probe"]["stats"]
        for k in ("quill_bytes","text_bytes","story_count","nonempty_stories",
                  "zero_length_stories","story_terminal_cr","story_missing_terminal_cr",
                  "story_catalog_byte_mismatches","raw_cr_count",
                  "story_terminal_cr_count","story_internal_cr_count",
                  "raw_cr_not_owned_by_stories","fdpp_page_count","fdpp_entry_count",
                  "fdpp_unique","fdpp_duplicate_entries","fdpc_page_count",
                  "fdpc_entry_count","fdpc_unique","fdpc_duplicate_entries",
                  "fdpp_missing_cr_ends","fdpp_extraneous_entries",
                  "story_gap_bytes","story_overlap_bytes"):
            n[k]+=z[k]
        if z["fdpp_equal_raw_cr_multiset"]:n["fdpp_multiset_equal_files"]+=1
        if z["story_partition_exact"]:n["story_partition_exact_files"]+=1
        if z["story_catalog_byte_mismatches"]==0:
            n["raw_story_catalog_agreement_files"]+=1
        for name in ("both","start_only","end_only","neither"):
            terminal[name]+=z["fdpc_terminal_"+name]
            internal[name]+=z["fdpc_internal_"+name]
        if (not z["fdpp_equal_raw_cr_multiset"]
            or not z["story_partition_exact"] or z["story_missing_terminal_cr"]>0
            or z["story_catalog_byte_mismatches"]>0):
            mismatches.append({
                "source_sha256":x["source_sha256"],"host":x["host"],
                "missing_fdpp_cr_ends":z["fdpp_missing_cr_ends"],
                "unexpected_fdpp_entries":z["fdpp_extraneous_entries"],
                "missing_fdpp_offsets":z["fdpp_missing_offset_sample"],
                "unexpected_fdpp_offsets":z["fdpp_extraneous_offset_sample"],
                "missing_terminal_cr_count":z["story_missing_terminal_cr"],
                "story_gap_bytes":z["story_gap_bytes"],
                "story_overlap_bytes":z["story_overlap_bytes"],
                "story_catalog_byte_mismatches":z["story_catalog_byte_mismatches"]
            })
    return {
        "attempted_sources":len(rows),
        "sha_verified_sources":sum(x["status"]=="SHA_VERIFIED" for x in rows),
        "parsed_sources":parsed,
        "source_states":dict(sorted(source_states.items())),
        "source_reasons":dict(sorted(source_reasons.items())),
        "per_host_states":{k:dict(sorted(v.items())) for k,v in sorted(per_host.items())},
        "totals":dict(sorted(n.items())),
        "fdpc_terminal_cr_classes":dict(sorted(terminal.items())),
        "fdpc_internal_cr_classes":dict(sorted(internal.items())),
        "counterexamples":mismatches
    }

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--historic-t971",type=Path,required=True)
    ap.add_argument("--rar2",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    historical_mod=historical(args.historic_t971)
    source=historical_mod.fetcher()
    fixed=historical_mod.select_all_unused(source)
    if (len(fixed)!=EXPECTED_SOURCES or len({x["sha256"] for x in fixed})!=EXPECTED_SOURCES
        or sum(x["size"] for x in fixed)!=EXPECTED_BYTES
        or len({x["host"] for x in fixed})!=EXPECTED_HOSTS):
        raise ValueError("historical cohort selected differently")
    binpath=args.rar2.resolve()/"tools/native-pub-candidate-cli/target/release/examples/sk1_pub_t_976_cr_fd"
    if not binpath.is_file():ap.error("pinned read-only Quill analyzer absent")
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    plan={"schema":"sk1.pub-t-976.plan.v1","rar2_pin":PIN,
          "lalamu_pin":LALAMU,"t971_selection_sha":T971,
          "selected_sha256":[r["sha256"] for r in fixed],
          "selected_file_bytes":EXPECTED_BYTES,"selected_file_count":EXPECTED_SOURCES,
          "host_count":EXPECTED_HOSTS,"historical_excluded_sha":178,
          "observation":"UTF16 CR end offset vs source FDPP values; FDPC CR-bracketing; Story text partition",
          "reader_only":True,"quill_writer_invocations":0,
          "native_publisher_acceptance":"NOT_EVALUATED"}
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n")
    records=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for row in pool.map(lambda r:one(source,r,binpath),fixed):
            records.append(row)
            (out/"records.json").write_text(json.dumps(records,indent=2)+"\n")
    summary=totals(records)
    report={"schema":"sk1.pub-t-976.report.v1","rar2_pin":PIN,
            "native_publisher_acceptance":"NOT_EVALUATED",
            "quill_writer_invocations":0,"product_pub_download_authorized":False,
            "summary":summary,"records":records}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps({"attempted":summary["attempted_sources"],
        "verified":summary["sha_verified_sources"],"parsed":summary["parsed_sources"],
        "story_count":summary["totals"].get("story_count",0),
        "raw_cr_count":summary["totals"].get("raw_cr_count",0),
        "fdpp_exact_files":summary["totals"].get("fdpp_multiset_equal_files",0),
        "counterexample_files":len(summary["counterexamples"])},sort_keys=True))
    enough=(summary["parsed_sources"]>=MIN_PARSED
        and summary["totals"].get("nonempty_stories",0)>=MIN_STORIES
        and summary["totals"].get("raw_cr_count",0)>=MIN_CR)
    return 0 if enough else 2

if __name__=="__main__":raise SystemExit(main())
