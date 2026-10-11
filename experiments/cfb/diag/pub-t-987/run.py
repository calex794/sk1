#!/usr/bin/env python3
"""PUB-T-987 — source-safe bridge from entire pinned natural-corpus census
to the inherited, unmodified real Writer two-arm inverse experiment.
"""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

RAR2_PIN="703808408fd919e564a90cdc236e81db3c04af8b"
DONOR_PIN="87094c23e2a9eaa2aa9e95d72ec52f72ef109f11"
DONOR_TREE="8146fa9fdd2f577ebe02bc7205a61bb14e20d3e7"
T984_PIN="14ac75ae0346b3bdbeeada110e1f463dda6cbb27"
T963_PIN="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
T971_PIN="cd38c8d6a545737f9f99821076340505db5e149c"
EXPECTED=625
SOURCE_SAFE={"source_sha256","source_bytes","status","syid_header","syid_count",
 "syid_max_live","low_byte","is_fe_ff_boundary","original_bytes_immutable"}
STATUS={"NATURAL_SYID_PARSED","QUILL_STREAM_UNAVAILABLE",
        "QUILL_SYID_PARSE_BLOCKED","NOT_CFB"}
SHA_RE=re.compile(r"^[a-f0-9]{64}$")
WRITER_SCHEMA="sk1.cfb-diag-pub-t-984.inverse.v1"

def checksum(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def load_census(path:Path):
    c=json.loads(path.read_text(encoding="utf-8"))
    assert set(c)=={"schema","planned_pub","source_immutable_sha_verified","rows"}
    assert c["schema"]=="sk1.cfb-diag-pub-t-987.census.v1"
    assert c["planned_pub"]==c["source_immutable_sha_verified"]==EXPECTED
    assert len(c["rows"])==EXPECTED
    sha_list=[]
    for row in c["rows"]:
        assert set(row)==SOURCE_SAFE
        assert isinstance(row["source_sha256"],str) and SHA_RE.fullmatch(row["source_sha256"])
        assert type(row["source_bytes"]) is int and 0<row["source_bytes"]<=128*1024*1024
        assert row["status"] in STATUS
        assert row["original_bytes_immutable"] is True
        parsed=row["status"]=="NATURAL_SYID_PARSED"
        if parsed:
            h=row["syid_header"]
            assert type(h) is int and 0<=h<=0xffffffff
            assert type(row["syid_count"]) is int and 0<=row["syid_count"]<=0xffffffff
            assert row["syid_max_live"] is None or (
                type(row["syid_max_live"]) is int and 0<=row["syid_max_live"]<=0xffffffff)
            assert type(row["low_byte"]) is int and row["low_byte"]==h&255
            assert row["is_fe_ff_boundary"] is (row["low_byte"] in (0xfe,0xff))
        else:
            assert all(row[key] is None for key in (
                "syid_header","syid_count","syid_max_live","low_byte"))
            assert row["is_fe_ff_boundary"] is False
        sha_list.append(row["source_sha256"])
    assert sha_list==sorted(set(sha_list)), "input inventory was not a sorted SHA-unique complete cohort"
    return c

def writer_probe(row:dict,donor:Path,binary:Path):
    sha=row["source_sha256"]
    candidate=donor/(sha+".pub")
    # Verify exact source bytes a second time immediately before Writer.
    if not candidate.is_file() or checksum(candidate.read_bytes())!=sha:
        return {"status":"SOURCE_SHA_DRIFT","probe":None}
    with tempfile.TemporaryDirectory(prefix="sk1-pub-t987-writer-") as td:
        receipt=Path(td)/"safe_receipt.json"
        try:
            p=subprocess.run([str(binary),str(candidate),sha,str(receipt)],
                 capture_output=True,check=False,timeout=360)
        except (OSError,subprocess.TimeoutExpired):
            return {"status":"WRITER_PROCESS_UNAVAILABLE","probe":None}
        if p.returncode!=0 or not receipt.is_file():
            return {"status":"WRITER_PROCESS_FAILED","probe":None}
        try:
            r=json.loads(receipt.read_text(encoding="utf-8"))
        except (OSError,ValueError):
            return {"status":"WRITER_RECEIPT_UNREADABLE","probe":None}
    if (r.get("schema")!=WRITER_SCHEMA or
        r.get("source_sha256")!=sha or r.get("source_bytes")!=row["source_bytes"] or
        r.get("publisher_native_acceptance")!="NOT_EVALUATED" or
        r.get("product_pub_download_authorized") is not False):
        return {"status":"WRITER_RECEIPT_INVALID","probe":None}
    if r.get("source_syid_first_dword") is not None and r["source_syid_first_dword"]!=row["syid_header"]:
        return {"status":"WRITER_SOURCE_SYID_DRIFT","probe":None}
    return {"status":"RECEIPT_AVAILABLE","probe":r}

def byte_diff_u32(before:int,after:int)->int:
    return sum(a!=b for a,b in zip(before.to_bytes(4,"little"),after.to_bytes(4,"little")))

def summarize(rows:list[dict])->dict:
    origin=Counter()
    seen=[]
    low_bytes=Counter()
    targets=[]
    writer_probe_states=Counter()
    writer_admit=Counter()
    outcomes=Counter()
    finals=0
    finals_sources=set()
    final_model_good=0
    final_changed=Counter()
    counterexamples=[]
    for row in rows:
        origin[row["status"]]+=1
        if row["status"]=="NATURAL_SYID_PARSED":
            seen.append(row["syid_header"])
            low_bytes[str(row["low_byte"])]+=1
        if not row["is_fe_ff_boundary"]:
            continue
        selection={"source_sha256":row["source_sha256"],
            "initial_syid_header":row["syid_header"],
            "low_byte":row["low_byte"],
            "source_bytes":row["source_bytes"],
            "writer_attempt_status":row["writer"]["status"],
            "writer_probe_result":None,
            "original_both_writer_pass":0,
            "inverse_complete":0,
            "raw_model_matched":0}
        writer_probe_states[row["writer"]["status"]]+=1
        p=row["writer"]["probe"]
        if p is None:
            targets.append(selection); continue
        selection["writer_probe_result"]=p["result"]
        writer_admit[p["result"]]+=1
        if p["result"]!="EVALUATED":
            targets.append(selection);continue
        for story in p["stories"]:
            for pair in story["pairs"]:
                if not pair["both_single_pass"]:
                    outcomes["INITIAL_PAIR_BLOCKED"]+=1
                    continue
                selection["original_both_writer_pass"]+=1
                for arm,key in (("insert_then_delete","insert_delete"),
                                 ("delete_then_insert","delete_insert")):
                    step=pair[arm]
                    outcomes[step["status"]]+=1
                    if step["status"]!="HOSTED_PASS":continue
                    finals+=1
                    finals_sources.add(row["source_sha256"])
                    selection["inverse_complete"]+=1
                    cfb=pair[key+"_cfb"]
                    raw=pair[key+"_raw"]
                    old=row["syid_header"]
                    future=old+2 if old<=0xfffffffd else None
                    expected=byte_diff_u32(old,future) if future is not None else None
                    ok=(future is not None and
                        cfb["source_syid_first_dword"]==old and
                        cfb["final_syid_first_dword"]==future and
                        cfb["syid_first_dword_delta"]==2 and
                        raw["equal_length"] is True and raw["extra_bytes"]==0 and
                        raw["changed_same_offset_bytes"]==expected and
                        cfb["syid_first_dword_changed_bytes"]==expected and
                        cfb["quill_differing_byte_positions_equal_len"]==expected and
                        cfb["quill_changed_bytes_outside_syid_first_dword"]==0 and
                        cfb["same_quill_TEXT_payload_bytes"] is True and
                        cfb["same_quill_story_syid_sequence"] is True and
                        cfb["non_quill_streams_changed"]==0 and
                        cfb["missing_cfb_paths"]==0 and
                        cfb["added_cfb_paths"]==0 and
                        cfb["cfb_entry_type_changes"]==0 and
                        cfb["matched_descriptor_sequence"] is True)
                    final_changed[str(raw["changed_same_offset_bytes"])]+=1
                    if ok:
                        final_model_good+=1
                        selection["raw_model_matched"]+=1
                    else:
                        counterexamples.append({
                            "source_sha256":row["source_sha256"],
                            "story_ordinal":story["story_ordinal"],
                            "arm":arm,
                            "expected_changed_bytes":expected,
                            "observed_changed_bytes":raw["changed_same_offset_bytes"],
                            "observed_syid_delta":cfb["syid_first_dword_delta"],
                            "quill_outside_syid":cfb["quill_changed_bytes_outside_syid_first_dword"],
                            "non_quill_streams_changed":cfb["non_quill_streams_changed"]
                        })
        targets.append(selection)
    return {
      "source_sha_verified":len(rows),
      "source_status_counts":dict(sorted(origin.items())),
      "original_syid_headers_observed":len(seen),
      "natural_min_header":min(seen) if seen else None,
      "natural_max_header":max(seen) if seen else None,
      "natural_low_byte_histogram":dict(sorted(low_bytes.items(),key=lambda x:int(x[0]))),
      "natural_fe_ff_count":len(targets),
      "natural_fe_ff_candidates":targets,
      "writer_attempt_status":dict(sorted(writer_probe_states.items())),
      "writer_probe_result":dict(sorted(writer_admit.items())),
      "writer_inverse_status":dict(sorted(outcomes.items())),
      "inverse_final_files":finals,
      "inverse_final_distinct_sha":len(finals_sources),
      "inverse_final_exact_syid_model":final_model_good,
      "inverse_final_raw_bytes_by_count":dict(sorted(final_changed.items())),
      "counterexamples":counterexamples,
      "native_publisher_acceptance":"NOT_EVALUATED"
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--rar2",type=Path,required=True)
    ap.add_argument("--donor",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    root=a.rar2.resolve(strict=True)
    donor=a.donor.resolve(strict=True)/"pub-corpus/corpus/native/unclassified"
    output=a.output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    example=root/"tools/native-pub-candidate-cli/target/release/examples"
    scanner=example/"sk1_pub_t_987_natural_syid_census"
    writer=example/"sk1_pub_t_984_inverse_cfb"
    if not scanner.is_file() or not writer.is_file():
        ap.error("approved Reader+Writer probes are missing")
    with tempfile.TemporaryDirectory(prefix="sk1-pub-t987-in-memory-") as td:
        census=Path(td)/"natural.json"
        cp=subprocess.run([str(scanner),str(donor),str(census)],
                          capture_output=True,check=False,timeout=900)
        if cp.returncode or not census.is_file():
            raise RuntimeError("pinned Rust original 625 source census failed")
        original=load_census(census)
    rows=original["rows"]
    plan={
      "schema":"sk1.cfb-diag-pub-t-987.plan.v1",
      "corpus_repo":"Lalalalendia/lalamu",
      "corpus_commit":DONOR_PIN,
      "corpus_native_tree":DONOR_TREE,
      "corpus_exact_sha_count":EXPECTED,
      "original_sha_list_lf_sha256":checksum(("\n".join(x["source_sha256"] for x in rows)+"\n").encode()),
      "reader_writer_pin":RAR2_PIN,
      "inverse_writer_science_pin":T984_PIN,
      "inverse_writer_parent_t963":T963_PIN,
      "inverse_writer_parent_t971":T971_PIN,
      "natural_target_low_bytes":[254,255],
      "writer_policy":"all natural parsed FE/FF, no post-hoc selection",
      "previous_1050_matched_mature_cohort_note":"same 396 mature SHA as 625, legacy remainder not a new mature cohort",
      "native_publisher_acceptance":"NOT_EVALUATED",
      "raw_original_or_candidate_pub_export":False
    }
    (output/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    for row in rows:
        row["writer"]=(
            writer_probe(row,donor,writer) if row["is_fe_ff_boundary"]
            else None
        )
    (output/"records.json").write_text(json.dumps(rows,indent=2)+"\n",encoding="utf-8")
    final={
        "schema":"sk1.cfb-diag-pub-t-987.report.v1",
        "plan_sha256":checksum((output/"plan.json").read_bytes()),
        "source_pub_count":EXPECTED,
        "summary":summarize(rows),
        "records":rows,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "raw_original_or_candidate_pub_export":False
    }
    (output/"report.json").write_text(json.dumps(final,indent=2)+"\n",encoding="utf-8")
    summary=final["summary"]
    print(json.dumps({"all_source_sha_verified":summary["source_sha_verified"],
       "syid_headers":summary["original_syid_headers_observed"],
       "natural_fe_ff":summary["natural_fe_ff_count"],
       "writer_inverse_complete":summary["inverse_final_files"],
       "physical_syid_model_exact":summary["inverse_final_exact_syid_model"],
       "counterexamples":len(summary["counterexamples"])}))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
