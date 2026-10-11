#!/usr/bin/env python3
"""Prepare PUB-T-993 experiment from pinned already-verified T984 helpers.

No second Writer implementation; step(), Reader/Editor checks and full CFB
diff functions are copied verbatim into ephemeral GitHub worker example.
Only the new chaining experiment belongs to PUB-T-993.
"""
from pathlib import Path
import argparse
import subprocess

PIN_984="14ac75ae0346b3bdbeeada110e1f463dda6cbb27"
PIN_963="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
PIN_971="cd38c8d6a545737f9f99821076340505db5e149c"
OLD_INSPECT="fn inspect_source(source: &[u8], expected_sha: &str) -> Result<Value> {"

def git(root,*args):
    return subprocess.check_output(["git",*args],cwd=root,text=True).strip()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--ref-984",type=Path,required=True)
    parser.add_argument("--ref-963",type=Path,required=True)
    parser.add_argument("--ref-971",type=Path,required=True)
    args=parser.parse_args()
    parent=args.ref_984.resolve(strict=True)
    old=args.ref_963.resolve(strict=True)
    legacy=args.ref_971.resolve(strict=True)
    assert git(parent,"rev-parse","HEAD")==PIN_984
    assert git(old,"rev-parse","HEAD")==PIN_963
    assert git(legacy,"rev-parse","HEAD")==PIN_971
    original=parent/"experiments/cfb/val/pub-t-984/prepare.py"
    if not original.is_file():
        raise ValueError("pinned original generator unavailable")
    # Generator's own checks authenticate all historical Rust helper blobs.
    subprocess.run(["python3",str(original),
        "--ref-inverse",str(old),"--ref-corpus",str(legacy)],check=True)
    built=parent/"experiments/cfb/val/pub-t-984/real_inverse.rs"
    source=built.read_text(encoding="utf-8")
    assert source.count(OLD_INSPECT)==1
    prefix=source[:source.index(OLD_INSPECT)]
    assert "fn step(input: &[u8]," in prefix
    assert "fn inspect_reverted_cfb(source: &[u8]," in prefix
    assert "fn physical_residue(source: &[u8]," in prefix
    assert "fn main()" not in prefix
    assert "fn inspect_source(" not in prefix
    prefix=prefix.replace("pub-t-984","pub-t-993").replace("PUB-T-984","PUB-T-993")
    our=Path(__file__).resolve().parent
    tail=(our/"chain_body.rs").read_text(encoding="utf-8")
    assert tail.count("fn inspect_source(source:&[u8],expected:&str)->Result<Value>")==1
    assert tail.count("fn main()->Result<()>")==1
    target=our/"generated_writer_chain.rs"
    if target.exists():
        raise ValueError("refuse overwrite generated test source")
    target.write_text(prefix+tail,encoding="utf-8")
    print("PUB-T-993: unchanged T984 Writer helper and deterministic 3-cycle chain generated")

if __name__=="__main__":
    main()
