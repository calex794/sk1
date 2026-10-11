#!/usr/bin/env python3
"""Independent source-safe report gate for PUB-T-998 (never reads a source PUB)."""
import json
from pathlib import Path
import sys

def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_report.py report.json")
    r = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    assert r["schema"] == "sk1-pub-t998-reader-alignment/v1"
    assert r["task_id"] == "PUB-T-998"
    p = r["source_provenance"]
    assert p["rar2_commit"] == "b224a614af48c273b2d4bc0881793cf0217cc16d"
    assert p["reference_parser_commit"] == "87a6733516ad6ffd1b6b97a3176f359bfeb60ca1"
    assert p["reference_parser_git_blob_sha1"] == "cd92e00942f0a6949e72785bb1605fb70620de22"
    assert p["apache_poi_git_blob_sha1"] == "728811c92dff5694520e56b6c020533b29d5295d"
    assert p["source_size_bytes"] == 88576
    assert len(p["source_sha256"]) == 64
    raw = r["physical_source_structure"]
    assert raw["live_syid_count"] == 2
    assert raw["strs_utf16_lengths"] == [22, 36]
    assert raw["stsh1_paragraph_style_count"] == 5
    assert raw["raw_alignment_5a02_style_count"] == 4
    assert raw["fdpp_selected_stsh1_styles"] == [1, 2]
    assert raw["explicit_fdpp_alignment_count"] == 0
    assert (r["microsoft_publisher_native_tested"],
            r["libreoffice_retested"],
            r["product_rar2_modified"],
            r["visual_fidelity_tested"]) == (False, False, False, False)
    rows = r["variants"]
    assert [row["variant"] for row in rows] == ["original", "high_zero", "low_zero"]
    assert [row["changed_physical_bytes"] for row in rows] == [0, 4, 4]
    assert [row["changed_quill_bytes"] for row in rows] == [0, 4, 4]
    assert all(x["opened"] is True and x["reader"].get("opened") is True for x in rows)
    assert all(row["reader"]["pages"] == 1 and
               row["reader"]["text_fragment_count"] == 2 and
               sorted((story["utf16_units"], story["scalars"])
                      for story in row["reader"]["stories"]) == [(22, 22), (36, 36)]
               for row in rows)
    controls = r["controls"]
    assert controls["all_three_real_rust_reader_open"]
    assert controls["source_story_extents_and_page_count_stable"]
    assert controls["source_unchanged"]
    assert controls["only_four_expected_input_bytes_changed_per_mutant"]
    if r["verdict"] == "CONFIRMED_READER_ALIGNMENT_HIGH_BYTE_GAP":
        assert controls["expected_raw_value_high_only_delta_changes_projection"]
        original, high, low = [x["reader"] for x in rows]
        assert len(original["paragraph_alignments"]) == len(low["paragraph_alignments"]) == 0
        assert len(high["paragraph_alignments"]) == 2
        assert all(x["alignment"] == "Right" and x["source_value"] == 2
                   and x["applies_to_original_story_text"] for x in high["paragraph_alignments"])
        assert sorted((x["story_utf16_units"], x["story_scalars"],
                       x["scalar_start"], x["scalar_end"])
                      for x in high["paragraph_alignments"]) == [
            (22, 22, 0, 22), (36, 36, 0, 36)]
    else:
        assert r["verdict"] == "OTHER_READER_BEHAVIOR"
    encoded = json.dumps(r).lower()
    forbidden = ["story_text", "source_bytes", "private_story", "source_file_path",
                 "full_quill", "raw_payload", "input_pub_b64", "canonicalid",
                 "story_id"]
    assert all(x not in encoded for x in forbidden)
    print("PUB-T-998 report PASS:", r["verdict"])

if __name__ == "__main__":
    main()
