#!/usr/bin/env python3
"""Independent T1003 numeric report checks: no PUB/Quill/Story text."""
from __future__ import annotations
import json
from pathlib import Path
import sys

def main():
    if len(sys.argv)!=2:
        raise SystemExit("usage: check_report.py JSON")
    r=json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert r["schema"]=="sk1-pub-t1003-second-source-rust-ab/v1"
    assert r["task_id"]=="PUB-T-1003"
    assert r["rar2_commit"]=="b224a614af48c273b2d4bc0881793cf0217cc16d"
    assert r["t994_parser_commit"]=="87a6733516ad6ffd1b6b97a3176f359bfeb60ca1"
    assert r["t994_parser_git_blob"]=="cd92e00942f0a6949e72785bb1605fb70620de22"
    s=r["source"]
    assert s["name"]=="60685.pub"
    assert s["source_git_blob_sha1"]=="37d3dce70e1786e948edd5592527f90be1fae2ff"
    assert s["original_sha256"]=="0d3cecf0ff000a20931d0de3ebc48040bea10e03833ade3f9902f996c20e7184"
    assert s["original_byte_size"]==119296
    assert [r[k] for k in ("microsoft_publisher_native_evaluated",
                           "libreoffice_retested","rar2_product_modified",
                           "visual_fidelity_tested")]==[False,False,False,False]
    p=r["physical_source"]
    assert p["stsh1_paragraph_style_count"]==36
    assert p["natural_known_alignment_style_count"]==4
    assert p["natural_nonzero_high_style_count"]==2
    assert p["source_selected_nonzero_high_fdpp_range_count"]==3
    assert p["source_selected_style_indices"]==[21,21,23]
    assert p["source_story_utf16_lengths"]==[1882,1,1,1]
    assert p["source_utf16_unit_count"]==1885
    assert p["source_text_bytes"]==3770
    assert p["source_story_id_count"]==4
    assert p["explicit_fdpp_override_in_selected_ranges"]==0
    variants=r["variants"]
    assert [v["name"] for v in variants]==["original","high_zero","low_zero"]
    assert [v["changed_physical_bytes"] for v in variants]==[0,2,2]
    assert [v["changed_quill_bytes"] for v in variants]==[0,2,2]
    assert all(v["rust"]["opened"] is True for v in variants)
    c=r["controls"]
    assert c["three_variants_opened"]
    assert c["pages_and_fragment_counts_stable"]
    assert c["reader_story_extents_stable"]
    assert c["physical_byte_change_counts_correct"]
    counts=r["run_counts"]
    assert counts["high_additions"]>=0 and counts["high_removals"]>=0
    assert counts["high_added_expected_single_character_right"]<=counts["high_additions"]
    if r["verdict"]=="CONFIRMED_SECOND_SOURCE_HIGH_BYTE_ALIGNMENT_GAP":
        assert c["low_control_run_multiset_unchanged"]
        assert c["high_control_adds_exactly_three_single_character_right_runs"]
        assert counts["high_additions"]==3
        assert counts["high_removals"]==0
        assert counts["high_zero"]==counts["original"]+3
        assert counts["low_zero"]==counts["original"]
        assert counts["low_has_changes"] is False
    else:
        assert r["verdict"]=="HYPOTHESIS_NOT_CONFIRMED_ON_SECOND_SOURCE"
    def check_safe(value):
        if isinstance(value,dict):
            forbidden={"source_bytes","raw_quill","story_text","story_id","canonical_id",
                       "input_pub_b64","original_bytes","raw_payload"}
            assert not forbidden.intersection(value)
            for v in value.values():check_safe(v)
        elif isinstance(value,list):
            for v in value:check_safe(v)
        elif isinstance(value,str):
            assert "CanonicalId(" not in value
    check_safe(r)
    print("PUB-T-1003 independent report PASS, verdict:",r["verdict"])

if __name__=="__main__":
    main()
