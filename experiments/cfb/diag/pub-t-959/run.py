#!/usr/bin/env python3
"""PUB-T-959: independent one-way Writer edit with source-safe CFB physical accounting."""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

PIN="703808408fd919e564a90cdc236e81db3c04af8b"
# Independent of EXP001-004 original 35 SHA. These were used in EXP005
# for a *different* growth-guard question, never for physical Writer deltas.
HOST_SIZES={
 "www.mathematicshed.com":10,
 "www.anyssa.org":4,
 "storage.googleapis.com":4,
 "law.duke.edu":3,
 "www.greville.surrey.sch.uk":2,
 "cdn.instructables.com":2,
 "www.bnssports.us":2,
}
EXPECTED=sum(HOST_SIZES.values())
HERE=Path(__file__).resolve().parent
EXP005=HERE.parents[2]/"sk1-exp-005"/"run.py"

def legacy_source():
    spec=importlib.util.spec_from_file_location("sk1_exp005_public_fetcher",EXP005)
    if spec is None or spec.loader is None:raise RuntimeError("EXP005 immutable importer missing")
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    assert mod.RAR2_PIN==PIN and mod.EXPECTED_ATTEMPTED==62
    return mod

def choose_rows(src):
    base=src.candidates()
    assert len(base)==62 and len({x["sha256"] for x in base})==62
    out=[]
    for host,count in HOST_SIZES.items():
        pool=sorted((r for r in base if r["host"]==host),key=lambda r:r["sha256"])
        if len(pool)<count:raise ValueError("insufficient pinned stratum")
        out.extend(pool[:count])
    if len(out)!=EXPECTED or len({r["sha256"] for r in out})!=EXPECTED:
        raise ValueError("holdout selection drift")
    if sum(r["size"] for r in out)>50*1024*1024:
        raise ValueError("holdout byte budget exceeded")
    return out

SAFE_CATEGORIES={
    "header_area","header","difat_sector","fat_sector","minifat_sector",
    "directory_sector","root_ministream_container","unallocated_sector",
    "allocated_other_sector","stream_payload","stream_slack","unclassified",
}
SAFE_DIRECTORY_FIELDS={"name","name_length","type","color","left","right",
"child","clsid","state","ctime","mtime","start","size_low","size_high"}
def norm_label(label:str)->str:
    if label.startswith("directory[") and "]." in label:
        field=label.rsplit(".",1)[-1]
        return "directory_"+field if field in SAFE_DIRECTORY_FIELDS else "unclassified"
    if label.startswith("header."):
        return "header"
    if label.startswith("stream_payload:"):return "stream_payload"
    if label.startswith("stream_slack:"):return "stream_slack"
    return label if label in SAFE_CATEGORIES else "unclassified"

def raw_counts(left,right):
    changes=Counter()
    for a,b,x,y in zip(left.b,right.b,left.lab,right.lab):
        if a!=b:
            old,new=norm_label(x),norm_label(y)
            key=old if old==new else old+"->"+new
            changes[key]+=1
    return dict(sorted(changes.items()))

def physical(a:bytes,b:bytes):
    # No raw name, Story, or stream payload can enter this return value.
    from cfb_physical import CFB
    from cfb_physical_diff import logical
    old,new=CFB(a),CFB(b)
    pre,post=logical(a),logical(b)
    common=set(pre)&set(post)
    quill="/Quill/QuillSub/CONTENTS"
    if quill not in common:raise ValueError("expected canonical Quill stream missing")
    stream_changed=sum(pre[k]!=post[k] for k in common)
    other_changed=sum(pre[k]!=post[k] for k in common if k!=quill)
    same_directories=sum(
        old.dirs[i]["type"]==new.dirs[i]["type"]
        for i in range(min(len(old.dirs),len(new.dirs))))
    raw=raw_counts(old,new)
    fat_different=sum(1 for i in range(min(len(old.fat),len(new.fat)))
                    if old.fat[i]!=new.fat[i])
    mini_different=sum(1 for i in range(min(len(old.minifat),len(new.minifat)))
                    if old.minifat[i]!=new.minifat[i])
    return {
        "source_bytes":len(a),"candidate_bytes":len(b),
        "source_sector_size":old.ss,"candidate_sector_size":new.ss,
        "source_sector_count":old.nsec,"candidate_sector_count":new.nsec,
        "source_directory_count":len(old.dirs),"candidate_directory_count":len(new.dirs),
        "same_sid_type_count":same_directories,
        "source_fat_sector_count":len(old.fatsecs),"candidate_fat_sector_count":len(new.fatsecs),
        "source_minifat_sector_count":len(old.minisecs),"candidate_minifat_sector_count":len(new.minisecs),
        "source_root_chain_sector_count":len(old.rootchain),
        "candidate_root_chain_sector_count":len(new.rootchain),
        "fat_table_changed_entries_same_index":fat_different,
        "minifat_table_changed_entries_same_index":mini_different,
        "fat_sector_ids_equal":old.fatsecs==new.fatsecs,
        "difat_sector_ids_equal":old.difsecs==new.difsecs,
        "directory_sector_ids_equal":old.dirsecs==new.dirsecs,
        "root_chain_equal":old.rootchain==new.rootchain,
        "logical_stream_count_before":len(pre),
        "logical_stream_count_after":len(post),
        "logical_streams_added":len(set(post)-set(pre)),
        "logical_streams_removed":len(set(pre)-set(post)),
        "logical_streams_changed":stream_changed,
        "logical_non_quill_streams_changed":other_changed,
        "logical_quill_changed":pre[quill]!=post[quill],
        "raw_overlap_changed_byte_count":sum(raw.values()),
        "raw_bytes_added_after_overlap":max(0,len(b)-len(a)),
        "raw_bytes_removed_after_overlap":max(0,len(a)-len(b)),
        "raw_absolute_offset_categories":raw,
        "raw_unclassified_absolute_byte_count":sum(v for k,v in raw.items() if "unclassified" in k),
        "physical_interpretation":"ABSOLUTE_OFFSETS_ONLY_NOT_RELOCATION_NORMALIZED",
    }

def selftest():
    from cfb_physical import CFB
    from cfb_physical_diff import minimal
    a,b=minimal(0),minimal(1)
    diff=raw_counts(CFB(a),CFB(b))
    assert diff=={"directory_state":1},diff
    assert norm_label("stream_payload:SECRET")=="stream_payload"
    assert norm_label("directory[1].name")=="directory_name"
    assert norm_label("unknown unrelated")=="unclassified"
    return 0

def run_case(row,source,binary,rar2):
    r={"source_sha256":row["sha256"],"source_bytes":row["size"],
       "host":row["host"],"status":"NOT_EVALUATED","reason":"NOT_STARTED"}
    try:
        data=source.download(row)
    except Exception as e:
        r["reason"]=source.safe_error(e)
        return r
    r["status"]="SHA_VERIFIED"
    with tempfile.TemporaryDirectory(prefix="sk1-t959-") as tmp:
        folder=Path(tmp)
        inp=folder/"source.pub";cand=folder/"candidate.pub";rec=folder/"receipt.json"
        inp.write_bytes(data)
        try:
            p=subprocess.run([str(binary),str(inp),row["sha256"],str(cand),str(rec)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,check=False)
        except (OSError,subprocess.TimeoutExpired):
            r["status"]="PROBE_UNAVAILABLE";r["reason"]="BINARY_OR_TIMEOUT"
            return r
        if p.returncode!=0 or not rec.is_file():
            r["status"]="PROBE_UNAVAILABLE";r["reason"]="EXECUTION_FAILED"
            return r
        try:
            proof=json.loads(rec.read_text(encoding="utf-8"))
            status=proof.get("status")
            if status!="HOSTED_PASS":
                r["status"]="WRITER_NOT_ADMITTED"
                r["reason"]=status if status in {
                    "WRITER_BLOCKED","SOURCE_OPEN_BLOCKED","NO_ELIGIBLE_STORY",
                    "CANONICAL_EDIT_REJECTED","HASH_OR_NO_CHANGE","REOPEN_FAILED",
                    "TARGET_SEMANTIC_MISMATCH","SYID_OR_SIBLING_MISMATCH",
                    "REPLAY_OPEN_FAILED","REPLAY_APPLY_FAILED","REPLAY_WRITE_FAILED",
                    "REPLAY_BYTES_MISMATCH"} else "UNCLASSIFIED_PROBE_OUTCOME"
                if r["reason"]=="WRITER_BLOCKED":
                    code=proof.get("writer_code")
                    if (isinstance(code,str) and 0<len(code)<=64 and
                        all(c.islower() or c=="_" for c in code)):
                        r["writer_code"]=code
                return r
            import hashlib
            if not cand.is_file():raise ValueError("missing candidate")
            result=cand.read_bytes()
            if (len(result)!=proof["candidate_bytes"] or
                hashlib.sha256(result).hexdigest()!=proof["candidate_sha256"] or
                proof["source_sha256"]!=row["sha256"] or
                proof["source_bytes"]!=len(data) or
                proof["edit"]!="delete_one_ascii" or
                not all(proof[x] is True for x in (
                  "reader_reopened","syid_siblings_preserved",
                  "project_replay_byte_equal","source_immutable"))):
                raise ValueError("bad probe receipt")
            r["physical"]=physical(data,result)
            r["candidate_sha256"]=proof["candidate_sha256"]
            r["offset_utf16"]=proof["offset_utf16"]
            r["status"]="MEASURED";r["reason"]="OK"
        except (ValueError,KeyError,TypeError,AssertionError,ImportError):
            r["status"]="PHYSICAL_NOT_EVALUATED";r["reason"]="PARSER_OR_RECEIPT_MISMATCH"
    return r

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--rar2",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    root=args.rar2.resolve()
    sys.path.insert(0,str(root/"tools/corpus"))
    if args.self_test:return selftest()
    import olefile # noqa: F401  # needed for original rar2 CFB logical extraction
    source=legacy_source()
    rows=choose_rows(source)
    binary=root/"tools/native-pub-candidate-cli/target/release/examples/sk1_pub_t_959_one_way"
    if not binary.is_file():ap.error("pinned Writer probe executable missing")
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    plan={"schema":"sk1.pub-t-959.plan.v1","rar2_pin":PIN,
          "lalamu_pin":source.LALAMU_PIN,"source_manifest":source.NEW_MANIFEST,
          "prior_35_source_manifest":source.OLD_MANIFEST,
          "host_quotas":HOST_SIZES,
          "preselected_sha256":[r["sha256"] for r in rows],
          "source_budget_bytes":sum(r["size"] for r in rows),
          "scope":"single ASCII deletion, one new physical measurement per distinct source SHA",
          "native_publisher_acceptance":"NOT_EVALUATED"}
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    records=[]
    for row in rows:
        records.append(run_case(row,source,binary,root))
        (out/"records.json").write_text(json.dumps(records,indent=2)+"\n",encoding="utf-8")
    status=Counter(r["status"] for r in records)
    categories=Counter()
    changed_other=0; changed_quill=0; unclassified=0
    hosts=defaultdict(Counter)
    for r in records:
        hosts[r["host"]][r["status"]]+=1
        if r["status"]=="MEASURED":
            d=r["physical"];categories.update(d["raw_absolute_offset_categories"])
            changed_other+=int(d["logical_non_quill_streams_changed"]>0)
            changed_quill+=int(d["logical_quill_changed"])
            unclassified+=d["raw_unclassified_absolute_byte_count"]
    summary={
        "attempted":len(records),"source_verified":sum(r["status"] not in
              ("NOT_EVALUATED",) for r in records),
        "measured":status["MEASURED"],"status_counts":dict(sorted(status.items())),
        "per_host_statuses":{k:dict(sorted(v.items())) for k,v in sorted(hosts.items())},
        "measured_with_non_quill_stream_changes":changed_other,
        "measured_with_quill_stream_change":changed_quill,
        "raw_absolute_offset_category_totals":dict(sorted(categories.items())),
        "raw_unclassified_absolute_byte_total":unclassified
    }
    report={"schema":"sk1.pub-t-959.report.v1","rar2_pin":PIN,
            "native_publisher_acceptance":"NOT_EVALUATED",
            "product_pub_download_authorized":False,
            "summary":summary,"records":records}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"measured":summary["measured"],"attempted":EXPECTED,
                      "other_stream_change_cases":changed_other,
                      "physical_unclassified_bytes":unclassified},sort_keys=True))
    # CI execution succeeded only if at least eight independent source SHA.
    return 0 if summary["measured"]>=8 else 2

if __name__=="__main__":raise SystemExit(main())
