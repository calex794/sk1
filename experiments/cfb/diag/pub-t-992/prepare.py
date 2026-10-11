#!/usr/bin/env python3
"""PUB-T-992: derive only a 29-or-fewer natural-source census variant
from exact, unchanged T987 Quill parser, and the original T984 Writer probe.
No product or Writer code is committed or reimplemented here.
"""
from pathlib import Path
import argparse,subprocess
T987_PIN="fa714fe958999325649430dad53c10edac42246a"
T987_BLOB="c8ebf6988b1c4beabef1b9526228895269b7c199"
T984_PIN="14ac75ae0346b3bdbeeada110e1f463dda6cbb27"
T963_PIN="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
T971_PIN="cd38c8d6a545737f9f99821076340505db5e149c"
OLD_COUNT='ensure!(files.len()==625,"donor inventory count not pinned to 625");'
NEW_COUNT='ensure!(!files.is_empty() && files.len()<=29,"unexpected source roster count");'
OLD_PLANNED='"planned_pub":625,'
NEW_PLANNED='"planned_pub":all,'
OLD_SCHEMA='"schema":"sk1.cfb-diag-pub-t-987.census.v1",'
NEW_SCHEMA='"schema":"sk1.cfb-diag-pub-t-992.census.v1",'
def git(path,*args):
    return subprocess.check_output(["git",*args],cwd=path,text=True).strip()
def once(s,old,new,label):
    if s.count(old)!=1:raise ValueError(f"pin drift {label}: {s.count(old)}")
    return s.replace(old,new)
def main():
    ap=argparse.ArgumentParser()
    for x in ("ref_987","ref_984","ref_963","ref_971"):
        ap.add_argument("--"+x.replace("_","-"),required=True,type=Path)
    a=ap.parse_args()
    r987=a.ref_987.resolve(strict=True);r984=a.ref_984.resolve(strict=True)
    r963=a.ref_963.resolve(strict=True);r971=a.ref_971.resolve(strict=True)
    for root,pin in [(r987,T987_PIN),(r984,T984_PIN),(r963,T963_PIN),(r971,T971_PIN)]:
        if git(root,"rev-parse","HEAD")!=pin:raise ValueError("scientific parent commit drift")
    f=r987/"experiments/cfb/diag/pub-t-987/natural_syid_census.rs"
    if git(r987,"hash-object",str(f))!=T987_BLOB:raise ValueError("original Quill scanner git blob drift")
    data=f.read_text(encoding="utf-8")
    data=once(data,OLD_COUNT,NEW_COUNT,"input roster cardinality")
    data=once(data,OLD_PLANNED,NEW_PLANNED,"dynamic source count")
    data=once(data,OLD_SCHEMA,NEW_SCHEMA,"source-safe schema name")
    output=Path(__file__).resolve().parent/"derived_census.rs"
    if output.exists():raise ValueError("refusing to overwrite generated census")
    output.write_text(data,encoding="utf-8")
    # Upstream generator validates the exact T963 and T971 Rust blobs.
    subprocess.run(["python3",
        str(r984/"experiments/cfb/val/pub-t-984/prepare.py"),
        "--ref-inverse",str(r963),"--ref-corpus",str(r971)],check=True)
    source=r984/"experiments/cfb/val/pub-t-984/real_inverse.rs"
    if not source.exists():raise ValueError("inherited Writer not generated")
    print("PUB-T-992: original frozen T987 Quill scanner + untouched T984 Writer derived on worker only")
if __name__=="__main__":main()
