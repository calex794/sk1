#!/usr/bin/env python3
"""SK1 PUB-T-961 fail-closed safe schema and pre-registered Unicode control gate."""
from __future__ import annotations
from pathlib import Path
import hashlib
import importlib.util
import json
import re
import sys

HERE=Path(__file__).resolve().parent
SOURCE_SHA=re.compile(r"^[0-9a-f]{64}$")
CODE=re.compile(r"^[a-z_]{1,64}$")
GLYPHS=("LATIN1_E_ACUTE","CYRILLIC_ZHE","CJK_ZHONG","COMBINING_ACUTE","ASTRAL_GRIN")
BMP=GLYPHS[:4]
PASS_KEYS={"status","candidate_sha256","reader_semantic_reopen",
    "syid_siblings_preserved","project_replay_byte_equal","source_immutable"}
ALLOWED_STATUSES={"HOSTED_PASS","WRITER_BLOCKED","SOURCE_EDITOR_OPEN_BLOCKED",
    "STORY_ID_UNAVAILABLE","STORY_INPUT_MISMATCH","CANONICAL_EDIT_REJECTED",
    "WRITER_HASH_OR_NO_CHANGE","READER_REOPEN_BLOCKED",
    "OUTPUT_STORY_ID_UNAVAILABLE","TARGET_SEMANTIC_MISMATCH",
    "SYID_OR_SIBLING_MISMATCH","REPLAY_SOURCE_OPEN_BLOCKED",
    "PROJECT_REPLAY_BLOCKED","PROJECT_REPLAY_WRITER_BLOCKED",
    "PROJECT_REPLAY_BYTE_MISMATCH"}
SOURCE_FIELDS={"source_sha256","source_type","source_bytes","status","reason",
    "eligible_story_count","witness_count","records"}
CASE_FIELDS={"story_ordinal","slot","offset_utf16","story_utf16_len",
    "story_ascii_count","baseline_ASCII","unicode"}
DIFF_FIELDS={
    "schema","ascii_output_len","glyph_output_len",
    "ascii_quill_len","glyph_quill_len",
    "raw_output_diff_positions_equal_len",
    "quill_diff_byte_count_equal_len",
    "quill_diff_outside_expected_utf16_unit_equal_len",
    "quill_diff_outside_TEXT_equal_len",
    "TEXT_descriptor_same_offset_length",
    "TEXT_expected_UTF16_unit_present",
    "quill_diff_confined_to_one_UTF16_unit",
    "same_quill_descriptor_sequence",
    "same_SYID_header","same_story_SYID_sequence",
    "same_story_UTF16_lengths","source_quill_descriptor_count",
    "missing_CFB_paths","added_CFB_paths","changed_CFB_entry_kinds",
    "non_Quill_streams_checked","non_Quill_streams_changed",
    "all_non_Quill_streams_equal","publisher_native_acceptance",
    "product_PUB_download_authorized"
}
DIFF_BOOL={"TEXT_descriptor_same_offset_length",
    "TEXT_expected_UTF16_unit_present",
    "quill_diff_confined_to_one_UTF16_unit",
    "same_quill_descriptor_sequence","same_SYID_header",
    "same_story_SYID_sequence","same_story_UTF16_lengths",
    "all_non_Quill_streams_equal"}
DIFF_NULLABLE={"raw_output_diff_positions_equal_len",
    "quill_diff_byte_count_equal_len",
    "quill_diff_outside_expected_utf16_unit_equal_len",
    "quill_diff_outside_TEXT_equal_len"}
DIFF_SCALARS=DIFF_FIELDS-DIFF_BOOL-DIFF_NULLABLE-{
    "schema","publisher_native_acceptance","product_PUB_download_authorized"
}

def step_ok(s):
    assert type(s) is dict and s.get("status") in ALLOWED_STATUSES
    if s["status"]=="HOSTED_PASS":
        assert set(s)==PASS_KEYS
        assert SOURCE_SHA.fullmatch(s["candidate_sha256"])
        for key in PASS_KEYS-{"status","candidate_sha256"}:
            assert s[key] is True,key
    elif s["status"]=="WRITER_BLOCKED":
        assert set(s)=={"status","writer_code"}
        assert CODE.fullmatch(s["writer_code"])
    else:
        assert set(s)=={"status"}

def diff_ok(d):
    assert type(d) is dict and set(d)==DIFF_FIELDS,(set(d)-DIFF_FIELDS,DIFF_FIELDS-set(d))
    assert d["schema"]=="sk1.quill-val-pub-t-961.glyph-diff.v1"
    assert d["publisher_native_acceptance"]=="NOT_EVALUATED"
    assert d["product_PUB_download_authorized"] is False
    for k in DIFF_BOOL: assert type(d[k]) is bool,k
    for k in DIFF_SCALARS:
        assert type(d[k]) is int and 0<=d[k]<=12*1024*1024,k
    for k in DIFF_NULLABLE:
        assert d[k] is None or (type(d[k]) is int and 0<=d[k]<=12*1024*1024),k
    assert d["ascii_output_len"]>0 and d["glyph_output_len"]>0
    assert d["ascii_quill_len"]>0 and d["glyph_quill_len"]>0
    assert d["source_quill_descriptor_count"]>0
    assert d["non_Quill_streams_changed"]<=d["non_Quill_streams_checked"]
    x=(d["missing_CFB_paths"]==d["added_CFB_paths"]==
        d["changed_CFB_entry_kinds"]==d["non_Quill_streams_changed"]==0)
    assert d["all_non_Quill_streams_equal"]==x
    if d["ascii_quill_len"]==d["glyph_quill_len"]:
        for k in ("quill_diff_byte_count_equal_len",
            "quill_diff_outside_expected_utf16_unit_equal_len",
            "quill_diff_outside_TEXT_equal_len"):
            assert type(d[k]) is int,k
        assert d["quill_diff_outside_expected_utf16_unit_equal_len"]<=d[
            "quill_diff_byte_count_equal_len"]
        assert d["quill_diff_outside_TEXT_equal_len"]<=d[
            "quill_diff_byte_count_equal_len"]
    else:
        for k in ("quill_diff_byte_count_equal_len",
            "quill_diff_outside_expected_utf16_unit_equal_len",
            "quill_diff_outside_TEXT_equal_len"):
            assert d[k] is None
    if d["ascii_output_len"]==d["glyph_output_len"]:
        assert type(d["raw_output_diff_positions_equal_len"]) is int
    else:
        assert d["raw_output_diff_positions_equal_len"] is None
    confined=(d["ascii_quill_len"]==d["glyph_quill_len"]
        and d["TEXT_expected_UTF16_unit_present"]
        and d["quill_diff_byte_count_equal_len"] in (1,2)
        and d["quill_diff_outside_expected_utf16_unit_equal_len"]==0)
    assert d["quill_diff_confined_to_one_UTF16_unit"]==confined
    if confined:
        assert d["quill_diff_outside_TEXT_equal_len"]==0
        assert d["TEXT_descriptor_same_offset_length"]

def check(root:Path):
    mod_spec=importlib.util.spec_from_file_location("sk1_t961_runner",HERE/"run.py")
    assert mod_spec and mod_spec.loader
    runner=importlib.util.module_from_spec(mod_spec)
    mod_spec.loader.exec_module(runner)
    witness=runner.read_witnesses()
    plan=json.loads((root/"plan.json").read_text(encoding="utf8"))
    rows=json.loads((root/"records.json").read_text(encoding="utf8"))
    report=json.loads((root/"report.json").read_text(encoding="utf8"))
    assert set(plan)=={"schema","upstream_commit","previous_exp956_scientific_sha",
        "previous_exp956_zip_sha256","witness_sha256","source_manifest",
        "source_sha256","scope","test_classes","predeclared_slot_count",
        "product_authorized"}
    assert plan["schema"]=="sk1.quill-val-pub-t-961.plan.v1"
    assert plan["upstream_commit"]==runner.UPSTREAM
    assert plan["previous_exp956_scientific_sha"]==runner.PARENT_956
    assert plan["previous_exp956_zip_sha256"]==runner.PARENT_ZIP
    assert plan["witness_sha256"]==runner.WITNESS_SHA
    assert plan["source_sha256"]==list(witness)
    assert plan["test_classes"]==list(GLYPHS)
    assert plan["predeclared_slot_count"]==77
    assert plan["product_authorized"] is False
    assert set(report)=={"schema","upstream_commit","witness_sha256",
        "publisher_native_acceptance","product_PUB_download_authorized",
        "summary","records"}
    assert report["schema"]=="sk1.quill-val-pub-t-961.report.v1"
    assert report["upstream_commit"]==runner.UPSTREAM
    assert report["witness_sha256"]==runner.WITNESS_SHA
    assert report["publisher_native_acceptance"]=="NOT_EVALUATED"
    assert report["product_PUB_download_authorized"] is False
    assert report["records"]==rows
    assert type(rows) is list and len(rows)==13
    seen=set()
    per_glyph={kind:0 for kind in GLYPHS}
    n=0
    for r in rows:
        assert type(r) is dict and set(r)==SOURCE_FIELDS
        sha=r["source_sha256"]
        assert SOURCE_SHA.fullmatch(sha) and sha in witness and sha not in seen
        seen.add(sha)
        assert r["source_type"] in {"github","institutional-web"}
        assert type(r["source_bytes"]) is int and 0<r["source_bytes"]<=12*1024*1024
        assert r["status"]=="EVALUATED" and r["reason"]=="SAFE_READONLY_DIFF"
        assert type(r["eligible_story_count"]) is int and 1<=r["eligible_story_count"]<=3
        assert r["witness_count"]==len(witness[sha])==len(r["records"])
        got=set()
        for p in r["records"]:
            assert type(p) is dict and set(p)==CASE_FIELDS
            sid=p["story_ordinal"]
            expected=[sid,p["slot"],p["offset_utf16"],
                p["story_utf16_len"],p["story_ascii_count"]]
            assert expected in witness[sha]
            assert tuple(expected) not in got
            got.add(tuple(expected))
            assert 0<=sid<r["eligible_story_count"]
            assert 0<=p["offset_utf16"]<p["story_utf16_len"]
            step_ok(p["baseline_ASCII"])
            assert p["baseline_ASCII"]["status"]=="HOSTED_PASS"
            assert type(p["unicode"]) is dict and set(p["unicode"])==set(GLYPHS)
            for glyph in GLYPHS:
                v=p["unicode"][glyph]
                assert type(v) is dict and set(v)=={"step","vs_ascii_reference"}
                step_ok(v["step"])
                per_glyph[glyph]+=1
                if v["step"]["status"]=="HOSTED_PASS" and glyph in BMP:
                    diff_ok(v["vs_ascii_reference"])
                else:
                    assert v["vs_ascii_reference"] is None
            n+=1
        assert len(got)==len(witness[sha])
    assert seen==set(witness) and n==77 and all(x==77 for x in per_glyph.values())
    assert report["summary"]==runner.summarize(rows)
    assert report["summary"]["evaluated_sources"]==13
    assert report["summary"]["evaluated_slot_count"]==77
    print("SK1 PUB-T-961 VERIFIED: 13 source-SHA, 77 predeclared Story-offsets, 385 Unicode arms")

if __name__=="__main__":
    assert len(sys.argv)==2
    check(Path(sys.argv[1]))
