#!/usr/bin/env python3
"""PUB-T-961: immutable source-safe Unicode glyph width/equality experiment."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from collections import Counter
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
BASE=HERE.parents[3]
ORIGINAL=BASE/"sk1-exp-001"/"run.py"
SPEC=importlib.util.spec_from_file_location("sk1_exp001_original_safe_intake",ORIGINAL)
assert SPEC and SPEC.loader
source=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)

UPSTREAM="703808408fd919e564a90cdc236e81db3c04af8b"
PARENT_956="08abf5c7d92fb5ca56fd3ff84009309120fcf52c"
PARENT_ZIP="afad2b913bf2dfccf06af213f09142e2cc0b139748a5174ae9bc50129f9ed427"
WITNESS_SHA="c7a74f2fe7e1f72b4400628705d9f5eb7640ba95c9a1ff5b8292bddd579d904b"
GLYPHS=("LATIN1_E_ACUTE","CYRILLIC_ZHE","CJK_ZHONG","COMBINING_ACUTE","ASTRAL_GRIN")
BMP=GLYPHS[:4]
TARGET_BINARY="sk1_pub_t_961_unicode"

def read_witnesses()->dict:
    data=(HERE/"witnesses.json").read_bytes()
    assert hashlib.sha256(data).hexdigest()==WITNESS_SHA,"pre-registration changed"
    rows=json.loads(data)
    assert type(rows) is dict and len(rows)==13
    assert sum(len(v) for v in rows.values())==77
    identities=set()
    counts=Counter()
    for sha,group in rows.items():
        assert len(sha)==64 and all(ch in "0123456789abcdef" for ch in sha)
        assert type(group) is list and 1<=len(group)<=9
        for ordinal,slot,offset,length,ascii_count in group:
            assert type(ordinal) is int and 0<=ordinal<3
            assert slot in ("F","S","M")
            assert type(offset) is int and type(length) is int and type(ascii_count) is int
            assert 0<=offset<length and 0<ascii_count<=length
            identity=(sha,ordinal,slot,offset)
            assert identity not in identities,"duplicate sample"
            identities.add(identity)
            counts[slot]+=1
    assert counts=={"F":9,"S":34,"M":34},counts
    return rows

def run_source(row:dict,oracle:Path,witness_file:Path)->dict:
    result={
        "source_sha256":row["sha256"],
        "source_type":row["source_type"],
        "source_bytes":row["size"],
        "status":"NOT_EVALUATED","reason":"NOT_STARTED"
    }
    try:
        data=source.retrieve(row["url"],min(row["size"]+1,source.MAX_FILE_BYTES))
        if len(data)!=row["size"] or source.digest(data)!=row["sha256"]:
            result["reason"]="SOURCE_SHA_SIZE_DRIFT";return result
        if not data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            result["reason"]="NOT_CFB";return result
        with tempfile.TemporaryDirectory(prefix="sk1-961-") as d:
            pub=Path(d)/"source.pub"
            receipt=Path(d)/"safe.json"
            pub.write_bytes(data)
            proc=subprocess.run([str(oracle),str(pub),row["sha256"],
                str(witness_file),str(receipt)],stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,timeout=540)
            if proc.returncode or not receipt.is_file():
                result["reason"]="RUST_EVIDENCE_UNAVAILABLE";return result
            x=json.loads(receipt.read_text(encoding="utf8"))
        if (x.get("schema")!="sk1.quill-val-pub-t-961.source.v1"
            or x.get("source_sha256")!=row["sha256"]
            or x.get("source_bytes")!=row["size"]
            or x.get("publisher_native_acceptance")!="NOT_EVALUATED"
            or x.get("product_PUB_download_authorized") is not False):
            result["reason"]="MALFORMED_SOURCE_RECEIPT";return result
        result.update(status="EVALUATED",reason="SAFE_READONLY_DIFF",
            eligible_story_count=x["eligible_story_count"],
            witness_count=x["witness_count"],
            records=x["records"])
    except Exception:
        # The exception may contain a URL/Story or source path; do not expose.
        result["reason"]="BOUNDED_INPUT_OR_RUNTIME_ERROR"
    return result

def summarize(rows:list[dict])->dict:
    status=Counter()
    kinds={name:Counter() for name in GLYPHS}
    sources_by_glyph={name:set() for name in GLYPHS}
    examples=[]
    offsets=0
    for row in rows:
        status[row["status"]]+=1
        if row["status"]!="EVALUATED":continue
        for item in row["records"]:
            offsets+=1
            for name in GLYPHS:
                observation=item["unicode"][name]
                s=observation["step"]
                kinds[name]["attempted"]+=1
                kinds[name]["status_"+s["status"]]+=1
                sources_by_glyph[name].add(row["source_sha256"])
                if s["status"]=="WRITER_BLOCKED":
                    kinds[name]["guard_"+s["writer_code"]]+=1
                d=observation["vs_ascii_reference"]
                if d is not None:
                    kinds[name]["compared"]+=1
                    for flag in ("quill_diff_confined_to_one_UTF16_unit",
                        "same_SYID_header","same_story_SYID_sequence",
                        "same_story_UTF16_lengths",
                        "all_non_Quill_streams_equal",
                        "same_quill_descriptor_sequence",
                        "TEXT_expected_UTF16_unit_present"):
                        kinds[name][flag+"_true"]+=int(d[flag] is True)
                    kinds[name]["non_Quill_streams_checked"]+=d["non_Quill_streams_checked"]
                    kinds[name]["non_Quill_streams_changed"]+=d["non_Quill_streams_changed"]
                    kinds[name]["extra_Quill_bytes_differ"]+=d[
                        "quill_diff_outside_expected_utf16_unit_equal_len"] or 0
                    kinds[name]["whole_file_same_length"]+=int(
                        d["ascii_output_len"]==d["glyph_output_len"])
                    if not (
                        d["quill_diff_confined_to_one_UTF16_unit"] and
                        d["same_SYID_header"] and
                        d["same_quill_descriptor_sequence"] and
                        d["all_non_Quill_streams_equal"]
                    ) and len(examples)<40:
                        examples.append({
                            "source_sha256":row["source_sha256"],
                            "story_ordinal":item["story_ordinal"],
                            "slot":item["slot"],
                            "offset_utf16":item["offset_utf16"],
                            "glyph_class":name,
                            "reader_status":s["status"],
                            "utf16_confined":d["quill_diff_confined_to_one_UTF16_unit"],
                            "other_streams_preserved":d["all_non_Quill_streams_equal"],
                        })
    return {
        "evaluated_sources":status["EVALUATED"],
        "sources_by_status":dict(sorted(status.items())),
        "predeclared_source_count":13,
        "predeclared_slot_count":77,
        "evaluated_slot_count":offsets,
        "glyph_matrix":{k:{"distinct_sources":len(sources_by_glyph[k]),
            "counts":dict(sorted(v.items()))}for k,v in kinds.items()},
        "source_safe_counterexamples":examples,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "writer_changed":False,
    }

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--rar2",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    rar2=args.rar2.resolve(strict=True)
    oracle=rar2/"tools/native-pub-candidate-cli/target/release/examples"/TARGET_BINARY
    if not oracle.is_file():p.error("read-only experimental Rust example not compiled")
    witnesses=read_witnesses()
    all_sources=source.candidates(source.load_manifest(None))
    if len(all_sources)!=26 or len({x["sha256"] for x in all_sources})!=26:
        raise RuntimeError("original manifest admission drift")
    selected=[r for r in all_sources if r["sha256"] in witnesses]
    if len(selected)!=13 or {r["sha256"] for r in selected}!=set(witnesses):
        raise RuntimeError("pre-registered sources cannot be matched to public manifest")
    if sum(r["size"] for r in selected)>source.MAX_TOTAL_BYTES:
        raise RuntimeError("total source byte budget exceeded")
    out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=True)
    plan={
        "schema":"sk1.quill-val-pub-t-961.plan.v1",
        "upstream_commit":UPSTREAM,
        "previous_exp956_scientific_sha":PARENT_956,
        "previous_exp956_zip_sha256":PARENT_ZIP,
        "witness_sha256":WITNESS_SHA,
        "source_manifest":source.MANIFEST_URL,
        "source_sha256":list(witnesses),
        "scope":"77 matched ASCII source+Story+UTF16 slots, different Unicode BMP glyph widths; no Publisher native",
        "test_classes":list(GLYPHS),
        "predeclared_slot_count":77,
        "product_authorized":False,
    }
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf8")
    observed=[]
    for r in selected:
        observed.append(run_source(r,oracle,HERE/"witnesses.json"))
        (out/"records.json").write_text(json.dumps(observed,indent=2)+"\n",encoding="utf8")
    s=summarize(observed)
    report={
        "schema":"sk1.quill-val-pub-t-961.report.v1",
        "upstream_commit":UPSTREAM,
        "witness_sha256":WITNESS_SHA,
        "publisher_native_acceptance":"NOT_EVALUATED",
        "product_PUB_download_authorized":False,
        "summary":s,"records":observed
    }
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
    passed=(s["evaluated_sources"]==13 and s["evaluated_slot_count"]==77
        and all(s["glyph_matrix"][name]["counts"].get("attempted")==77 for name in GLYPHS)
        and all(r["status"]=="EVALUATED" and
                r["witness_count"]==len(witnesses[r["source_sha256"]])
                for r in observed))
    if not passed:
        print(json.dumps({"research_result":"INCOMPLETE",
            "sources":s["sources_by_status"],"slots":s["evaluated_slot_count"]}))
        return 2
    print(json.dumps({"research_result":"COMPLETE",
        "witnesses":s["evaluated_slot_count"],"glyph_matrix":s["glyph_matrix"]},
        sort_keys=True))
    return 0

if __name__=="__main__":
    sys.exit(main())
