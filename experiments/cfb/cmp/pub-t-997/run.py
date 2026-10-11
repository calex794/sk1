#!/usr/bin/env python3
"""PUB-T-997: same-source Reader vs LibreOffice public corpus comparison.

Only source-free aggregate/result JSON may leave this process. Raw PUB, ODG,
and the temporary Rust Reader story-text probe are deleted on exit.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
from urllib.parse import quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile

import olefile

RAR_PIN="b224a614af48c273b2d4bc0881793cf0217cc16d"
MANIFEST_GIT_BLOB="4e77d912e7a104cc192be5e6504892c295c1db01"
RECEIPT_GIT_BLOB="d57ea6b07e62751b65790238b1a374275dbb2199"
EXPECTED_SOURCE_COUNT=22
ADVERSARIAL="clusterfuzz-testcase-minimized-POIHPBFFuzzer-4701121678278656.pub"
REPEAT=("Simple.pub","Sample98.pub")
NS_DRAW="{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
NS_TEXT="{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
NS_TABLE="{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
NS_OFFICE="{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
SHAPES=("frame","rect","ellipse","custom-shape","line","polyline","polygon",
        "path","connector","g","measure","caption")


def digest(b):return hashlib.sha256(b).hexdigest()


def git(args,root):
    return subprocess.run(["git",*args],cwd=root,capture_output=True,text=True,
                          timeout=30,check=True).stdout.strip()


def verified_sources(root):
    if git(["rev-parse","HEAD"],root)!=RAR_PIN:raise ValueError("RAR_PIN_MISMATCH")
    for filename,blob in [
      ("tools/reader_corpus_manifest_v1.json",MANIFEST_GIT_BLOB),
      ("vendor/producer-a/crates/pub-viewer/src/bin/corpus-reader-receipt.rs",RECEIPT_GIT_BLOB),
    ]:
        if git(["hash-object",filename],root)!=blob:raise ValueError("RAR_BLOB_MISMATCH")
    manifest=json.loads((root/"tools/reader_corpus_manifest_v1.json").read_text())
    if manifest.get("schema_version")!="chaptera.reader-corpus-manifest.v1":
        raise ValueError("MANIFEST_SCHEMA_UNSUPPORTED")
    allrows=manifest.get("fixtures",[])
    if len(allrows)!=EXPECTED_SOURCE_COUNT:raise ValueError("MANIFEST_COUNT_MISMATCH")
    if len({x["name"] for x in allrows})!=EXPECTED_SOURCE_COUNT:
        raise ValueError("MANIFEST_DUPLICATES")
    assert manifest["upstream"]["repository"]=="apache/poi"
    assert manifest["upstream"]["commit"]=="942d95d85b15d0dfdb3bc9ba1b4f273f277757c8"
    assert sum(not x["semantic"] for x in allrows)==1
    assert next(x for x in allrows if not x["semantic"])["name"]==ADVERSARIAL
    return manifest


def fetch(entry,base):
    uri=base.rstrip("/")+"/"+quote(entry["name"],safe="")
    data=None
    for i in range(3):
        try:
            with urlopen(Request(uri,headers={"User-Agent":"SK1-PUB-T-997"}),timeout=45) as stream:
                data=stream.read(6_000_000)
            break
        except Exception:
            if i==2:raise ValueError("CORPUS_NETWORK_UNAVAILABLE")
            time.sleep(2)
    if len(data)!=entry["byte_len"] or digest(data)!=entry["sha256"]:
        raise ValueError("CORPUS_IDENTITY_DRIFT")
    return data


def source_family(raw):
    try:
        with olefile.OleFileIO(io.BytesIO(raw)) as cfb:
            if not cfb.exists("Contents"):return "cfb_without_contents"
            magic=cfb.openstream("Contents").read(4)
        return {b"\xe8\xac\x22\x00":"0x22",b"\xe8\xac\x2c\x00":"0x2c"}.get(
            magic, "unknown_contents_magic")
    except Exception:
        return "unsupported_cfb"


def safe_run(argv,timeout):
    try:
        proc=subprocess.run(argv,stdin=subprocess.DEVNULL,
                            capture_output=True,timeout=timeout,check=False)
        return proc.returncode,False
    except subprocess.TimeoutExpired:
        return None,True


def vocab(texts):
    tokens=Counter()
    for txt in texts:
        normalized=unicodedata.normalize("NFKC",txt).casefold()
        tokens.update(re.findall(r"(?u)\b[^\W_]{2,}\b",normalized))
    return tokens


def summarize_tokens(rwords,lwords):
    intersection=sum((rwords&lwords).values())
    return {
        "reader_tokens":sum(rwords.values()),
        "libreoffice_tokens":sum(lwords.values()),
        "shared_tokens_min_count":intersection,
        "reader_token_recall_in_lo":round(
            intersection/sum(rwords.values()),4) if rwords else None,
        "lo_token_recall_in_reader":round(
            intersection/sum(lwords.values()),4) if lwords else None,
    }


def reader_once(src,case_dir,receipt_exe,probe_exe):
    case_dir.mkdir(parents=True,exist_ok=True)
    normal=case_dir/"structural.json"
    private=case_dir/"private_story.json"
    rc,to=safe_run([str(receipt_exe),str(src),str(normal)],120)
    if to:return {"status":"TIMEOUT"},Counter()
    if rc!=0 or not normal.is_file():return {"status":"EXECUTION_FAILED"},Counter()
    rc2,to2=safe_run([str(probe_exe),str(src),str(private)],120)
    if to2:return {"status":"TEXT_PROBE_TIMEOUT"},Counter()
    if rc2!=0 or not private.is_file():return {"status":"TEXT_PROBE_FAILED"},Counter()
    try:
        stable=json.loads(normal.read_text())
        extra=json.loads(private.read_text())
    except Exception:
        return {"status":"INVALID_JSON"},Counter()
    if stable.get("schema")!="chaptera.reader-corpus-structural-receipt.v1":
        return {"status":"SCHEMA_MISMATCH"},Counter()
    source_sha=digest(src.read_bytes())
    if stable.get("source_sha256")!=source_sha or stable.get("byte_len")!=src.stat().st_size:
        return {"status":"RECEIPT_SOURCE_MISMATCH"},Counter()
    if stable.get("opened")!=extra.get("opened"):
        return {"status":"PROBE_OPEN_DISAGREEMENT"},Counter()
    opened=stable["opened"]
    output={
      "status":"EXECUTED","opened":opened,
      "structural_receipt_sha256":digest(normal.read_bytes()),
    }
    if not opened:
        output["error_signature_sha256"]=stable.get("open_error_signature_sha256")
        output["classification"]="UNSUPPORTED_OR_OPEN_FAILED"
        return output,Counter()
    for key in ["viewer_page_count","scene_surface_count","scene_node_count",
                "story_count","story_frame_count","text_fragment_count",
                "typography_run_count","inherited_typography_run_count",
                "image_resource_count","image_placement_count","paint_node_count"]:
        if type(stable.get(key)) is not int or stable[key]<0:
            return {"status":"INVALID_STRUCTURAL_COUNTS"},Counter()
        output[key]=stable[key]
    pairs={
        "viewer_page_count":"pages","story_count":"stories",
        "story_frame_count":"story_frame_count",
        "text_fragment_count":"text_fragment_count",
        "typography_run_count":"typography_runs",
        "image_resource_count":"image_resources",
        "image_placement_count":"image_placements",
        "scene_node_count":"shape_scene_nodes",
        "paint_node_count":"paints",
    }
    for stable_key,extra_key in pairs.items():
        v=extra.get(extra_key)
        count=len(v) if extra_key=="stories" and isinstance(v,list) else v
        if output[stable_key]!=count:
            return {"status":"STRUCTURAL_PROBE_COUNT_MISMATCH"},Counter()
    output["format_version"]=stable.get("format_version")
    output["fidelity_status"]=stable.get("fidelity_status")
    output["paragraph_alignment_runs"]=extra.get("paragraph_alignment_runs")
    output["paragraph_line_spacing_runs"]=extra.get("paragraph_line_spacing_runs")
    output["paragraph_flow_runs"]=extra.get("paragraph_flow_runs")
    output["table_count"]=extra.get("tables")
    output["diagnostic_codes"]=stable.get("diagnostic_codes",[])
    if not isinstance(extra["stories"],list) or not all(isinstance(x,str) for x in extra["stories"]):
        return {"status":"BAD_PROBE_STORIES"},Counter()
    tokens=vocab(extra["stories"])
    output["story_unicode_characters"]=sum(len(x) for x in extra["stories"])
    output["story_nonspace_characters"]=sum(len("".join(x.split())) for x in extra["stories"])
    return output,tokens


def libreoffice_once(src,case_dir,lo):
    case_dir.mkdir(parents=True,exist_ok=True)
    output=case_dir/"out"
    output.mkdir()
    profile=case_dir/"lo-profile"
    argv=[lo,"-env:UserInstallation="+profile.absolute().as_uri(),
          "--headless","--convert-to","odg","--outdir",str(output),str(src)]
    rc,to=safe_run(argv,110)
    if to:return {"status":"TIMEOUT"},Counter()
    odg=output/(src.stem+".odg")
    if not odg.is_file():
        return {"status":"EXECUTED","opened":False,"converter_exit_code":rc},Counter()
    try:
        with zipfile.ZipFile(odg) as z:
            if z.testzip() is not None:raise ValueError("ZIP_CRC")
            cbytes=z.read("content.xml")
            sbytes=z.read("styles.xml")
            ct=ET.fromstring(cbytes)
            ET.fromstring(sbytes)
    except Exception:
        return {"status":"INVALID_ODG"},Counter()
    drawing=ct.find("./"+NS_OFFICE+"body/"+NS_OFFICE+"drawing")
    if drawing is None:
        return {"status":"MISSING_ODF_DRAWING"},Counter()
    pages=list(drawing.findall(NS_DRAW+"page"))
    shapes=sum(1 for p in pages for x in p.iter()
               if x.tag in {NS_DRAW+n for n in SHAPES})
    paras=[elem for p in pages for elem in p.iter(NS_TEXT+"p")]
    page_texts=["".join(el.itertext()) for el in paras]
    tokens=vocab(page_texts)
    imagery=sum(1 for p in pages for x in p.iter(NS_DRAW+"image"))
    embedded_tables=sum(1 for p in pages for x in p.iter(NS_TABLE+"table"))
    result={
      "status":"EXECUTED","opened":True,"converter_exit_code":rc,
      "content_xml_sha256":digest(cbytes),"styles_xml_sha256":digest(sbytes),
      "draw_page_count":len(pages),"draw_shape_nodes":shapes,
      "draw_image_elements":imagery,"embedded_table_nodes":embedded_tables,
      "text_paragraph_count":len(paras),
      "nonspace_text_characters":sum(len("".join(x.split())) for x in page_texts),
      "text_word_count":sum(tokens.values()),
    }
    return result,tokens


def classify(r,l):
    if r["status"]!="EXECUTED" or l["status"]!="EXECUTED":
        return "NOT_EVALUATED"
    if r["opened"] and l["opened"]:return "BOTH_OPEN"
    if r["opened"] and not l["opened"]:return "READER_ONLY"
    if not r["opened"] and l["opened"]:return "LIBREOFFICE_ONLY"
    return "NEITHER_OPEN"


def safe_for_report(report):
    forbidden=("private_story","source_bytes","output_file","story_text")
    s=json.dumps(report,ensure_ascii=False).lower()
    if any(k in s for k in forbidden):raise ValueError("UNSAFE_REPORT_KEY")
    return report


def main():
    if len(sys.argv)!=4:
        raise SystemExit("usage: run.py RAR2_SOURCE_DIR OUT_DIR EXECUTABLE_DIR")
    source=Path(sys.argv[1]).resolve()
    out=Path(sys.argv[2]).resolve()
    bin_dir=Path(sys.argv[3]).resolve()
    out.mkdir(parents=True,exist_ok=True)
    manifest=verified_sources(source)
    lo=shutil.which("libreoffice") or shutil.which("soffice")
    if not lo:raise ValueError("LO_NOT_INSTALLED")
    ver=subprocess.run([lo,"--version"],capture_output=True,text=True,check=True).stdout.strip()
    official=bin_dir/"corpus-reader-receipt"
    probe=bin_dir/"sk1-compare-reader-text"
    if not official.is_file() or not probe.is_file():raise ValueError("READER_BINARIES_MISSING")
    report={
      "schema":"sk1-pub-cmp-t997/v1",
      "task_id":"PUB-T-997",
      "rar2_source_commit":RAR_PIN,
      "rar2_corpus_manifest_git_blob":MANIFEST_GIT_BLOB,
      "official_viewer_receipt_git_blob":RECEIPT_GIT_BLOB,
      "poi_source_commit":manifest["upstream"]["commit"],
      "libreoffice_version":ver,
      "rust_probe":"ephemeral_real_pub_viewer_open_pub_geometry",
      "comparison_scope":"same_pub_bytes_open_pages_text_tokens_and_descriptive_counts",
      "visual_fidelity_proven":False,
      "publisher_native_evaluated":False,
      "data_provenance":"public_apache_poi_existing_22_fixture_corpus",
      "rows":[],
    }
    with tempfile.TemporaryDirectory(prefix="sk1-pub-t997-") as dirstr:
        temp=Path(dirstr)
        for entry in manifest["fixtures"]:
            name=entry["name"]
            case=temp/name
            case.mkdir()
            row={"fixture":name,"semantic":entry["semantic"],
                 "manifest_family":entry["family"],
                 "source_sha256":entry["sha256"],
                 "source_byte_len":entry["byte_len"]}
            report["rows"].append(row)
            try:
                data=fetch(entry,manifest["upstream"]["base_url"])
                src=case/name
                src.write_bytes(data)
                row["source_physical_version"]=source_family(data)
                r,rt=reader_once(src,case/"reader_one",official,probe)
                l,lt=libreoffice_once(src,case/"lo_one",lo)
                row["reader"]=r
                row["libreoffice"]=l
                row["comparison"]=classify(r,l)
                row["source_unchanged"]=digest(src.read_bytes())==entry["sha256"]
                if row["comparison"]=="BOTH_OPEN":
                    row["text_overlap"]=summarize_tokens(rt,lt)
                    row["page_count_equal_when_both_open"]=(r["viewer_page_count"]==l["draw_page_count"])
                if name in REPEAT:
                    rr,rrt=reader_once(src,case/"reader_repeat",official,probe)
                    ll,llt=libreoffice_once(src,case/"lo_repeat",lo)
                    row["repeat"]={
                      "reader_status_stable":r["status"]==rr["status"] and r["opened"]==rr["opened"],
                      "reader_structure_stable":(
                        r.get("structural_receipt_sha256")==rr.get("structural_receipt_sha256")
                        and rt==rrt
                      ),
                      "lo_status_stable":l["status"]==ll["status"] and l["opened"]==ll["opened"],
                      "lo_xml_stable":(
                        l.get("content_xml_sha256")==ll.get("content_xml_sha256")
                        and l.get("styles_xml_sha256")==ll.get("styles_xml_sha256")
                        and lt==llt),
                    }
            except Exception as ex:
                row["comparison"]="NOT_EVALUATED"
                row["failure_class"]=str(ex) if str(ex) in {
                    "CORPUS_IDENTITY_DRIFT","CORPUS_NETWORK_UNAVAILABLE",
                    "RAR_PIN_MISMATCH","RAR_BLOB_MISMATCH",
                    "MANIFEST_SCHEMA_UNSUPPORTED","MANIFEST_COUNT_MISMATCH",
                    "MANIFEST_DUPLICATES"
                } else type(ex).__name__

        # Malformed CFB test. Separate from the 22 original source specimens.
        valid=next(x for x in report["rows"] if x["fixture"]=="Sample.pub")
        sourcebytes=fetch(next(x for x in manifest["fixtures"] if x["name"]=="Sample.pub"),
                          manifest["upstream"]["base_url"])
        broken=temp/"negative"
        broken.mkdir()
        bb=bytearray(sourcebytes)
        bb[0]^=0xFF
        fixture=broken/"negative.pub"
        fixture.write_bytes(bb)
        nr,_=reader_once(fixture,broken/"reader",official,probe)
        nl,_=libreoffice_once(fixture,broken/"lo",lo)
        report["negative_control"]={
            "changed_physical_bytes":1,
            "reader_rejected":nr["status"]=="EXECUTED" and nr["opened"] is False,
            "libreoffice_rejected":nl["status"]=="EXECUTED" and nl["opened"] is False,
            "not_a_semantic_fixture":True,
        }
    semantic=[row for row in report["rows"] if row["semantic"]]
    classes=Counter(row.get("comparison","NOT_EVALUATED") for row in semantic)
    groups=defaultdict(lambda:Counter())
    for row in semantic:
        groups[row.get("source_physical_version","unavailable")][row.get("comparison","NOT_EVALUATED")]+=1
    reader_open=sum(row.get("reader",{}).get("opened") is True for row in semantic)
    lo_open=sum(row.get("libreoffice",{}).get("opened") is True for row in semantic)
    both=[row for row in semantic if row.get("comparison")=="BOTH_OPEN"]
    mismatches=[row for row in both if not row.get("page_count_equal_when_both_open")]
    report["summary"]={
      "all_public_source_fixtures":len(report["rows"]),
      "semantic_fixture_count":len(semantic),
      "adversarial_fixture_count":len(report["rows"])-len(semantic),
      "reader_semantic_opened":reader_open,
      "lo_semantic_opened":lo_open,
      "both_semantic_opened":classes["BOTH_OPEN"],
      "reader_only_semantic":classes["READER_ONLY"],
      "lo_only_semantic":classes["LIBREOFFICE_ONLY"],
      "neither_semantic":classes["NEITHER_OPEN"],
      "not_evaluated_semantic":classes["NOT_EVALUATED"],
      "both_open_page_count_equal":len(both)-len(mismatches),
      "both_open_page_count_different":len(mismatches),
      "both_open_with_nonzero_token_intersection":sum(
          x.get("text_overlap",{}).get("shared_tokens_min_count",0)>0 for x in both),
      "by_physical_family":{key:dict(value) for key,value in sorted(groups.items())},
      "sampled_repeat_count":sum("repeat" in row for row in report["rows"]),
      "source_immutability_count":sum(row.get("source_unchanged",False) for row in report["rows"]),
    }
    safe_for_report(report)
    (out/"report.json").write_text(json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True)+"\n")
    print("PUB-T-997 original semantic sources 21; Reader-open=",reader_open,
          "LO-open=",lo_open,"both=",classes["BOTH_OPEN"],
          "LO-only=",classes["LIBREOFFICE_ONLY"],
          "Reader-only=",classes["READER_ONLY"],
          "not-evaluated=",classes["NOT_EVALUATED"],sep="")
    bad=sum(row.get("comparison")=="NOT_EVALUATED" for row in report["rows"])
    bad+=sum(not row.get("source_unchanged",False) for row in report["rows"])
    if not all(report["negative_control"][k] for k in ("reader_rejected","libreoffice_rejected")):bad+=1
    for row in report["rows"]:
        if "repeat" in row and not all(row["repeat"].values()):bad+=1
    return 0 if bad==0 else 2

if __name__=="__main__":
    raise SystemExit(main())
