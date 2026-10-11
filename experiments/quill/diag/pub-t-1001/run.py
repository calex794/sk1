#!/usr/bin/env python3
"""PUB-T-1001: natural STSH1 paragraph alignment u16 across the fixed 21-PUB T997 corpus.

All PUB/Quill/Story/source bytes are transient on hosted CI. The JSON exports
only source identities, counts and bounded reasons; never source text or raw bytes.
"""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
from urllib.parse import quote
from urllib.request import urlopen, Request

import olefile

RAR_PIN = "b224a614af48c273b2d4bc0881793cf0217cc16d"
MANIFEST_BLOB = "4e77d912e7a104cc192be5e6504892c295c1db01"
T994_PIN = "87a6733516ad6ffd1b6b97a3176f359bfeb60ca1"
PARSER_BLOB = "cd92e00942f0a6949e72785bb1605fb70620de22"
POI_PIN = "942d95d85b15d0dfdb3bc9ba1b4f273f277757c8"
FIXTURES_EXPECTED = 22
SEMANTIC_EXPECTED = 21
FUZZ_NAME = "clusterfuzz-testcase-minimized-POIHPBFFuzzer-4701121678278656.pub"
STREAM = ("Quill", "QuillSub", "CONTENTS")
WIDTH_UNKNOWN = "STSH1_UNSUPPORTED_WIRE"
REASONS = {
    "CFB_OPEN_FAILED", "MISSING_QUILL", "STSH1_MISSING",
    "STSH1_FRAMING_UNSUPPORTED", "FDPP_NOT_UNIQUE",
    "FDPP_FRAMING_UNSUPPORTED", "FDPP_UNSUPPORTED_WIRE"
}


def checked_git(args, root):
    return subprocess.run(["git", *args], cwd=root, check=True,
                          capture_output=True, text=True, timeout=30).stdout.strip()


def sha256(buf):
    return hashlib.sha256(buf).hexdigest()


def load_sources(root):
    if checked_git(["rev-parse", "HEAD"], root) != RAR_PIN:
        raise ValueError("RAR_SOURCE_PIN_DRIFT")
    path = root / "tools/reader_corpus_manifest_v1.json"
    if checked_git(["hash-object", "tools/reader_corpus_manifest_v1.json"], root) != MANIFEST_BLOB:
        raise ValueError("MANIFEST_BLOB_DRIFT")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "chaptera.reader-corpus-manifest.v1":
        raise ValueError("MANIFEST_SCHEMA_DRIFT")
    if manifest["upstream"]["commit"] != POI_PIN:
        raise ValueError("APACHE_POI_COMMIT_DRIFT")
    fixtures = manifest["fixtures"]
    if len(fixtures) != FIXTURES_EXPECTED or len(set(e["name"] for e in fixtures)) != 22:
        raise ValueError("CORPUS_SIZE_OR_DUPLICATION_DRIFT")
    if sum(bool(e["semantic"]) for e in fixtures) != SEMANTIC_EXPECTED:
        raise ValueError("CORPUS_SEMANTIC_COUNT_DRIFT")
    if [e["name"] for e in fixtures if not e["semantic"]] != [FUZZ_NAME]:
        raise ValueError("ADVERSARIAL_IDENTITY_DRIFT")
    return manifest


def load_prior(root):
    if checked_git(["rev-parse", "HEAD"], root) != T994_PIN:
        raise ValueError("PRIOR_HELPER_PIN_DRIFT")
    filename = "experiments/quill/exp/pub-t-994/run.py"
    if checked_git(["hash-object", filename], root) != PARSER_BLOB:
        raise ValueError("PRIOR_HELPER_BLOB_DRIFT")
    path = root / filename
    spec = importlib.util.spec_from_file_location("sk1_t1001_prior", path)
    if not spec or not spec.loader:
        raise ValueError("PRIOR_HELPER_IMPORT_FAIL")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def download_verified(entry, prefix):
    with urlopen(Request(prefix.rstrip("/") + "/" + quote(entry["name"], safe=""),
                         headers={"User-Agent": "SK1-PUB-T-1001"}), timeout=45) as response:
        source = response.read(2_000_000)
    if len(source) != entry["byte_len"] or sha256(source) != entry["sha256"]:
        raise ValueError("UPSTREAM_BYTES_OR_SHA_DRIFT")
    return source


def class_from_value(value):
    low = value & 255
    high = value >> 8
    if low not in (1, 2, 3, 4):
        return "other_low"
    return "nonzero_high_known_low" if high else "zero_high_known_low"


def styles_from_stsh(prior, quill, desc):
    stsh = [d for d in desc if d[0] == b"STSH" and d[1] == 1]
    if len(stsh) != 1:
        raise ValueError("STSH1_MISSING")
    try:
        records = prior.paragraph_properties(quill, stsh[0])
    except (ValueError, IndexError, OverflowError, KeyError) as err:
        raise ValueError("STSH1_FRAMING_UNSUPPORTED") from err
    categories = {"zero_high_known_low": 0, "nonzero_high_known_low": 0,
                  "other_low": 0, "absent": 0, "ambiguous": 0}
    styles = {}
    for item in records:
        style_id = (item["index"] - 1) // 2
        relevant = [prop for prop in item["props"] if prop[0] == 0x04]
        if not relevant:
            categories["absent"] += 1
            styles[style_id] = "absent"
        elif len(relevant) != 1 or relevant[0][1] != 0x12 or relevant[0][3] != 2:
            categories["ambiguous"] += 1
            styles[style_id] = "ambiguous"
        else:
            pos = relevant[0][2]
            if pos + 4 > len(quill):
                categories["ambiguous"] += 1
                styles[style_id] = "ambiguous"
            else:
                value = prior.u16(quill, pos + 2)
                category = class_from_value(value)
                categories[category] += 1
                styles[style_id] = category
    if sum(categories.values()) != len(records):
        raise ValueError("STSH1_CATEGORY_SUM")
    return styles, categories


def fdpp_selection_counts(prior, quill, desc, styles):
    fdpps = [d for d in desc if d[0] == b"FDPP"]
    if len(fdpps) != 1:
        raise ValueError("FDPP_NOT_UNIQUE")
    _, _, start, nbytes = fdpps[0]
    try:
        count = prior.u16(quill, start)
        index_end = start + 8 + 6 * count
        if not (0 < count <= 10000 and index_end <= start + nbytes <= len(quill)):
            raise ValueError("FDPP_FRAMING_UNSUPPORTED")
        selected = 0
        nonzero_high_selected = 0
        distinct_nonzero = set()
        explicit = 0
        ambiguous_selector = 0
        for ordinal in range(count):
            rel = prior.u16(quill, start + 8 + count * 4 + ordinal * 2)
            rowstart = start + rel
            if rowstart < index_end or rowstart + 4 > start + nbytes:
                raise ValueError("FDPP_FRAMING_UNSUPPORTED")
            rowlen = prior.u32(quill, rowstart)
            rowend = rowstart + rowlen
            if rowlen < 4 or rowend > start + nbytes:
                raise ValueError("FDPP_FRAMING_UNSUPPORTED")
            cursor = rowstart + 4
            selectors = []
            direct_align = False
            while cursor < rowend:
                if cursor + 2 > rowend:
                    raise ValueError("FDPP_FRAMING_UNSUPPORTED")
                propid, wire = quill[cursor], quill[cursor + 1]
                width = prior.TYPE_LEN.get(wire)
                if width is None:
                    raise ValueError("FDPP_UNSUPPORTED_WIRE")
                if width == -1:
                    if cursor + 6 > rowend:
                        raise ValueError("FDPP_FRAMING_UNSUPPORTED")
                    width = prior.u32(quill, cursor + 2)
                if width < 0 or cursor + 2 + width > rowend:
                    raise ValueError("FDPP_FRAMING_UNSUPPORTED")
                if propid == 0x19 and wire == 0x1A and width == 2:
                    selectors.append(prior.u16(quill, cursor + 2))
                if propid == 0x04:
                    direct_align = True
                cursor += 2 + width
            if cursor != rowend:
                raise ValueError("FDPP_FRAMING_UNSUPPORTED")
            if direct_align:
                explicit += 1
                continue
            if len(selectors) != 1:
                ambiguous_selector += 1
                continue
            selected += 1
            style_idx = selectors[0]
            if styles.get(style_idx) == "nonzero_high_known_low":
                nonzero_high_selected += 1
                distinct_nonzero.add(style_idx)
        return {
            "fdpp_records": count,
            "fdpp_selected_unique_no_override": selected,
            "fdpp_selected_nonzero_high_known_low": nonzero_high_selected,
            "fdpp_distinct_selected_nonzero_high_styles": len(distinct_nonzero),
            "fdpp_explicit_alignment_override": explicit,
            "fdpp_no_unique_selector": ambiguous_selector,
        }
    except (ValueError, IndexError, OverflowError, KeyError) as err:
        reason = str(err)
        if reason not in ("FDPP_FRAMING_UNSUPPORTED", "FDPP_UNSUPPORTED_WIRE"):
            reason = "FDPP_FRAMING_UNSUPPORTED"
        raise ValueError(reason) from err


def classify_semantic(prior, original, entry):
    row = {"name": entry["name"], "source_sha256": entry["sha256"],
           "bytes": len(original), "status": "NOT_EVALUATED"}
    try:
        with olefile.OleFileIO(io.BytesIO(original)) as ole:
            if not ole.exists(STREAM):
                row["status"] = "NOT_APPLICABLE"
                row["reason"] = "MISSING_QUILL"
                return row
            quill = ole.openstream(STREAM).read()
    except (OSError, ValueError, TypeError, IndexError) as err:
        row["reason"] = "CFB_OPEN_FAILED"
        return row
    try:
        desc = prior.descriptors(quill)
        styles, categories = styles_from_stsh(prior, quill, desc)
    except (ValueError, IndexError, OverflowError, KeyError) as err:
        reason = str(err)
        row["reason"] = reason if reason in REASONS else "STSH1_FRAMING_UNSUPPORTED"
        return row
    row["status"] = "STSH1_ANALYZED"
    row["paragraph_styles"] = len(styles)
    row["alignment_categories"] = categories
    try:
        f = fdpp_selection_counts(prior, quill, desc, styles)
        row["fdpp_join_status"] = "EVALUATED"
        row["fdpp"] = f
    except (ValueError, IndexError, OverflowError, KeyError) as err:
        reason = str(err)
        row["fdpp_join_status"] = "NOT_EVALUATED"
        row["fdpp_reason"] = reason if reason in REASONS else "FDPP_FRAMING_UNSUPPORTED"
    return row


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: run.py RAR2_DIR T994_DIR OUT_JSON")
    rar, helper, output = [Path(v).resolve() for v in sys.argv[1:]]
    manifest = load_sources(rar)
    prior = load_prior(helper)
    result = {
        "schema": "sk1-pub-t1001-stsh1-natural-census/v1",
        "task_id": "PUB-T-1001",
        "rar2_commit": RAR_PIN,
        "rar2_manifest_git_blob": MANIFEST_BLOB,
        "prior_t994_commit": T994_PIN,
        "prior_helper_blob": PARSER_BLOB,
        "poi_commit": POI_PIN,
        "native_publisher_evaluated": False,
        "real_rust_reader_retested": False,
        "source_corpus_selected_after_results": False,
        "rows": [],
    }
    for entry in manifest["fixtures"]:
        source = download_verified(entry, manifest["upstream"]["base_url"])
        if entry["semantic"]:
            row = classify_semantic(prior, source, entry)
        else:
            row = {"name": entry["name"], "source_sha256": entry["sha256"],
                   "bytes": len(source), "status": "EXCLUDED_PREDECLARED_FUZZ"}
        result["rows"].append(row)
    normal = [r for r in result["rows"] if r["status"] != "EXCLUDED_PREDECLARED_FUZZ"]
    analyzed = [r for r in normal if r["status"] == "STSH1_ANALYZED"]
    def category(name):
        return sum(r["alignment_categories"][name] for r in analyzed)
    joins = [r for r in analyzed if r.get("fdpp_join_status") == "EVALUATED"]
    result["summary"] = {
        "verified_source_sha_count": len(result["rows"]),
        "semantic_original_count": len(normal),
        "adversarial_excluded_count": len(result["rows"]) - len(normal),
        "stsh1_analyzed_count": len(analyzed),
        "not_applicable_count": sum(r["status"] == "NOT_APPLICABLE" for r in normal),
        "stsh1_not_evaluated_count": sum(r["status"] == "NOT_EVALUATED" for r in normal),
        "fdpp_join_evaluated_count": len(joins),
        "fdpp_join_not_evaluated_count": len(analyzed) - len(joins),
        "total_paragraph_styles_analyzed": sum(r["paragraph_styles"] for r in analyzed),
        "zero_high_known_low_styles": category("zero_high_known_low"),
        "nonzero_high_known_low_styles": category("nonzero_high_known_low"),
        "other_low_styles": category("other_low"),
        "absent_alignment_styles": category("absent"),
        "ambiguous_alignment_styles": category("ambiguous"),
        "selected_nonzero_high_known_low_ranges": sum(
            r["fdpp"]["fdpp_selected_nonzero_high_known_low"] for r in joins),
        "files_with_selected_nonzero_high_known_low": sum(
            r["fdpp"]["fdpp_selected_nonzero_high_known_low"] > 0 for r in joins),
    }
    control = next(r for r in result["rows"] if r["name"] == "51318.pub")
    if not (control["status"] == "STSH1_ANALYZED"
            and control["paragraph_styles"] == 5
            and control["alignment_categories"]["nonzero_high_known_low"] == 4
            and control["fdpp_join_status"] == "EVALUATED"
            and control["fdpp"]["fdpp_selected_nonzero_high_known_low"] == 2
            and control["fdpp"]["fdpp_explicit_alignment_override"] == 0):
        raise ValueError("T998_POSITIVE_CONTROL_FAILED")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                      encoding="utf-8")
    print("PUB-T-1001 fixed-corpus natural STSH1 census:",
          json.dumps(result["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
