#!/usr/bin/env python3
"""Derive T978 on-worker from pinned T961, without duplicating product or harness."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

PARENT = "9ca16fa981e9fd516822979491654eb9b0fc9264"
BLOBS = {
    "unicode_glyph_compare.rs": "7c1bb7fa817fff3875e9d04a19c5fb7358e78e78",
    "run.py": "32a5750b740909bbff41115026db7ffe04e64d95",
    "check_report.py": "e83fde424cb2181a42825354b59ea4ad87c89f96",
    "witnesses.json": "cea5b61e35e6a0fa994c7e40550b0d2a27da81e2",
}
TESTS = {
    "NUL": 0x0000, "TAB": 0x0009, "LF": 0x000A, "VT": 0x000B,
    "CR": 0x000D, "NBSP": 0x00A0, "LINE_SEPARATOR": 0x2028,
}
assert len(TESTS) == 7 and len(set(TESTS.values())) == 7
assert all(x <= 0xFFFF for x in TESTS.values())

OLD_RUST = """        for (tag,ch) in [
            ("LATIN1_E_ACUTE",'\\u{00e9}'),
            ("CYRILLIC_ZHE",'\\u{0416}'),
            ("CJK_ZHONG",'\\u{4e2d}'),
            ("COMBINING_ACUTE",'\\u{0301}'),
            ("ASTRAL_GRIN",'\\u{1f600}')
        ] {"""
NEW_RUST = """        for (tag,ch) in [
            ("NUL",'\\u{0000}'),
            ("TAB",'\\u{0009}'),
            ("LF",'\\u{000a}'),
            ("VT",'\\u{000b}'),
            ("CR",'\\u{000d}'),
            ("NBSP",'\\u{00a0}'),
            ("LINE_SEPARATOR",'\\u{2028}')
        ] {"""
OLD_CLASSES = 'GLYPHS=("LATIN1_E_ACUTE","CYRILLIC_ZHE","CJK_ZHONG","COMBINING_ACUTE","ASTRAL_GRIN")'
NEW_CLASSES = 'GLYPHS=("NUL","TAB","LF","VT","CR","NBSP","LINE_SEPARATOR")'

def once(s, old, new, name):
    n=s.count(old)
    if n != 1:
        raise ValueError(f"immutable parent changed: {name}, count={n}")
    return s.replace(old,new)

def git(*parts, cwd):
    return subprocess.check_output(["git",*parts],cwd=cwd,text=True).strip()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--reference",required=True,type=Path)
    args=parser.parse_args()
    root=args.reference.resolve(strict=True)
    if git("rev-parse","HEAD",cwd=root)!=PARENT:
        raise ValueError("reference commit changed")
    baseline=root/"experiments/quill/val/pub-t-961"
    here=Path(__file__).resolve().parent
    if not here.as_posix().endswith("/experiments/quill/val/pub-t-978"):
        raise ValueError("unexpected code path")
    if any((here/k).exists() for k in BLOBS):
        raise ValueError("generated files already exist: refusing overwrite")
    for name,sha in BLOBS.items():
        src=baseline/name
        if not src.is_file() or git("hash-object",str(src),cwd=root)!=sha:
            raise ValueError(f"pinned T961 blob checksum changed: {name}")
        if name=="witnesses.json":
            (here/name).write_bytes(src.read_bytes())
            continue
        code=src.read_text(encoding="utf-8")
        if name=="unicode_glyph_compare.rs":
            code=once(code,OLD_RUST,NEW_RUST,"Writer glyph list")
        else:
            code=once(code,OLD_CLASSES,NEW_CLASSES,"Python Unicode labels")
            code=once(code,"BMP=GLYPHS[:4]","BMP=GLYPHS","all seven are BMP")
        if name=="run.py":
            code=once(code,
              "77 matched ASCII source+Story+UTF16 slots, different Unicode BMP glyph widths; no Publisher native",
              "77 pinned ASCII source+Story+UTF16 slots, seven UTF16 control/separator code units; no Publisher native",
              "experiment scope")
            code=once(code,'TARGET_BINARY="sk1_pub_t_961_unicode"',
                      'TARGET_BINARY="sk1_pub_t_978_unicode"',"binary target")
            code=once(code,'"predeclared_slot_count":77,',
                      '"predeclared_slot_count":77,\n        "parent_t961_scientific_commit":PARENT,\n        "parent_t961_zip_sha256":"03181d77d764fd6ad9377ce90ac0804da70dc02c646a41cf4553c450aeff4d80",',
                      "parent metadata")
            code=once(code,'UPSTREAM="703808408fd919e564a90cdc236e81db3c04af8b"',
                      'UPSTREAM="703808408fd919e564a90cdc236e81db3c04af8b"\nPARENT="'+PARENT+'"',
                      "parent constant")
        elif name=="check_report.py":
            code=once(code,'"product_authorized"}',
                 '"product_authorized","parent_t961_scientific_commit","parent_t961_zip_sha256"}',
                 "plan strict field count")
            code=once(code,'assert plan["product_authorized"] is False',
                 'assert plan["product_authorized"] is False\n'
                 '    assert plan["parent_t961_scientific_commit"]==runner.PARENT\n'
                 '    assert plan["parent_t961_zip_sha256"]=="03181d77d764fd6ad9377ce90ac0804da70dc02c646a41cf4553c450aeff4d80"',
                 "parent acceptance")
            code=once(code,"77 predeclared Story-offsets, 385 Unicode arms",
                      "77 predeclared Story-offsets, 539 UTF16 control arms",
                      "count log")
        code=code.replace("961","978")
        (here/name).write_text(code,encoding="utf-8")
    print("PUB-T-978 prepared strictly: T961 harness+77 SHA-pinned witnesses, 7 new code units")

if __name__=="__main__":
    main()
