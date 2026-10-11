#!/usr/bin/env python3
"""Independent closed-corpus aggregation verification (no raw source data)."""
from collections import Counter
import json
from pathlib import Path
import sys

report=json.loads(Path(sys.argv[1]).read_text())
manifest=json.loads(Path(sys.argv[2]).read_text())
assert report["schema"]=="sk1-pub-cmp-t997/v1"
assert report["task_id"]=="PUB-T-997"
assert report["rar2_source_commit"]=="b224a614af48c273b2d4bc0881793cf0217cc16d"
assert report["rar2_corpus_manifest_git_blob"]=="4e77d912e7a104cc192be5e6504892c295c1db01"
assert report["official_viewer_receipt_git_blob"]=="d57ea6b07e62751b65790238b1a374275dbb2199"
assert report["poi_source_commit"]==manifest["upstream"]["commit"]
assert report["visual_fidelity_proven"] is False
assert report["publisher_native_evaluated"] is False
assert report["rust_probe"]=="ephemeral_real_pub_viewer_open_pub_geometry"
assert len(report["rows"])==len(manifest["fixtures"])==22
expect={f["name"]:f for f in manifest["fixtures"]}
seen=set()
for row in report["rows"]:
    n=row["fixture"]
    assert n not in seen
    seen.add(n)
    e=expect[n]
    assert (row["source_sha256"],row["source_byte_len"],row["semantic"],row["manifest_family"])==(
        e["sha256"],e["byte_len"],e["semantic"],e["family"])
    assert row.get("source_unchanged") is True
    r,l=row["reader"],row["libreoffice"]
    assert r["status"]=="EXECUTED" and l["status"]=="EXECUTED",n
    assert type(r["opened"]) is bool and type(l["opened"]) is bool
    expected=(
      "BOTH_OPEN" if r["opened"] and l["opened"] else
      "READER_ONLY" if r["opened"] else
      "LIBREOFFICE_ONLY" if l["opened"] else "NEITHER_OPEN"
    )
    assert row["comparison"]==expected
    if r["opened"]:
        assert len(r["structural_receipt_sha256"])==64
        for f in ["viewer_page_count","scene_node_count","story_count",
                  "typography_run_count","image_resource_count","paint_node_count",
                  "story_nonspace_characters","story_unicode_characters"]:
            assert type(r[f]) is int and r[f]>=0
    if l["opened"]:
        assert len(l["content_xml_sha256"])==len(l["styles_xml_sha256"])==64
        for f in ["draw_page_count","draw_shape_nodes","draw_image_elements",
                  "text_paragraph_count","nonspace_text_characters","text_word_count"]:
            assert type(l[f]) is int and l[f]>=0
    if expected=="BOTH_OPEN":
        t=row["text_overlap"]
        assert t["reader_tokens"]>=t["shared_tokens_min_count"]>=0
        assert t["libreoffice_tokens"]>=t["shared_tokens_min_count"]>=0
        assert row["page_count_equal_when_both_open"]==(
          r["viewer_page_count"]==l["draw_page_count"])
    if "repeat" in row:
        assert n in ("Simple.pub","Sample98.pub")
        assert all(row["repeat"].values())
assert seen==set(expect)
assert report["negative_control"]["changed_physical_bytes"]==1
assert report["negative_control"]["reader_rejected"]
assert report["negative_control"]["libreoffice_rejected"]
assert report["negative_control"]["not_a_semantic_fixture"] is True
sm=report["summary"]
assert sm["all_public_source_fixtures"]==22
assert sm["semantic_fixture_count"]==21
assert sm["adversarial_fixture_count"]==1
sem=[r for r in report["rows"] if r["semantic"]]
counts=Counter(r["comparison"] for r in sem)
assert sm["both_semantic_opened"]==counts["BOTH_OPEN"]
assert sm["reader_only_semantic"]==counts["READER_ONLY"]
assert sm["lo_only_semantic"]==counts["LIBREOFFICE_ONLY"]
assert sm["neither_semantic"]==counts["NEITHER_OPEN"]
assert sm["not_evaluated_semantic"]==0
assert sm["reader_semantic_opened"]==counts["BOTH_OPEN"]+counts["READER_ONLY"]
assert sm["lo_semantic_opened"]==counts["BOTH_OPEN"]+counts["LIBREOFFICE_ONLY"]
assert sum(counts.values())==21
both=[r for r in sem if r["comparison"]=="BOTH_OPEN"]
assert sm["both_open_page_count_equal"]==sum(r["page_count_equal_when_both_open"] for r in both)
assert sm["both_open_page_count_different"]==sum(not r["page_count_equal_when_both_open"] for r in both)
assert sm["both_open_with_nonzero_token_intersection"]==sum(
    r["text_overlap"]["shared_tokens_min_count"]>0 for r in both)
assert sm["source_immutability_count"]==22
assert sm["sampled_repeat_count"]==2
for row in report["rows"]:
    assert row.get("source_physical_version") in ("0x2c","0x22","unknown_contents_magic","cfb_without_contents","unsupported_cfb")
for family,counts2 in sm["by_physical_family"].items():
    sampled=[r for r in sem if r["source_physical_version"]==family]
    assert sum(counts2.values())==len(sampled)
    assert counts2==dict(Counter(r["comparison"] for r in sampled))
print("SK1 T997 independent paired source-safe benchmark gate PASS: ",
      sm["reader_semantic_opened"],"Reader; ",sm["lo_semantic_opened"],"LibreOffice; ",
      sm["both_semantic_opened"],"both; native NOT_EVALUATED",sep="")
