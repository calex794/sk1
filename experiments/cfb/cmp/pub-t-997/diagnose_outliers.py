#!/usr/bin/env python3
"""Targeted source-ground truth discriminator for PUB-T-997 outliers.

Never exports raw PUB, Quill TEXT, ODG, Reader story text or actual word tokens.
All inputs are the same prior, SHA-pinned public Apache POI fixtures.
"""
from __future__ import annotations
from collections import Counter
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

TARGETS=("SampleNewsletter.pub","Sample98.pub","Sample2000.pub","SampleBrochure.pub")
T994_PIN="87a6733516ad6ffd1b6b97a3176f359bfeb60ca1"

def module_from_path(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def run_cmd(argv,base):
    return subprocess.run(argv,cwd=base,capture_output=True,text=True,check=True).stdout.strip()

def quill_raw_words(data,pri,base):
    with base.olefile.OleFileIO(io.BytesIO(data)) as file:
        if not file.exists(pri.STREAM):
            return {"status":"NO_QUILL"}
        quill=file.openstream(pri.STREAM).read()
    try:
        descriptor=pri.one(pri.descriptors(quill),b"TEXT")
        _,_,off,n=descriptor
        if n==0 or n%2:
            return {"status":"BAD_TEXT_LENGTH"}
        text=quill[off:off+n].decode("utf-16le","replace")
        count=base.vocab([text])
        return {"status":"DECODED_TEXT","text_chunk_byte_len":n,
                "words":count,
                "reader_visible_code_units":sum(len(z.encode("utf-16le","surrogatepass"))//2
                                                for z in [text])}
    except Exception:
        return {"status":"UNSUPPORTED_QUILL_GRAMMAR"}


def per_page_odg(path,base):
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise ValueError("ODG_CRC_BAD")
        doc=ET.fromstring(z.read("content.xml"))
        names=z.namelist()
    drawing=doc.find("./"+base.NS_OFFICE+"body/"+base.NS_OFFICE+"drawing")
    if drawing is None:raise ValueError("NOT_A_DRAWING")
    pages=drawing.findall(base.NS_DRAW+"page")
    page_stats=[]
    paragraph_hashes=Counter()
    allparas=[]
    allwords=Counter()
    for p in pages:
        paras=["".join(elem.itertext()) for elem in p.iter(base.NS_TEXT+"p")]
        textwords=base.vocab(paras)
        shape_types=Counter(elem.tag.split("}",1)[-1] for elem in p.iter()
                            if elem.tag in {base.NS_DRAW+n for n in base.SHAPES})
        nonspace=sum(len("".join(x.split())) for x in paras)
        page_stats.append({
           "token_count":sum(textwords.values()),
           "nonspace_text_characters":nonspace,
           "text_paragraph_count":len(paras),
           "shape_nodes":sum(shape_types.values()),
           "draw_frame_count":shape_types.get("frame",0),
           "draw_custom_shape_count":shape_types.get("custom-shape",0),
           "draw_image_elements":sum(1 for elem in p.iter(base.NS_DRAW+"image")),
           "is_text_and_shape_empty":nonspace==0 and sum(shape_types.values())==0,
        })
        allwords.update(textwords)
        for txt in paras:
            words=base.vocab([txt])
            if not words:continue
            fingerprint=base.digest((" ".join(txt.split())).casefold().encode("utf-8"))
            paragraph_hashes[fingerprint]+=1
        allparas.extend(paras)
    repeated_paras=sum(c-1 for c in paragraph_hashes.values() if c>1)
    pictures=sum(1 for name in names
                 if name.startswith("Pictures/") and not name.endswith("/"))
    return page_stats,allwords,{
        "duplicate_paragraph_text_instances":repeated_paras,
        "unique_nonempty_paragraph_fingerprints":len(paragraph_hashes),
        "odg_pictures_media_files":pictures,
        "lo_draw_page_count":len(pages),
    }


def token_comparison(sourcewords,readerwords,lowords):
    a=sum(sourcewords.values())
    b=sum(readerwords.values())
    c=sum(lowords.values())
    return {
      "physical_quill_tokens":a,
      "reader_story_tokens":b,
      "lo_visible_tokens":c,
      "quill_reader_shared":sum((sourcewords&readerwords).values()),
      "quill_lo_shared":sum((sourcewords&lowords).values()),
      "reader_lo_shared":sum((readerwords&lowords).values()),
      "reader_extra_vs_quill":sum((readerwords-sourcewords).values()),
      "reader_missing_vs_quill":sum((sourcewords-readerwords).values()),
      "lo_extra_vs_quill":sum((lowords-sourcewords).values()),
      "lo_missing_vs_quill":sum((sourcewords-lowords).values()),
      "quill_unique_word_kinds":len(sourcewords),
      "reader_unique_word_kinds":len(readerwords),
      "lo_unique_word_kinds":len(lowords),
      "lo_unique_kinds_not_in_quill":len(set(lowords)-set(sourcewords)),
      "reader_unique_kinds_not_in_quill":len(set(readerwords)-set(sourcewords)),
    }


def main(args):
    if len(args)!=5:
        raise SystemExit("usage: diagnose_outliers.py RAR2_DIR TARGET_BIN_DIR T994_DIR REPORT_JSON OUT_JSON")
    srcroot,binroot,oldroot,inreport,destination=map(lambda s:Path(s).resolve(),args)
    base=module_from_path("t997_base",Path(__file__).parent/"run.py")
    report=json.loads(inreport.read_text())
    if report["schema"]!="sk1-pub-cmp-t997/v1":raise ValueError("PARENT_REPORT_SCHEMA")
    if report["rar2_source_commit"]!=base.RAR_PIN:raise ValueError("PARENT_SOURCE_DRIFT")
    if run_cmd(["git","rev-parse","HEAD"],oldroot)!=T994_PIN:
        raise ValueError("T994_PIN_DRIFT")
    prior=module_from_path("pinned_t994",oldroot/"experiments/quill/exp/pub-t-994/run.py")
    base.verified_sources(srcroot)
    manifest=json.loads((srcroot/"tools/reader_corpus_manifest_v1.json").read_text())
    m={f["name"]:f for f in manifest["fixtures"]}
    earlier={r["fixture"]:r for r in report["rows"]}
    lo=base.shutil.which("libreoffice") or base.shutil.which("soffice")
    binex=binroot/"sk1-compare-reader-text"
    if not lo or not binex.is_file():raise ValueError("RUNTIMES_MISSING")
    out={"schema":"sk1-pub-cmp-t997-outliers/v1",
         "task_id":"PUB-T-997","rar2_source_commit":base.RAR_PIN,
         "poi_commit":manifest["upstream"]["commit"],
         "parent_scientific_receipt":"source-safe-t997/report.json",
         "libreoffice_version":report["libreoffice_version"],
         "native_publisher_evaluated":False,
         "physical_source_is_not_native_oracle":True,
         "rows":{}}
    with tempfile.TemporaryDirectory(prefix="sk1-t997-outliers-") as scratch:
        root=Path(scratch)
        for name in TARGETS:
            e=m[name]
            old=earlier[name]
            if not old["semantic"] or old["comparison"]!="BOTH_OPEN":
                raise ValueError("TARGET_NO_SUCCESSFUL_PARENT")
            data=base.fetch(e,manifest["upstream"]["base_url"])
            case=root/name
            case.mkdir()
            path=case/name
            path.write_bytes(data)
            raw=quill_raw_words(data,prior,base)
            localreader=case/"reader-private.json"
            rc,to=base.safe_run([str(binex),str(path),str(localreader)],90)
            if to or rc!=0 or not localreader.is_file():
                raise ValueError("ACTUAL_READER_PROBE_FAILED")
            parsed=json.loads(localreader.read_text())
            if not parsed.get("opened"):raise ValueError("READER_NOT_OPEN")
            reader_words=base.vocab(parsed["stories"])
            lo_dir=case/"lo"
            imported,runner_lo_words=base.libreoffice_once(path,lo_dir,lo)
            if imported.get("status")!="EXECUTED" or not imported["opened"]:
                raise ValueError("LO_NOT_OPEN")
            pages,lwords,stats=per_page_odg(lo_dir/"out"/(path.stem+".odg"),base)
            if lwords!=runner_lo_words:raise ValueError("LO_WORD_EXTRACTION_MISMATCH")
            if sum(lwords.values())!=old["text_overlap"]["libreoffice_tokens"]:
                raise ValueError("PARENT_LO_TOKEN_DRIFT")
            if sum(reader_words.values())!=old["text_overlap"]["reader_tokens"]:
                raise ValueError("PARENT_READER_TOKEN_DRIFT")
            if len(pages)!=old["libreoffice"]["draw_page_count"]:
                raise ValueError("PARENT_PAGE_COUNT_DRIFT")
            result={"input_sha256":e["sha256"],"source_byte_len":e["byte_len"],
                    "source_physical_version":old["source_physical_version"],
                    "lo_page_statistics":pages,
                    "odg_content_hash_same_as_parent":(
                        imported.get("content_xml_sha256")==old["libreoffice"]["content_xml_sha256"]),
                    "odg_styles_hash_same_as_parent":(
                        imported.get("styles_xml_sha256")==old["libreoffice"]["styles_xml_sha256"]),
                    "lo_nonspace_duplicate_analysis":stats,
                    "quill_parse_status":raw["status"],
                    "source_unchanged":base.digest(path.read_bytes())==e["sha256"]}
            if raw["status"]=="DECODED_TEXT":
                result["quill_text_chunk_byte_len"]=raw["text_chunk_byte_len"]
                result["raw_vs_engines"]=token_comparison(raw["words"],reader_words,lwords)
            out["rows"][name]=result
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(out,sort_keys=True,indent=2)+"\n")
    print("PUB-T-997 targeted physical source outliers:",
          {name:(r["quill_parse_status"],
                 [p["token_count"] for p in r["lo_page_statistics"]])
           for name,r in out["rows"].items()})
    return 0 if all(x["source_unchanged"] and x["odg_content_hash_same_as_parent"]
                    and x["odg_styles_hash_same_as_parent"]
                    and x["quill_parse_status"]=="DECODED_TEXT"
                    for x in out["rows"].values()) else 2

if __name__=="__main__":
    raise SystemExit(main(sys.argv[1:]))
