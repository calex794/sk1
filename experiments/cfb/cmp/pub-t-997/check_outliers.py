#!/usr/bin/env python3
import json,sys
from pathlib import Path
base=json.loads(Path(sys.argv[2]).read_text())
j=json.loads(Path(sys.argv[1]).read_text())
assert j["schema"]=="sk1-pub-cmp-t997-outliers/v1"
assert j["task_id"]==base["task_id"]=="PUB-T-997"
assert j["rar2_source_commit"]==base["rar2_source_commit"]
assert j["poi_commit"]==base["poi_source_commit"]
assert j["native_publisher_evaluated"] is False
assert j["physical_source_is_not_native_oracle"] is True
names={"SampleNewsletter.pub","Sample98.pub","Sample2000.pub","SampleBrochure.pub"}
assert set(j["rows"])==names
parent={r["fixture"]:r for r in base["rows"]}
for name,row in j["rows"].items():
    p=parent[name]
    assert row["input_sha256"]==p["source_sha256"]
    assert row["source_byte_len"]==p["source_byte_len"]
    assert row["source_physical_version"]==p["source_physical_version"]
    assert row["source_unchanged"] and row["odg_content_hash_same_as_parent"]
    assert row["odg_styles_hash_same_as_parent"]
    assert row["quill_parse_status"]=="DECODED_TEXT", (name,row["quill_parse_status"])
    assert len(row["lo_page_statistics"])==p["libreoffice"]["draw_page_count"]
    assert sum(q["token_count"] for q in row["lo_page_statistics"])==p["text_overlap"]["libreoffice_tokens"]
    assert sum(q["nonspace_text_characters"] for q in row["lo_page_statistics"])==p["libreoffice"]["nonspace_text_characters"]
    assert all(type(q[k]) is int and q[k]>=0 for q in row["lo_page_statistics"] for k in
               ("token_count","nonspace_text_characters","text_paragraph_count","shape_nodes"))
    t=row["raw_vs_engines"]
    assert t["reader_story_tokens"]==p["text_overlap"]["reader_tokens"]
    assert t["lo_visible_tokens"]==p["text_overlap"]["libreoffice_tokens"]
    assert t["reader_lo_shared"]==p["text_overlap"]["shared_tokens_min_count"]
    assert t["quill_reader_shared"]+t["reader_extra_vs_quill"]==t["reader_story_tokens"]
    assert t["quill_lo_shared"]+t["lo_extra_vs_quill"]==t["lo_visible_tokens"]
    assert t["physical_quill_tokens"]-t["quill_reader_shared"]==t["reader_missing_vs_quill"]
    assert t["physical_quill_tokens"]-t["quill_lo_shared"]==t["lo_missing_vs_quill"]
print("SK1 T997 targeted Quill vs Reader vs ODG discriminator PASS")
