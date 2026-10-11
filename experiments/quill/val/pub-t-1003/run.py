#!/usr/bin/env python3
"""PUB-T-1003: real Rust Reader on one independent 60685.pub: original/high-zero/low-zero.

No raw PUB, Quill, Story text or Publisher binaries are committed or uploaded.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.request import urlopen, Request

import olefile

RAR_PIN="b224a614af48c273b2d4bc0881793cf0217cc16d"
T994_PIN="87a6733516ad6ffd1b6b97a3176f359bfeb60ca1"
HELPER_BLOB="cd92e00942f0a6949e72785bb1605fb70620de22"
SOURCE_PIN="942d95d85b15d0dfdb3bc9ba1b4f273f277757c8"
SOURCE_BLOB="37d3dce70e1786e948edd5592527f90be1fae2ff"
SOURCE_SHA256="0d3cecf0ff000a20931d0de3ebc48040bea10e03833ade3f9902f996c20e7184"
SOURCE_SIZE=119296
QUILL_SIZE=26112
STREAM=("Quill","QuillSub","CONTENTS")


def git(args,root):
    return subprocess.run(["git",*args],cwd=root,check=True,
                          capture_output=True,text=True,timeout=25).stdout.strip()

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def load_helper(root):
    if git(["rev-parse","HEAD"],root)!=T994_PIN:
        raise ValueError("PRIOR_REVISION_DRIFT")
    path="experiments/quill/exp/pub-t-994/run.py"
    if git(["hash-object",path],root)!=HELPER_BLOB:
        raise ValueError("PRIOR_BLOB_DRIFT")
    spec=importlib.util.spec_from_file_location("sk1_t1003_t994",root/path)
    if not spec or not spec.loader:
        raise ValueError("PRIOR_IMPORT_FAIL")
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def source():
    url="https://raw.githubusercontent.com/apache/poi/"+SOURCE_PIN+"/test-data/publisher/60685.pub"
    with urlopen(Request(url,headers={"User-Agent":"SK1-PUB-T-1003"}),timeout=45) as response:
        original=response.read(300000)
    if len(original)!=SOURCE_SIZE or digest(original)!=SOURCE_SHA256:
        raise ValueError("PUB_SOURCE_SHA256_OR_SIZE_DRIFT")
    blob=hashlib.sha1(b"blob "+str(len(original)).encode("ascii")+bytes([0])+original).hexdigest()
    if blob!=SOURCE_BLOB:
        raise ValueError("PUB_SOURCE_BLOB_DRIFT")
    return original

def diff(a,b):
    if len(a)!=len(b):
        raise ValueError("PUB_PHYSICAL_SIZE_DRIFT")
    return sum(x!=y for x,y in zip(a,b))

def t1001_second_source_structure(prior,q):
    desc=prior.descriptors(q)
    stsh=prior.one(desc,b"STSH",1)
    text=prior.one(desc,b"TEXT")
    syid=prior.one(desc,b"SYID")
    strs=prior.one(desc,b"STRS")
    fdpp=prior.one(desc,b"FDPP")
    if text[2:]!=(512,3770):
        raise ValueError("TEXT_SOURCE_DRIFT")
    if prior.u32(q,syid[2]+4)!=4:
        raise ValueError("SYID_COUNT_DRIFT")
    ids=[prior.u32(q,syid[2]+8+j*4) for j in range(4)]
    if ids!=[2,3,4,5]:
        raise ValueError("SYID_IDS_DRIFT")
    if prior.u32(q,strs[2])!=4:
        raise ValueError("STRS_COUNT_DRIFT")
    sp=prior.u32(q,strs[2]+4)
    lengths=[prior.u32(q,strs[2]+4+sp+4*j) for j in range(4)]
    if lengths!=[1882,1,1,1] or sum(lengths)*2!=text[3]:
        raise ValueError("STRS_UTF16_LENGTH_DRIFT")
    rows=prior.paragraph_properties(q,stsh)
    if len(rows)!=36:
        raise ValueError("STSH1_STYLE_COUNT_DRIFT")
    known={}
    high_offsets=[]
    low_offsets=[]
    for row in rows:
        style_idx=(row["index"]-1)//2
        selected=[v for v in row["props"] if v[0]==0x04]
        if not selected:
            continue
        if len(selected)!=1 or selected[0][1]!=0x12 or selected[0][3]!=2:
            raise ValueError("STSH1_ALIGN_WIRE_DRIFT")
        pos=selected[0][2]
        value=prior.u16(q,pos+2)
        known[style_idx]=value
        if style_idx in (21,23):
            if value!=0x0102:
                raise ValueError("STSH1_0102_SOURCE_DRIFT")
            low_offsets.append(pos+2)
            high_offsets.append(pos+3)
    if known!={4:2,5:2,21:0x0102,23:0x0102} or len(high_offsets)!=2:
        raise ValueError("STSH1_ALIGNMENT_STYLES_DRIFT")
    _,_,fdstart,fdlength=fdpp
    count=prior.u16(q,fdstart)
    if count!=23:
        raise ValueError("FDPP_RECORD_COUNT_DRIFT")
    observations=[]
    for ordinal in (20,21,22):
        end_text=prior.u32(q,fdstart+8+ordinal*4)
        relative=prior.u16(q,fdstart+8+4*count+2*ordinal)
        start=fdstart+relative
        if start+4>fdstart+fdlength:
            raise ValueError("FDPP_STYLE_BOUNDS")
        style_length=prior.u32(q,start)
        stop=start+style_length
        if style_length<4 or stop>fdstart+fdlength:
            raise ValueError("FDPP_STYLE_BOUNDS")
        cursor=start+4
        selectors=[]
        explicit_alignment=False
        while cursor<stop:
            if cursor+2>stop:
                raise ValueError("FDPP_BLOCK_SHORT")
            tag,wire=q[cursor],q[cursor+1]
            width=prior.TYPE_LEN.get(wire)
            if width is None:
                raise ValueError("FDPP_BLOCK_WIRE_DRIFT")
            if width==-1:
                if cursor+6>stop:
                    raise ValueError("FDPP_VAR_BOUNDS")
                width=prior.u32(q,cursor+2)
            if cursor+2+width>stop or width<0:
                raise ValueError("FDPP_BLOCK_BOUNDS")
            if tag==0x19 and wire==0x1A and width==2:
                selectors.append(prior.u16(q,cursor+2))
            if tag==0x04:
                explicit_alignment=True
            cursor+=2+width
        observations.append((ordinal,end_text,selectors,explicit_alignment))
    expected=[(20,4278,[21],False),(21,4280,[21],False),(22,4282,[23],False)]
    if observations!=expected:
        raise ValueError("FDPP_STSH1_SELECTOR_DRIFT")
    return high_offsets,low_offsets,{
      "stsh1_paragraph_style_count":len(rows),
      "natural_known_alignment_style_count":len(known),
      "natural_nonzero_high_style_count":len(high_offsets),
      "source_selected_nonzero_high_fdpp_range_count":len(observations),
      "source_selected_style_indices":[21,21,23],
      "source_story_utf16_lengths":lengths,
      "source_utf16_unit_count":sum(lengths),
      "source_text_bytes":text[3],
      "source_story_id_count":len(ids),
      "explicit_fdpp_override_in_selected_ranges":0
    }

def run_rust(exe,input_file,out):
    p=subprocess.run([str(exe),str(input_file),str(out)],
                     check=False,capture_output=True,timeout=120)
    if p.returncode!=0 or not out.is_file():
        raise ValueError("RUST_READER_PROBE_EXECUTION_FAILED")
    return json.loads(out.read_text(encoding="utf-8"))

def key(r):
    return (r["alignment"],r["source_value"],r["story_utf16_units"],
            r["story_scalars"],r["scalar_start"],r["scalar_end"],
            r["applies_to_original_story_text"])

def measure_runs(reader):
    return Counter(key(x) for x in reader.get("paragraph_alignments",[]))

def main():
    if len(sys.argv)!=5:
        raise SystemExit("usage: run.py RAR2_DIR T994_DIR REAL_RUST_BIN OUTPUT_JSON")
    rar,ref,exe,out=[Path(x).resolve() for x in sys.argv[1:]]
    if git(["rev-parse","HEAD"],rar)!=RAR_PIN:
        raise ValueError("PRODUCT_PIN_DRIFT")
    if not exe.is_file():
        raise ValueError("REAL_RUST_READER_BIN_MISSING")
    prior=load_helper(ref)
    original=source()
    with olefile.OleFileIO(io.BytesIO(original)) as ole:
        q=ole.openstream(STREAM).read()
    if len(q)!=QUILL_SIZE:
        raise ValueError("QUILL_STREAM_SIZE_DRIFT")
    high,low,physical=t1001_second_source_structure(prior,q)
    report={
      "schema":"sk1-pub-t1003-second-source-rust-ab/v1",
      "task_id":"PUB-T-1003",
      "source":{"name":"60685.pub","apache_poi_commit":SOURCE_PIN,
                "source_git_blob_sha1":SOURCE_BLOB,"original_sha256":SOURCE_SHA256,
                "original_byte_size":SOURCE_SIZE},
      "rar2_commit":RAR_PIN,
      "t994_parser_commit":T994_PIN,
      "t994_parser_git_blob":HELPER_BLOB,
      "physical_source":physical,
      "microsoft_publisher_native_evaluated":False,
      "libreoffice_retested":False,
      "rar2_product_modified":False,
      "visual_fidelity_tested":False,
      "variants":[]
    }
    with tempfile.TemporaryDirectory(prefix="sk1-60685-t1003-") as private:
        temp=Path(private)
        for name,patch in (
            ("original",[]),
            ("high_zero",[(offset,0) for offset in high]),
            ("low_zero",[(offset,0) for offset in low])
        ):
            pub=temp/(name+".pub")
            if patch:
                quill_new,change_count=prior.mutated_quill(q,patch)
                prior.write_variant(original,quill_new,pub)
            else:
                pub.write_bytes(original)
                quill_new=q
                change_count=0
            changed=diff(original,pub.read_bytes())
            if changed!=change_count or changed!=(0 if name=="original" else 2):
                raise ValueError("NON_LOCAL_PUB_MUTATION")
            with olefile.OleFileIO(str(pub)) as ole:
                after=ole.openstream(STREAM).read()
            if after!=quill_new:
                raise ValueError("CFB_QUILL_WRITE_DID_NOT_ROUNDTRIP")
            rust=run_rust(exe,pub,temp/(name+".json"))
            report["variants"].append({
                "name":name,
                "changed_physical_bytes":changed,
                "changed_quill_bytes":change_count,
                "rust":rust
            })
        baseline,hi,lo=[v["rust"] for v in report["variants"]]
        all_open=all(v.get("opened") is True for v in (baseline,hi,lo))
        stable_stories=all_open and (
            sorted((s["utf16_units"],s["scalars"]) for s in baseline["stories"])
            == sorted((s["utf16_units"],s["scalars"]) for s in hi["stories"])
            == sorted((s["utf16_units"],s["scalars"]) for s in lo["stories"])
        )
        stable_pages=all_open and (
            baseline["pages"]==hi["pages"]==lo["pages"] and
            baseline["text_fragment_count"]==hi["text_fragment_count"]
              ==lo["text_fragment_count"]
        )
        b,h,l=[measure_runs(v) for v in (baseline,hi,lo)]
        added_high=h-b
        removed_high=b-h
        changed_low=l!=b
        expected=("Right",2,1,1,0,1,True)
        hypothesis_confirmed=(
            all_open and stable_stories and stable_pages
            and added_high==Counter({expected:3}) and not removed_high
            and not changed_low
        )
        report["controls"]={
            "three_variants_opened":all_open,
            "pages_and_fragment_counts_stable":stable_pages,
            "reader_story_extents_stable":stable_stories,
            "physical_byte_change_counts_correct":True,
            "low_control_run_multiset_unchanged":not changed_low,
            "high_control_adds_exactly_three_single_character_right_runs":(
                added_high==Counter({expected:3}) and not removed_high),
        }
        report["run_counts"]={
            "original":sum(b.values()),
            "high_zero":sum(h.values()),
            "low_zero":sum(l.values()),
            "high_additions":sum(added_high.values()),
            "high_removals":sum(removed_high.values()),
            "low_has_changes":changed_low,
            "high_added_expected_single_character_right":added_high.get(expected,0),
        }
        if not all_open or not stable_stories or not stable_pages:
            report["verdict"]="NOT_EVALUATED"
        elif hypothesis_confirmed:
            report["verdict"]="CONFIRMED_SECOND_SOURCE_HIGH_BYTE_ALIGNMENT_GAP"
        else:
            report["verdict"]="HYPOTHESIS_NOT_CONFIRMED_ON_SECOND_SOURCE"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True)+"\n",encoding="utf-8")
    print("PUB-T-1003 true Rust Reader:",report["verdict"],
          "run counts",report["run_counts"],"stable",report["controls"])
    return 0 if report["verdict"]!="NOT_EVALUATED" else 2

if __name__=="__main__":
    raise SystemExit(main())
