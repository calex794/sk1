#!/usr/bin/env python3
"""Re-use exact PUB-T-963 scientific Reader/Writer/CFB probe, append only T1019 test."""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess

PARENT="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
BLOB="b7c2452ce837b87c4c68b5bcb2a956ec4fedfd92"
SENTINEL="fn inspect_source(source: &[u8], expected_sha: &str) -> Result<Value> {"
PROBE="sk1_pub_t_1019_boundary_replace"

def git(root,*args):
    return subprocess.check_output(["git",*args],cwd=root,text=True).strip()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--reference",type=Path,required=True)
    p.add_argument("--writer",type=Path,required=True)
    args=p.parse_args()
    reference=args.reference.resolve(strict=True)
    writer=args.writer.resolve(strict=True)
    if git(reference,"rev-parse","HEAD")!=PARENT:
        raise RuntimeError("pinned experiment source commit mismatch")
    original=reference/"experiments/cfb/val/pub-t-963/inspect_inverse.rs"
    if git(reference,"hash-object",str(original))!=BLOB:
        raise RuntimeError("pinned experiment Rust blob changed")
    content=original.read_text(encoding="utf-8")
    if content.count(SENTINEL)!=1:
        raise RuntimeError("one pinned source split required")
    base=content.split(SENTINEL)[0]
    if "fn physical_residue(source:" not in base or "fn inspect_reverted_cfb(" not in base:
        raise RuntimeError("physical-byte classifier missing in pinned reference")
    tail=Path(__file__).with_name("probe_tail.rs").read_text(encoding="utf-8")
    if "fn inspect_source(" not in tail or "const REPL_NAMES:[&str;2]" not in tail:
        raise RuntimeError("PUB-T-1019 fixture schema changed")
    target=writer/"tools/native-pub-candidate-cli/examples"/(PROBE+".rs")
    if target.exists():
        raise RuntimeError("refusing to overwrite existing rust example")
    target.write_text(base+"\n"+tail,encoding="utf-8")
    print("PUB-T-1019 prepared pinned Writer/Reader/CFB test; exact Rust parent blob verified")

if __name__=="__main__":
    main()
