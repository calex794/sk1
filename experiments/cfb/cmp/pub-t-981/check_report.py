#!/usr/bin/env python3
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); r=json.loads((p/"report.json").read_text()); rows=r["sources"]
err=[]
if r["source_count"]!=12 or r["sha_verified_count"]!=12:err.append("12 verified inputs required")
for fmt in ("DOC","XLS","PPT","PUB"):
 if sum(len(x.get("roots",[])) for x in rows if x["format"]==fmt)<1:err.append("missing grammar-validated root: "+fmt)
if not any(x.get("fopt_ids") for x in rows if x["format"]=="XLS"):err.append("missing XLS FOPT")
if not all(all(x is True for x in v.get("controls",[])) for v in rows if v["status"]=="SHA_VERIFIED_AND_SCANNED"):err.append("corrupt-root negative guard failed")
if err:print("PARTIAL/FAIL:",*err,sep="\n");sys.exit(1)
print("VERIFIED 12 pinned files, 4 format roots, XLS FOPT, negative controls")
