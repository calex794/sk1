#!/usr/bin/env python3
"""PUB-T-973: derive ONLY the four-byte carry test matrix from pinned T965 source.

The entire Writer/Reader/CFB comparison implementation stays in the immutable
T965 scientific commit. No duplicated Writer, Quill parser, or test framework.
Generated experiment programs are created only in the GitHub worker checkout.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re
import subprocess

PIN = "72f3c823186ec0e47d5c398f7e1118a7ba4814bb"
BLOBS = {
    "carry_probe.rs": "43f9cd167d54129fe71341bf8b5ceed4254e139c",
    "run.py": "8408b8819e0c61f81eee74e4f454a0033770c718",
    "check_report.py": "47d539e1f7368497f5f89ba8a2b509f891e1d2d1",
}
VALUES = (
    0x00FFFFFD,  # negative control: 1 changed little-endian byte
    0x00FFFFFE,  # FE FF FF 00 -> 00 00 00 01
    0x00FFFFFF,  # FF FF FF 00 -> 01 00 00 01
    0x01FFFFFE,  # FE FF FF 01 -> 00 00 00 02
    0x7FFFFFFE,  # FE FF FF 7F -> 00 00 00 80
    0xFEFFFFFE,  # FE FF FF FE -> 00 00 00 FF
)
assert len(VALUES)==6 and len(set(VALUES))==6
assert [sum(a!=b for a,b in zip(v.to_bytes(4,"little"),(v+2).to_bytes(4,"little"))) for v in VALUES]==[1,4,4,4,4,4]

OLD_RUST = """const SYNTHETIC_HEADERS:[u32;9]=[
    0x0000_00fd, 0x0000_00fe, 0x0000_00ff,
    0x0000_fffd, 0x0000_fffe, 0x0000_ffff,
    0xffff_fffd, 0xffff_fffe, 0xffff_ffff
];"""
NEW_RUST = """const SYNTHETIC_HEADERS:[u32;6]=[
    0x00ff_fffd, 0x00ff_fffe, 0x00ff_ffff,
    0x01ff_fffe, 0x7fff_fffe, 0xfeff_fffe
];"""
OLD_PY = r"VALUES = \[0xFD, 0xFE, 0xFF, 0xFFFD, 0xFFFE, 0xFFFF,\s+0xFFFFFFFD, 0xFFFFFFFE, 0xFFFFFFFF\]"
NEW_PY = """VALUES = [0x00FFFFFD, 0x00FFFFFE, 0x00FFFFFF,
          0x01FFFFFE, 0x7FFFFFFE, 0xFEFFFFFE]"""
ZIP_963 = "70aed39805d587b1f4cb32bb96ec8e615c6e4f22b7909438ed1d8685c976b3dc"
ZIP_965 = "549dd7e9791a59ae9a11be6f7cc1826ba29130dbc1944253418d9489bc2fca67"

def exactly_once(s, old, new, label):
    n=s.count(old)
    if n!=1:
        raise ValueError(f"pinned parent drift: {label}, expected one match, got {n}")
    return s.replace(old,new)

def git(*args, cwd):
    return subprocess.check_output(["git",*args],cwd=cwd,text=True).strip()

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--reference",type=Path,required=True)
    args=ap.parse_args()
    reference=args.reference.resolve(strict=True)
    if git("rev-parse","HEAD",cwd=reference)!=PIN:
        raise ValueError("parent scientific Git SHA changed")
    original=reference/"experiments/cfb/exp/pub-t-965"
    generated=Path(__file__).resolve().parent
    if not generated.as_posix().endswith("/experiments/cfb/exp/pub-t-973"):
        raise ValueError("experiment task path changed")
    if any((generated/name).exists() for name in BLOBS):
        raise ValueError("refusing to overwrite committed/previous generated source")
    for name,blob in BLOBS.items():
        f=original/name
        if not f.is_file() or git("hash-object",str(f),cwd=reference)!=blob:
            raise ValueError("parent blob changed: "+name)
        data=f.read_text(encoding="utf-8")
        if name=="carry_probe.rs":
            data=exactly_once(data,OLD_RUST,NEW_RUST,"Rust matrix")
        elif name=="run.py":
            data, n=re.subn(OLD_PY,NEW_PY,data)
            if n!=1:
                raise ValueError(f"pinned runner matrix drift: {n}")
            data=exactly_once(data,'len(row["variants"])==9',
                              'len(row["variants"])==6',"runner admission")
        else:
            data=exactly_once(data,'assert len(row["variants"])==9',
                              'assert len(row["variants"])==6',"independent validator")
            data=data.replace("3 SHA, 27 synthetic planned","3 SHA, 18 synthetic planned")
        # Different scientific identity and a bounded, explicitly pinned predecessor.
        if "965" not in data:
            raise ValueError("parent version marker disappeared in "+name)
        data=data.replace("965","973")
        if name in ("run.py","check_report.py"):
            data=exactly_once(data,"predecessor_963_zip_sha256",
                              "predecessor_965_zip_sha256","plan predecessor key")
            data=exactly_once(data,ZIP_963,ZIP_965,"predecessor archive identity")
        (generated/name).write_text(data,encoding="utf-8")
    print("PUB-T-973: exact T965 source pinned, six new SYID values, generated source verified")

if __name__=="__main__":
    main()
