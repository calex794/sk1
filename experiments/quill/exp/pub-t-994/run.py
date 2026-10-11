#!/usr/bin/env python3
"""Public-POI, source-pinned LibreOffice metamorphic importer test.

No Microsoft Publisher, no private PUB, no raw source/output in artifacts.
Unsupported or insensitive controls are reported, never promoted to a law.
"""
from __future__ import annotations
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

try:
    import olefile
except ImportError:
    raise SystemExit("Dependency olefile is missing")

PIN = "ae62bb5116b9aee19ebd5834e3a82066132c9f7f"
SOURCES = {
    "60685": {"path": "test-data/publisher/60685.pub",
              "blob": "37d3dce70e1786e948edd5592527f90be1fae2ff",
              "size": 119296, "natural_high": 0x01},
    "51318": {"path": "test-data/publisher/51318.pub",
              "blob": "728811c92dff5694520e56b6c020533b29d5295d",
              "size": 88576, "natural_high": 0x5A},
}
STREAM = ("Quill", "QuillSub", "CONTENTS")
TYPE_LEN = {0:0,5:0,8:0,10:0,7:2,16:2,18:2,24:2,26:2,
            32:4,34:4,88:4,104:4,112:4,184:4,
            40:8,56:16,72:24,
            128:-1,130:-1,136:-1,138:-1,144:-1,152:-1,160:-1}
NS_TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
NS_DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"


def u16(b, p): return struct.unpack_from("<H", b, p)[0]
def u32(b, p): return struct.unpack_from("<I", b, p)[0]
def sha(b): return hashlib.sha256(b).hexdigest()


def get_source(spec):
    url = ("https://raw.githubusercontent.com/apache/poi/" +
           PIN + "/" + spec["path"])
    raw = None
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={"User-Agent":"SK1-QUILL-PUB-T-994"})
            with urllib.request.urlopen(request, timeout=45) as response:
                raw = response.read(30_000_000)
            break
        except Exception:
            if attempt == 2:
                raise ValueError("public_source_download_failed")
            time.sleep(2)
    if len(raw) != spec["size"]:
        raise ValueError("source_size_mismatch")
    blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    if blob != spec["blob"]:
        raise ValueError("source_git_blob_mismatch")
    return raw


def descriptors(q):
    out = []
    cursor = 0x18
    visited = set()
    while cursor != 0xFFFFFFFF:
        if cursor in visited or cursor + 8 > len(q):
            raise ValueError("quill_descriptor_cycle")
        visited.add(cursor)
        n = u16(q,cursor+2)
        nxt = u32(q,cursor+4)
        if n > 4096 or cursor+8+n*24>len(q):
            raise ValueError("quill_descriptor_bounds")
        for k in range(n):
            p = cursor+8+k*24
            if u16(q,p) != 24: raise ValueError("quill_descriptor_marker")
            name = bytes(q[p+2:p+6])
            tag = u16(q,p+6)
            a,b = u32(q,p+16),u32(q,p+20)
            if a+b>len(q): raise ValueError("quill_payload_bounds")
            out.append((name,tag,a,b))
        cursor=nxt
    return out


def one(desc,name,tag=None):
    matches=[x for x in desc if x[0]==name and (tag is None or x[1]==tag)]
    if len(matches)!=1: raise ValueError("expected_single_descriptor")
    return matches[0]


def paragraph_properties(q,stsh):
    _,_,s,length=stsh
    n=u32(q,s+4)
    if not 2<=n<=10000 or 20+4*n>length:
        raise ValueError("stsh_record_index")
    offsets=[u32(q,s+20+4*i) for i in range(n)]
    if offsets != sorted(set(offsets)):
        raise ValueError("stsh_nonmonotone_offsets")
    rows=[]
    for i in range(1,n,2):
        start=s+20+offsets[i]
        end=(s+20+offsets[i+1] if i+1<n else s+length)
        if not start+8<=end<=s+length:
            raise ValueError("stsh_record_bounds")
        pos=start+6
        props=[]
        while pos<end-2:
            if pos+2>end-2: raise ValueError("stsh_short_block")
            prop,typ=q[pos],q[pos+1]
            body=TYPE_LEN.get(typ)
            if body is None: raise ValueError("stsh_unsupported_typed_block")
            if body==-1:
                if pos+6>end-2: raise ValueError("stsh_short_variable")
                body=u32(q,pos+2)
            if body>1_000_000 or pos+2+body>end-2:
                raise ValueError("stsh_property_bounds")
            props.append((prop,typ,pos,body))
            pos+=2+body
        if pos!=end-2:raise ValueError("stsh_unconsumed_bytes")
        rows.append({"index":i,"props":props})
    return rows


def mutated_quill(q, modifications):
    new=bytearray(q)
    visited=set()
    for pos,value in modifications:
        if not 0<=pos<len(q) or pos in visited:
            raise ValueError("mutation_offset_or_duplicate")
        visited.add(pos)
        if new[pos]==value:
            raise ValueError("mutation_is_noop")
        new[pos]=value
    diff=sum(a!=b for a,b in zip(q,new))
    if diff!=len(modifications): raise ValueError("mutation_diff_mismatch")
    return bytes(new), diff


def prepare_mutations(q, high):
    d=descriptors(q)
    stsh=one(d,b"STSH",1)
    heads=[one(d,b"STSH",i) for i in range(3)]+[one(d,b"FONT")]
    para=paragraph_properties(q,stsh)
    chosen=[]
    all_30=0
    for row in para:
        ids=[p[0] for p in row["props"]]
        props30=[p for p in row["props"] if p[0]==0x30 and p[1]==0x12 and p[3]==2]
        all_30+=len(props30)
        if len(props30)==1 and 0x13 not in ids:
            _,_,pos,_=props30[0]
            if q[pos+2]==5 and q[pos+3]==high:
                chosen.append(pos+3)
    if not chosen: raise ValueError("natural_nonzero_30_not_found")
    text=one(d,b"TEXT")
    _,_,off,length=text
    if length%2:raise ValueError("text_odd_length")
    positive=[]
    for pos in range(off,off+length,2):
        cp=u16(q,pos)
        if 0xD800<=cp<=0xDFFF:continue
        ch=chr(cp)
        if ch.isalpha() or ch.isdecimal():
            # Change a meaningful text code unit without modifying length.
            target=ord("X") if cp!=ord("X") else ord("Y")
            if q[pos]!=target&255:positive.append((pos,target&255))
            if q[pos+1]!=(target>>8):positive.append((pos+1,target>>8))
    if not positive:
        raise ValueError("no_positive_text_control")
    arms={
        "id30_first_zero":[(chosen[0],0)],
        "id30_first_ff":[(chosen[0],255)],
        "id30_all_zero":[(p,0) for p in chosen],
        "header_stsh1_xor":[(stsh[2]+8,q[stsh[2]+8]^0x5A)],
        "headers_four_xor":[(e[2]+8,q[e[2]+8]^0x5A) for e in heads],
        "text_positive":positive,
    }
    if high==0x5A:  # id30_first_ff and id30_first_zero both non-noop
        pass
    stats={
        "paragraph_records":len(para),
        "natural_nonzero_absent13_records":len(chosen),
        "count_30_properties":all_30,
        "original_headers_equal":len({u32(q,e[2]+8) for e in heads})==1,
        "utf16_text_units":length//2,
        "positive_text_changed_bytes":len(positive),
    }
    return arms,stats


def write_variant(original,q_new,out):
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_bytes(original)
    with olefile.OleFileIO(str(out), write_mode=True) as doc:
        was=doc.openstream(STREAM).read()
        if len(was)!=len(q_new):raise ValueError("quill_change_size")
        doc.write_stream(STREAM,q_new)
    after=out.read_bytes()
    if len(after)!=len(original):raise ValueError("cfb_change_size")
    with olefile.OleFileIO(str(out)) as doc:
        now=doc.openstream(STREAM).read()
    if now!=q_new:raise ValueError("quill_roundtrip_mismatch")
    return sum(a!=b for a,b in zip(original,after))


def import_odg(case_dir,lo):
    input_file=case_dir/"input.pub"
    dst=case_dir/"out"
    dst.mkdir()
    profile=case_dir/"profile"
    args=[lo, "-env:UserInstallation="+profile.absolute().as_uri(),
          "--headless","--convert-to","odg","--outdir",str(dst),str(input_file)]
    try:
        p=subprocess.run(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                         timeout=120,check=False)
        code=p.returncode
    except subprocess.TimeoutExpired:
        return {"imported":False,"error_class":"timeout"}
    out=dst/"input.odg"
    if not out.is_file():return {"imported":False,"exit_code":code}
    try:
        with zipfile.ZipFile(out) as z:
            if z.testzip() is not None:raise ValueError("bad_crc")
            content=z.read("content.xml")
            styles=z.read("styles.xml")
        c=ET.fromstring(content)
        ET.fromstring(styles)
    except Exception:
        return {"imported":False,"exit_code":code,"error_class":"unreadable_odg"}
    return {
      "imported":True,"exit_code":code,
      "content_sha256":sha(content),"styles_sha256":sha(styles),
      "text_paragraph_nodes":sum(1 for _ in c.iter(NS_TEXT+"p")),
      "draw_page_nodes":sum(1 for _ in c.iter(NS_DRAW+"page")),
      "rendered_nonspace_char_count":sum(len("".join(x.itertext()).strip())
          for x in c.iter(NS_TEXT+"p")),
    }


def main():
    if len(sys.argv)!=2:raise SystemExit("usage: run.py OUTPUT_DIRECTORY")
    output=Path(sys.argv[1]).resolve()
    output.mkdir(parents=True,exist_ok=True)
    report={"schema":"sk1-quill-exp-pub-t-994.v1","task_id":"PUB-T-994",
            "poi_commit":PIN,"native_publisher":"NOT_EVALUATED",
            "method":"LibreOffice Draw/libmspub public-only metamorphic importer",
            "samples":{}}
    lo=shutil.which("libreoffice") or shutil.which("soffice")
    if not lo:raise ValueError("missing_libreoffice")
    version=subprocess.run([lo,"--version"],capture_output=True,text=True,check=True)
    report["libreoffice_version"]=version.stdout.strip()
    report["olefile_version"]=getattr(olefile,"__version__","unknown")
    with tempfile.TemporaryDirectory(prefix="sk1-quill-994-") as tmp:
        parent=Path(tmp)
        for name,spec in SOURCES.items():
            row={"git_blob_sha1":spec["blob"],"input_size":spec["size"],
                 "natural_high":spec["natural_high"]}
            report["samples"][name]=row
            try:
                original=get_source(spec)
                row["input_sha256"]=sha(original)
                with olefile.OleFileIO(io.BytesIO(original)) as doc:
                    if not doc.exists(STREAM):raise ValueError("quill_missing")
                    q=doc.openstream(STREAM).read()
                arms,stats=prepare_mutations(q,spec["natural_high"])
                row["physical_controls"]=stats
                choices={"baseline_one":(q,0),"baseline_two":(q,0)}
                for aname,mods in arms.items():
                    q_new,diff=mutated_quill(q,mods)
                    choices[aname]=(q_new,diff)
                row["cases"]={}
                for case,(quill,expected_diff) in choices.items():
                    p=parent/name/case
                    actual_diff=write_variant(original,quill,p/"input.pub")
                    if actual_diff!=expected_diff:
                        raise ValueError("unexpected_nonquill_mutation")
                    item=import_odg(p,lo)
                    item["input_changed_bytes"]=actual_diff
                    row["cases"][case]=item
                # Negative control uses the same .pub path with corrupt CFB magic.
                negdir=parent/name/"broken_magic"
                negdir.mkdir(parents=True)
                invalid=bytearray(original);invalid[0]^=0xFF
                (negdir/"input.pub").write_bytes(invalid)
                neg=import_odg(negdir,lo)
                neg["input_changed_bytes"]=1
                row["cases"]["broken_magic"]=neg
                base=row["cases"]["baseline_one"]
                repeat=row["cases"]["baseline_two"]
                def signature(x):return (x.get("content_sha256"),x.get("styles_sha256"))
                stable=base["imported"] and repeat["imported"] and signature(base)==signature(repeat)
                positive=row["cases"]["text_positive"]
                sensitive=stable and positive["imported"] and signature(positive)!=signature(base)
                negative_ok=not neg["imported"]
                eligible=stable and sensitive and negative_ok and base.get("rendered_nonspace_char_count",0)>0
                row["baseline_stable"]=stable
                row["positive_control_detected"]=sensitive
                row["negative_control_rejected"]=negative_ok
                row["nonempty_import"]=base.get("rendered_nonspace_char_count",0)>0
                row["interpretation_eligible"]=eligible
                mutated=["id30_first_zero","id30_first_ff","id30_all_zero",
                         "header_stsh1_xor","headers_four_xor"]
                row["mutation_results"]={
                    k:("FAILED_IMPORT" if not row["cases"][k]["imported"]
                       else "DIFFERENT_PROJECTION" if signature(row["cases"][k])!=signature(base)
                       else "SAME_PROJECTION")
                    for k in mutated
                }
                row["conclusion"] = ("INTERPRETABLE" if eligible else "NON_DISCRIMINATING")
                row["status"]="EXECUTED"
            except Exception as exc:
                # Error labels only, never paths, source text or raw bytes.
                row["status"]="NOT_EVALUATED"
                row["error_class"]=(str(exc) if str(exc) in {
                    "public_source_download_failed","source_size_mismatch",
                    "source_git_blob_mismatch","quill_missing","quill_descriptor_bounds",
                    "quill_descriptor_marker","quill_payload_bounds",
                    "stsh_record_index","stsh_nonmonotone_offsets",
                    "stsh_record_bounds","stsh_unsupported_typed_block",
                    "stsh_short_variable","stsh_property_bounds",
                    "stsh_unconsumed_bytes","natural_nonzero_30_not_found",
                    "no_positive_text_control","quill_change_size",
                    "cfb_change_size","quill_roundtrip_mismatch",
                    "unexpected_nonquill_mutation"}
                    else type(exc).__name__)
    (output/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    valid=sum(s.get("status")=="EXECUTED" for s in report["samples"].values())
    interpret=sum(s.get("interpretation_eligible",False) for s in report["samples"].values())
    print(f"SK1 PUB-T-994 executed={valid}/2 interpretation_eligible={interpret}/2; native=NOT_EVALUATED")
    return 0 if valid==2 else 2


if __name__=="__main__":
    raise SystemExit(main())
