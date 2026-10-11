#!/usr/bin/env python3
"""Independent PUB-T-981 structured evidence audit; no source document bytes."""
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
FORMATS=("DOC","XLS","PPT","PUB")
SHA=re.compile(r"^[a-f0-9]{64}$")
TYPE=re.compile(r"^0xF[01][0-9A-F]{2}$")

def check(cond,msg):
    if not cond:raise ValueError("T981 EVIDENCE FAIL: "+msg)

def verify(directory):
    p=Path(directory)
    check(p.is_dir() and {f.name for f in p.iterdir()}=={"report.json","records.json"},
          "missing/unexpected output files")
    s=importlib.util.spec_from_file_location("original_t981_run",HERE/"run.py")
    assert s and s.loader
    mod=importlib.util.module_from_spec(s);s.loader.exec_module(mod)
    r=json.loads((p/"report.json").read_text())
    raw=json.loads((p/"records.json").read_text())
    check(r["schema"]=="sk1.cfb.cmp.pub-t-981.v1" and
          raw["schema"]=="sk1.cfb.cmp.pub-t-981.records.v1" and
          r["apache_poi_commit"]==mod.REV==
          "ae62bb5116b9aee19ebd5834e3a82066132c9f7f",
          "original source revision/schema mismatch")
    check(r["source_count"]==r["sha_verified_count"]==len(mod.INPUT)==12,
          "source denominator")
    sources={}
    total_roots=0
    for row,inp in zip(r["sources"],mod.INPUT):
        fmt,name,n,sha=inp
        check((row["format"],row["source"],row["source_bytes"],
               row["git_blob_sha1"])==(fmt,name,n,sha),
              "pinned Git blob input mismatch")
        check(row["status"]=="SHA_VERIFIED_AND_SCANNED" and
              SHA.fullmatch(row["source_sha256"]),
              "unverified source file")
        roots=row["roots"]
        check(bool(roots) and len(roots)==len(row["controls"]) and
              all(x is True for x in row["controls"]),
              "invalid/censored corruption-length negative controls")
        total_roots+=len(roots)
        scopes={x["scope"]:x["bytes"] for x in row["scopes"]}
        check(len(scopes)==len(row["scopes"]), "scope collision")
        for root in roots:
            check(root["scope"] in scopes and root["offset"]>=0 and
                  root["length"]>=8 and
                  root["offset"]+root["length"]<=scopes[root["scope"]] and
                  root["kind"] in ("0xF000","0xF002"),
                  "root outside source stream/BIFF slice")
            if fmt=="XLS":
                check("/BIFF_00EB@" in root["scope"] or
                      "/BIFF_00EC@" in root["scope"],
                      "XLS OfficeArt not in BIFF drawing carrier")
            if fmt=="PUB":
                check(root["scope"].lower().endswith("escher/escherstm"),
                      "PUB OfficeArt not in EscherStm")
        sources[(fmt,name)]=row
    records=raw["records"]
    check(isinstance(records,list) and len(records)>0 and len(records)<25000,
          "invalid record list")
    count=Counter();types=defaultdict(Counter);props=defaultdict(Counter)
    anchors=defaultdict(Counter);types4=defaultdict(set);props4=defaultdict(set)
    shaformats=defaultdict(set);seen=set()
    basefields={"scope","offset","type","ver","instance","length","payload_len",
                "sha256_record","format","source"}
    byrecord={}
    for q in records:
        check(set(q)==basefields or
              (len(set(q)-basefields)==1 and basefields<=set(q) and
               next(iter(set(q)-basefields)) in
               ("fopt","fdgg","fdg","anchor_bytes")),
              "unrecognized metadata; potential raw payload leak")
        key=(q["format"],q["source"])
        check(key in sources and isinstance(q["type"],str) and
              TYPE.fullmatch(q["type"]) and SHA.fullmatch(q["sha256_record"]),
              "unanchored format/file/type/hash")
        check(all(type(q[k]) is int for k in
                  ("offset","ver","instance","length","payload_len")) and
              q["offset"]>=0 and q["length"]>=8 and
              q["length"]==q["payload_len"]+8 and
              0<=q["ver"]<=15 and 0<=q["instance"]<4096,
              "record numeric header invalid")
        rs=sources[key]["roots"]
        check(any(x["scope"]==q["scope"] and x["offset"]<=q["offset"] and
                  q["offset"]+q["length"]<=x["offset"]+x["length"] for x in rs),
              "record not contained by validated root")
        ident=(*key,q["scope"],q["offset"],q["length"],q["type"])
        check(ident not in seen,"duplicate source record")
        seen.add(ident)
        byrecord[ident]=q
        count[key]+=1;types[key][q["type"]]+=1;types4[key[0]].add(q["type"])
        shaformats[q["sha256_record"]].add(key[0])
        if "fopt" in q:
            a=q["fopt"]
            check(q["type"] in ("0xF00B","0xF121","0xF122") and
                  a["valid"] is True and len(a["entries"])==q["instance"] and
                  0<=a["complex_bytes"] and
                  q["instance"]*6+a["complex_bytes"]<=q["payload_len"],
                  "FOPT instance or complex payload")
            for v in a["entries"]:
                check(set(v)=={"id","fComplex","fBid"} and
                      type(v["id"]) is int and 0<=v["id"]<16384 and
                      type(v["fComplex"]) is type(v["fBid"]) is bool,
                      "FOPT entry ID/flags")
                props[key][v["id"]]+=1;props4[key[0]].add(v["id"])
        if "fdgg" in q:
            d=q["fdgg"]
            check(q["type"]=="0xF006" and d["length_valid"] is True and
                  d["cidcl"]>0 and q["payload_len"]==16+8*(d["cidcl"]-1),
                  "FDGG length")
        if "fdg" in q:
            check(q["type"]=="0xF008" and
                  q["fdg"]=={"length_valid":True} and q["payload_len"]==8,
                  "FDG length")
        if "anchor_bytes" in q:
            check(q["type"]=="0xF010" and
                  q["anchor_bytes"]==q["payload_len"],
                  "host F010 length")
            anchors[key][str(q["anchor_bytes"])]+=1
    for key,src in sources.items():
        check(src["records_total"]==count[key] and
              src["record_types"]==dict(types[key]) and
              src["fopt_ids"]=={str(i):n for i,n in props[key].items()} and
              src["anchor_lengths"]==dict(anchors[key]),
              "per-source type/prop/anchor tally mismatch")
    pairs=[]
    for i,a in enumerate(FORMATS):
        for b in FORMATS[i+1:]:
            pairs.append({"left":a,"right":b,
                          "shared_types":sorted(types4[a]&types4[b]),
                          "shared_fopt_ids":sorted(props4[a]&props4[b])})
    check(len(r["pairwise"])==len(pairs)==6,"missing pairs")
    for reported,actual in zip(r["pairwise"],pairs):
        check(reported["left"]==actual["left"] and
              reported["right"]==actual["right"] and
              reported["shared_types"]==actual["shared_types"] and
              sorted(map(int,reported["shared_fopt_ids"]))==actual["shared_fopt_ids"],
              "incorrect pairwise intersection")
    exact={sha:sorted(f) for sha,f in shaformats.items() if len(f)>=2}
    claimed=r["exact_record_cross_format"]
    check(len(claimed)==len(exact) and
          len({x["sha256_record"] for x in claimed})==len(exact) and
          all(exact.get(x["sha256_record"])==x["formats"] for x in claimed),
          "unsupported exact byte-identical hash claims")
    shared_types=sorted(set.intersection(*(types4[f] for f in FORMATS)))
    shared_ids=sorted(set.intersection(*(props4[f] for f in FORMATS)))
    f009=[sha for sha,f in shaformats.items() if f==set(FORMATS) and
          any(q["sha256_record"]==sha and q["type"]=="0xF009"
              for q in records)]
    check(bool(f009),"missing real four-way identical F009 bytes")
    check(total_roots==sum(len(s["controls"]) for s in sources.values()),
          "negative control denominator")
    print(json.dumps({
        "audit":"SUCCESS","sources":len(sources),"records":len(records),
        "roots":total_roots,"invalid_length_negative_controls":total_roots,
        "four_way_common_record_types":shared_types,
        "four_way_common_fopt_ids":shared_ids,
        "exact_record_crossformat_sha_sets":len(exact),
        "four_way_exact_F009_sha":f009,
        "original_CFB_bytes_refetched_by_this_auditor":False,
        "native_publisher_acceptance":"NOT_EVALUATED"
    },sort_keys=True))

if __name__=="__main__":
    check(len(sys.argv)==2,"output folder argument required")
    verify(sys.argv[1])
