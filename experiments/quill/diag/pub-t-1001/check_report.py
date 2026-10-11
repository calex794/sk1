#!/usr/bin/env python3
"""Independent T1001 source-safe JSON validation, no PUB inputs."""
from __future__ import annotations
import json
from pathlib import Path
import sys

def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_report.py JSON")
    r = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert r["schema"] == "sk1-pub-t1001-stsh1-natural-census/v1"
    assert r["task_id"] == "PUB-T-1001"
    assert r["rar2_commit"] == "b224a614af48c273b2d4bc0881793cf0217cc16d"
    assert r["rar2_manifest_git_blob"] == "4e77d912e7a104cc192be5e6504892c295c1db01"
    assert r["prior_t994_commit"] == "87a6733516ad6ffd1b6b97a3176f359bfeb60ca1"
    assert r["prior_helper_blob"] == "cd92e00942f0a6949e72785bb1605fb70620de22"
    assert r["poi_commit"] == "942d95d85b15d0dfdb3bc9ba1b4f273f277757c8"
    assert r["native_publisher_evaluated"] is False
    assert r["real_rust_reader_retested"] is False
    assert r["source_corpus_selected_after_results"] is False
    rows = r["rows"]
    assert len(rows) == 22 and len({row["name"] for row in rows}) == 22
    assert all(len(row["source_sha256"]) == 64 and row["bytes"] > 0 for row in rows)
    fuzz = [row for row in rows if row["status"] == "EXCLUDED_PREDECLARED_FUZZ"]
    assert len(fuzz) == 1 and fuzz[0]["name"] == "clusterfuzz-testcase-minimized-POIHPBFFuzzer-4701121678278656.pub"
    normals = [row for row in rows if row["status"] != "EXCLUDED_PREDECLARED_FUZZ"]
    assert len(normals) == 21
    assert all(row["status"] in ("STSH1_ANALYZED", "NOT_APPLICABLE", "NOT_EVALUATED") for row in normals)
    assert all(row["status"] != "STSH1_ANALYZED" or
               row["fdpp_join_status"] in ("EVALUATED", "NOT_EVALUATED") for row in normals)
    analyzed = [row for row in normals if row["status"] == "STSH1_ANALYZED"]
    for row in analyzed:
        c = row["alignment_categories"]
        assert set(c) == {"zero_high_known_low", "nonzero_high_known_low", "other_low", "absent", "ambiguous"}
        assert sum(c.values()) == row["paragraph_styles"] and row["paragraph_styles"] > 0
        if row["fdpp_join_status"] == "EVALUATED":
            j = row["fdpp"]
            assert all(isinstance(value, int) and value >= 0 for value in j.values())
            assert j["fdpp_selected_nonzero_high_known_low"] <= j["fdpp_selected_unique_no_override"]
            assert j["fdpp_distinct_selected_nonzero_high_styles"] <= c["nonzero_high_known_low"]
            assert j["fdpp_records"] == (j["fdpp_selected_unique_no_override"] +
                j["fdpp_explicit_alignment_override"] + j["fdpp_no_unique_selector"])
    c = next(row for row in rows if row["name"] == "51318.pub")
    assert c["source_sha256"] == "3ab75a6a9196e0a51fc9b0aa759459501c71d313030c06652aabffbae0a2ab09"
    assert c["status"] == "STSH1_ANALYZED"
    assert c["paragraph_styles"] == 5
    assert c["alignment_categories"]["nonzero_high_known_low"] == 4
    assert c["fdpp_join_status"] == "EVALUATED"
    assert c["fdpp"]["fdpp_selected_nonzero_high_known_low"] == 2
    summary = r["summary"]
    assert summary["verified_source_sha_count"] == 22
    assert summary["semantic_original_count"] == 21
    assert summary["adversarial_excluded_count"] == 1
    assert summary["stsh1_analyzed_count"] == len(analyzed)
    assert summary["stsh1_analyzed_count"] + summary["not_applicable_count"] + summary["stsh1_not_evaluated_count"] == 21
    assert summary["fdpp_join_evaluated_count"] + summary["fdpp_join_not_evaluated_count"] == len(analyzed)
    assert summary["total_paragraph_styles_analyzed"] == sum(row["paragraph_styles"] for row in analyzed)
    for stem in ("zero_high_known_low", "nonzero_high_known_low", "other_low", "absent_alignment", "ambiguous_alignment"):
        lookup = stem if stem in ("zero_high_known_low", "nonzero_high_known_low", "other_low") else "absent" if stem == "absent_alignment" else "ambiguous"
        assert summary[stem + "_styles"] == sum(row["alignment_categories"][lookup] for row in analyzed)
    joins = [row for row in analyzed if row["fdpp_join_status"] == "EVALUATED"]
    assert summary["selected_nonzero_high_known_low_ranges"] == sum(
        row["fdpp"]["fdpp_selected_nonzero_high_known_low"] for row in joins)
    assert summary["files_with_selected_nonzero_high_known_low"] == sum(
        row["fdpp"]["fdpp_selected_nonzero_high_known_low"] > 0 for row in joins)
    def safe(obj):
        if isinstance(obj, dict):
            forbidden = {"pub_bytes", "quill_bytes", "story_text", "raw_payload", "raw_hex",
                         "unknown_quill", "raw_source"}
            assert not forbidden.intersection(obj)
            for key,value in obj.items():
                assert isinstance(key, str)
                safe(value)
        elif isinstance(obj, list):
            for value in obj:
                safe(value)
        else:
            assert isinstance(obj, (str,int,bool,type(None)))
    safe(r)
    print("PUB-T-1001 source SHA census independent gate PASS; classified",
          summary["stsh1_analyzed_count"], "of 21 semantic originals")

if __name__ == "__main__":
    main()
