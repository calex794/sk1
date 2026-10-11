#!/usr/bin/env python3
"""PUB-T-998: public 51318 original / STSH1 high-only / low-only, actual compiled Rust Reader.
Original and mutated PUB, Quill, Story text and private probe data never leave CI temp storage.
"""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import Request, urlopen

import olefile

RAR2_SHA = "b224a614af48c273b2d4bc0881793cf0217cc16d"
T994_SHA = "87a6733516ad6ffd1b6b97a3176f359bfeb60ca1"
T994_PARSER_BLOB = "cd92e00942f0a6949e72785bb1605fb70620de22"
POI_SHA = "ae62bb5116b9aee19ebd5834e3a82066132c9f7f"
POI_BLOB = "728811c92dff5694520e56b6c020533b29d5295d"
POI_PATH = "test-data/publisher/51318.pub"
EXPECTED_SIZE = 88576
STREAM = ("Quill", "QuillSub", "CONTENTS")


def git(args, root):
    return subprocess.run(["git", *args], cwd=root, check=True,
                          capture_output=True, text=True, timeout=25).stdout.strip()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def count_diff(before, after):
    if len(before) != len(after):
        raise ValueError("PHYSICAL_LENGTH_CHANGED")
    return sum(a != b for a, b in zip(before, after))


def load_pinned_parser(t994):
    if git(["rev-parse", "HEAD"], t994) != T994_SHA:
        raise ValueError("T994_SOURCE_REVISION_DRIFT")
    path = t994 / "experiments/quill/exp/pub-t-994/run.py"
    if git(["hash-object", str(path.relative_to(t994))], t994) != T994_PARSER_BLOB:
        raise ValueError("T994_PARSER_BLOB_DRIFT")
    spec = importlib.util.spec_from_file_location("sk1_pinned_t994_parser", path)
    if spec is None or spec.loader is None:
        raise ValueError("T994_PARSER_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fetch_source():
    url = "https://raw.githubusercontent.com/apache/poi/" + POI_SHA + "/" + POI_PATH
    with urlopen(Request(url, headers={"User-Agent": "SK1-PUB-T-998"}), timeout=45) as handle:
        raw = handle.read(200000)
    if len(raw) != EXPECTED_SIZE:
        raise ValueError("POI_SOURCE_SIZE_DRIFT")
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    if blob != POI_BLOB:
        raise ValueError("POI_SOURCE_BLOB_DRIFT")
    return raw


def fdpp_selected_styles(prior, quill, descriptors):
    fdpp = prior.one(descriptors, b"FDPP")
    _, _, offset, length = fdpp
    count = prior.u16(quill, offset)
    if count != 2 or length != 512:
        raise ValueError("FDPP_STRUCTURE_DRIFT")
    rows = []
    for ordinal in range(count):
        final_byte_offset = prior.u32(quill, offset + 8 + 4 * ordinal)
        style_rel = prior.u16(quill, offset + 8 + 4 * count + 2 * ordinal)
        start = offset + style_rel
        style_len = prior.u32(quill, start)
        end = start + style_len
        if start < offset + 8 + 6 * count or end > offset + length or style_len < 4:
            raise ValueError("FDPP_STYLE_BOUNDS")
        cursor = start + 4
        selectors = []
        direct_alignments = []
        while cursor < end:
            id_, type_ = quill[cursor], quill[cursor + 1]
            width = prior.TYPE_LEN.get(type_)
            if width is None:
                raise ValueError("FDPP_UNKNOWN_WIRE")
            if width == -1:
                width = prior.u32(quill, cursor + 2)
            if width < 0 or cursor + 2 + width > end:
                raise ValueError("FDPP_WIRE_BOUNDS")
            if id_ == 0x19 and type_ == 0x1A and width == 2:
                selectors.append(prior.u16(quill, cursor + 2))
            if id_ == 0x04:
                direct_alignments.append((id_, type_))
            cursor += 2 + width
        if cursor != end or len(selectors) != 1 or direct_alignments:
            raise ValueError("FDPP_SELECTOR_OR_OVERRIDE_DRIFT")
        rows.append({"selector": selectors[0], "text_end": final_byte_offset})
    if rows != [{"selector": 1, "text_end": 556},
                {"selector": 2, "text_end": 628}]:
        raise ValueError("FDPP_STORY_JOIN_DRIFT")
    return rows


def check_source_structure(prior, quill):
    descriptors = prior.descriptors(quill)
    text = prior.one(descriptors, b"TEXT")
    syid = prior.one(descriptors, b"SYID")
    strs = prior.one(descriptors, b"STRS")
    stsh = prior.one(descriptors, b"STSH", 1)
    if text[2:] != (512, 116):
        raise ValueError("TEXT_PHYSICAL_SIZE_DRIFT")
    if prior.u32(quill, syid[2]) != 3 or prior.u32(quill, syid[2] + 4) != 2:
        raise ValueError("SYID_HEADER_DRIFT")
    story_ids = [prior.u32(quill, syid[2] + 8 + i * 4) for i in range(2)]
    if story_ids != [2, 3]:
        raise ValueError("SYID_STORIES_DRIFT")
    if prior.u32(quill, strs[2]) != 2:
        raise ValueError("STRS_COUNT_DRIFT")
    service_span = prior.u32(quill, strs[2] + 4)
    lengths = [prior.u32(quill, strs[2] + 4 + service_span + 4 * i) for i in range(2)]
    if lengths != [22, 36] or sum(lengths) * 2 != text[3]:
        raise ValueError("STRS_LENGTH_DRIFT")
    paragraph_rows = prior.paragraph_properties(quill, stsh)
    if len(paragraph_rows) != 5:
        raise ValueError("STSH1_PARAGRAPH_RECORD_COUNT_DRIFT")
    high_offsets, low_offsets = [], []
    for logical_idx, row in enumerate(paragraph_rows):
        selected = [p for p in row["props"] if p[0] == 0x04]
        if logical_idx == 0:
            if selected:
                raise ValueError("STSH1_STYLE0_CHANGED")
            continue
        if len(selected) != 1:
            raise ValueError("STSH1_ALIGN_PRESENCE_CHANGED")
        id_, wire, pos, width = selected[0]
        if id_ != 4 or wire != 0x12 or width != 2 or quill[pos + 2:pos + 4] != b"\x02\x5a":
            raise ValueError("STSH1_ALIGN_VALUE_CHANGED")
        low_offsets.append(pos + 2)
        high_offsets.append(pos + 3)
    if len(high_offsets) != 4 or len(set(high_offsets + low_offsets)) != 8:
        raise ValueError("STSH1_ALIGNMENT_COUNT")
    selected = fdpp_selected_styles(prior, quill, descriptors)
    return high_offsets, low_offsets, {
        "live_syid_count": len(story_ids),
        "strs_utf16_lengths": lengths,
        "stsh1_paragraph_style_count": len(paragraph_rows),
        "raw_alignment_5a02_style_count": len(high_offsets),
        "fdpp_selected_stsh1_styles": [r["selector"] for r in selected],
        "explicit_fdpp_alignment_count": 0
    }


def run_reader(executable, case, private_out):
    subprocess.run([str(executable), str(case), str(private_out)],
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
    return json.loads(private_out.read_text(encoding="utf-8"))


def main():
    if len(sys.argv) != 5:
        raise SystemExit("usage: run.py RAR2_DIR REFERENCE_T994 READER_EXE REPORT_JSON")
    rar2, ref, exe, output = [Path(x).resolve() for x in sys.argv[1:]]
    if git(["rev-parse", "HEAD"], rar2) != RAR2_SHA:
        raise ValueError("RAR2_SOURCE_REVISION_DRIFT")
    if not exe.is_file():
        raise ValueError("ACTUAL_RUST_READER_MISSING")
    prior = load_pinned_parser(ref)
    original = fetch_source()
    with olefile.OleFileIO(io.BytesIO(original)) as ole:
        quill = ole.openstream(STREAM).read()
    if len(quill) != 5120:
        raise ValueError("QUILL_SIZE_DRIFT")
    high, low, physical = check_source_structure(prior, quill)
    report = {
        "schema": "sk1-pub-t998-reader-alignment/v1",
        "task_id": "PUB-T-998",
        "source_provenance": {
            "rar2_commit": RAR2_SHA,
            "reference_parser_commit": T994_SHA,
            "reference_parser_git_blob_sha1": T994_PARSER_BLOB,
            "apache_poi_commit": POI_SHA,
            "apache_poi_git_blob_sha1": POI_BLOB,
            "source_sha256": sha256(original),
            "source_size_bytes": len(original)
        },
        "physical_source_structure": physical,
        "microsoft_publisher_native_tested": False,
        "libreoffice_retested": False,
        "product_rar2_modified": False,
        "visual_fidelity_tested": False,
        "variants": [],
    }
    with tempfile.TemporaryDirectory(prefix="sk1-pub-t998-") as temp_str:
        temp = Path(temp_str)
        for name, patch in [
            ("original", []),
            ("high_zero", [(offset, 0) for offset in high]),
            ("low_zero", [(offset, 0) for offset in low]),
        ]:
            target = temp / (name + ".pub")
            if patch:
                q_new, changed = prior.mutated_quill(quill, patch)
                prior.write_variant(original, q_new, target)
            else:
                target.write_bytes(original)
                changed = 0
            final = target.read_bytes()
            physical_diff = count_diff(original, final)
            if physical_diff != changed or changed != (0 if name == "original" else 4):
                raise ValueError("PHYSICAL_BYTE_LOCALITY_FAILED")
            with olefile.OleFileIO(str(target)) as ole:
                reread_q = ole.openstream(STREAM).read()
            expected_q = quill if name == "original" else q_new
            if reread_q != expected_q or len(final) != len(original):
                raise ValueError("CFB_OR_QUILL_REPLAY_FAILED")
            private_out = temp / (name + ".json")
            reader = run_reader(exe, target, private_out)
            report["variants"].append({
                "variant": name,
                "changed_physical_bytes": physical_diff,
                "changed_quill_bytes": changed,
                "opened": reader.get("opened", False),
                "reader": reader
            })
        # Running experiments from the same verified original proves within-source
        # causality; these variants are NOT independent Microsoft Publisher saves.
        orig, upper, lower = [r["reader"] for r in report["variants"]]
        all_open = all(v.get("opened") is True for v in (orig, upper, lower))
        source_stable = all_open and (
            orig["stories"] == upper["stories"] == lower["stories"] and
            orig["pages"] == upper["pages"] == lower["pages"]
        )
        base_runs = orig.get("paragraph_alignments", [])
        hi_runs = upper.get("paragraph_alignments", [])
        lo_runs = lower.get("paragraph_alignments", [])
        exact_right = (
            len(base_runs) == 0 and len(hi_runs) == 2 and len(lo_runs) == 0
            and all(r.get("alignment") == "Right" and r.get("source_value") == 2
                    and r.get("applies_to_original_story_text") is True
                    for r in hi_runs)
            and len({r.get("story_id") for r in hi_runs}) == 2
            and all(r.get("scalar_start") == 0 and r.get("scalar_end") > 0
                    for r in hi_runs)
        )
        if not all_open or not source_stable:
            report["verdict"] = "NOT_EVALUATED"
        elif exact_right:
            report["verdict"] = "CONFIRMED_READER_ALIGNMENT_HIGH_BYTE_GAP"
        else:
            report["verdict"] = "OTHER_READER_BEHAVIOR"
        report["controls"] = {
            "all_three_real_rust_reader_open": all_open,
            "source_story_and_page_identity_stable": source_stable,
            "expected_raw_value_high_only_delta_changes_projection": exact_right,
            "source_unchanged": sha256(original) == report["source_provenance"]["source_sha256"],
            "only_four_expected_input_bytes_changed_per_mutant": True
        }
    # No private files survive TemporaryDirectory and the public JSON contains
    # only hashed source identities, numbers, alignment names and diagnostic codes.
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("PUB-T-998 actual Rust reader verdict:", report["verdict"])
    return 0 if report["verdict"] != "NOT_EVALUATED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
