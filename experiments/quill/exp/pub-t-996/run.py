#!/usr/bin/env python3
"""Known paragraph controls vs T994 unknown-field negative, public PUB only."""
from __future__ import annotations
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time

HELPER_SHA="87a6733516ad6ffd1b6b97a3176f359bfeb60ca1"
HELPER=Path("reference-t994/experiments/quill/exp/pub-t-994/run.py")
OPTS={
 "60685":{"field":0x13,"type":0x22,"size":4,"expected_count":10},
 "51318":{"field":0x04,"type":0x12,"size":2,"expected_count":4}
}


def diff_bytes(q,pos,raw):
    return [(pos+i,byte) for i,byte in enumerate(raw) if q[pos+i]!=byte]


def load_helper():
    source=Path("reference-t994").resolve()
    sha=subprocess.run(["git","rev-parse","HEAD"],cwd=source,
                       capture_output=True,text=True,check=True).stdout.strip()
    if sha!=HELPER_SHA:raise ValueError("wrong_helper_source_revision")
    t=source/Path("experiments/quill/exp/pub-t-994/run.py")
    spec=importlib.util.spec_from_file_location("prior_t994",t)
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def controls(q, prior, name):
    desc=prior.descriptors(q)
    stsh=prior.one(desc,b"STSH",1)
    rows=prior.paragraph_properties(q,stsh)
    spec=OPTS[name]
    options=[]
    for row in rows:
        for prop,typ,pos,body in row["props"]:
            if (prop,typ,body)==(spec["field"],spec["type"],spec["size"]):
                options.append(pos+2)
    if len(options)!=spec["expected_count"]:
        raise ValueError("known_property_count_mismatch")
    if name=="60685":
        plus=[]
        zeros=[]
        first_plus=[]
        for i,pos in enumerate(options):
            old=prior.u32(q,pos)
            if old>0xffffffff-12700:raise ValueError("known_field_overflow")
            current=struct.pack("<I",old+12700)
            data=diff_bytes(q,pos,current)
            plus.extend(data)
            if i==0:first_plus.extend(data)
            zeros.extend(diff_bytes(q,pos,b"\0\0\0\0"))
        variants={
          "spaceafter_first_plus_1pt":first_plus,
          "spaceafter_all_plus_1pt":plus,
          "spaceafter_all_zero":zeros,
        }
    else:
        if any(q[pos]!=2 or q[pos+1]!=0x5a for pos in options):
            raise ValueError("expected_alignment_5a02_missing")
        variants={
           "alignment_first_low_left":[(options[0],0)],
           "alignment_all_low_left":[(pos,0) for pos in options],
           "alignment_all_high_zero":[(pos+1,0) for pos in options],
        }
    if any(not x for x in variants.values()):
        raise ValueError("known_control_noop")
    # Positive TEXT is reused from T994, no re-measure of 0x30 controls.
    text_arms,_=prior.prepare_mutations(q,prior.SOURCES[name]["natural_high"])
    variants["text_positive"]=text_arms["text_positive"]
    return variants, {"known_property_records":len(options),
                      "paragraph_records":len(rows),"intervention_type":spec["field"]}


def main(outdir):
    prior=load_helper()
    result={"schema":"sk1-quill-exp-pub-t-996.v1","task_id":"PUB-T-996",
            "native_publisher":"NOT_EVALUATED",
            "parent_science_source_commit":HELPER_SHA,
            "poi_commit":prior.PIN,"samples":{}}
    lo=shutil.which("libreoffice") or shutil.which("soffice")
    if not lo:raise ValueError("missing_libreoffice")
    result["libreoffice_version"]=subprocess.run([lo,"--version"],capture_output=True,
                                                 text=True,check=True).stdout.strip()
    with tempfile.TemporaryDirectory(prefix="sk1-t996-") as scratch:
        temporary=Path(scratch)
        for name in ("60685","51318"):
            spec=prior.SOURCES[name]
            row={"git_blob_sha1":spec["blob"],"input_size":spec["size"],
                 "kind": "spaceafter" if name=="60685" else "alignment"}
            result["samples"][name]=row
            try:
                original=prior.get_source(spec)
                row["input_sha256"]=prior.sha(original)
                with prior.olefile.OleFileIO(io.BytesIO(original)) as ole:
                    q=ole.openstream(prior.STREAM).read()
                arms,static=controls(q,prior,name)
                row["physical_controls"]=static
                cases={"baseline_one":(q,0),"baseline_two":(q,0)}
                for case,mods in arms.items():
                    q_mod,n=prior.mutated_quill(q,mods)
                    cases[case]=(q_mod,n)
                row["cases"]={}
                for case,(bytesq,expected) in cases.items():
                    directory=temporary/name/case
                    observed=prior.write_variant(original,bytesq,directory/"input.pub")
                    if expected!=observed:raise ValueError("unexpected_outer_cfb_changes")
                    analysis=prior.import_odg(directory,lo)
                    analysis["input_changed_bytes"]=observed
                    row["cases"][case]=analysis
                neg=temporary/name/"broken_magic"
                neg.mkdir(parents=True)
                corrupt=bytearray(original)
                corrupt[0]^=255
                (neg/"input.pub").write_bytes(corrupt)
                analysis=prior.import_odg(neg,lo)
                analysis["input_changed_bytes"]=1
                row["cases"]["broken_magic"]=analysis
                signatures=lambda x: (x.get("content_sha256"),x.get("styles_sha256"))
                base=row["cases"]["baseline_one"]
                repeat=row["cases"]["baseline_two"]
                good=base["imported"] and repeat["imported"] and signatures(base)==signatures(repeat)
                positive=row["cases"]["text_positive"]
                sensitive=positive["imported"] and good and signatures(positive)!=signatures(base)
                nonempty=base.get("rendered_nonspace_char_count",0)>0
                negok=not analysis["imported"]
                row["baseline_stable"]=good
                row["text_control_detected"]=sensitive
                row["nonempty_import"]=nonempty
                row["broken_magic_rejected"]=negok
                eligible=good and sensitive and nonempty and negok
                row["interpretation_eligible"]=eligible
                keys=[k for k in arms if k!="text_positive"]
                row["known_field_results"]={
                  k:("FAILED_IMPORT" if not row["cases"][k]["imported"]
                     else "DIFFERENT_PROJECTION" if signatures(row["cases"][k])!=signatures(base)
                     else "SAME_PROJECTION")
                  for k in keys
                }
                row["conclusion"] = (
                  "DETECTED_KNOWN_STYLE_CHANGE" if eligible and
                  "DIFFERENT_PROJECTION" in row["known_field_results"].values()
                  else "KNOWN_STYLE_CHANGE_NOT_DETECTED" if eligible
                  else "NON_DISCRIMINATING"
                )
                row["status"]="EXECUTED"
            except Exception as err:
                row["status"]="NOT_EVALUATED"
                safe={
                  "known_property_count_mismatch","known_field_overflow",
                  "expected_alignment_5a02_missing","known_control_noop",
                  "unexpected_outer_cfb_changes","wrong_helper_source_revision"
                }
                row["error_class"]=str(err) if str(err) in safe else type(err).__name__
    output=Path(outdir)
    output.mkdir(parents=True,exist_ok=True)
    (output/"report.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    done=sum(x["status"]=="EXECUTED" for x in result["samples"].values())
    hit=sum(x.get("conclusion")=="DETECTED_KNOWN_STYLE_CHANGE" for x in result["samples"].values())
    print(f"SK1 T996 executed={done}/2; known_property_response_detected={hit}/2; native=NOT_EVALUATED")
    return 0 if done==2 else 2

if __name__=="__main__":
    if len(sys.argv)!=2:raise SystemExit("usage: run.py OUTDIR")
    raise SystemExit(main(sys.argv[1]))
