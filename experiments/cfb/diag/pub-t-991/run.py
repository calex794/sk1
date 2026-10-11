#!/usr/bin/env python3
"""PUB-T-991: exact bounded 21 POI + 5 Aspose + 1 sample .pub originals.

No source bytes, filenames, Story text or URLs are serialized. A real Writer
inverse is attempted only on never-modified source PUB with original FE/FF
and SHA disjoint from the previously inspected 625 samples.
"""
from __future__ import annotations
from collections import Counter
import argparse,hashlib,importlib.util,json,subprocess,tempfile
from pathlib import Path

POI_PIN="c85c6918858ea279de2c33df70518c105064df41"
POI_TREE="10300af0b12b49578dfda1b704aef0a84a663914"
ASPOSE_PIN="beee619f9a4b7e2c8908e0fa132f4f4650b08975"
FILE_FORMAT_PIN="bdc8e1d219af7d42aa1ebb30c902f0c4a12763f4"
LALAMU_PIN="87094c23e2a9eaa2aa9e95d72ec52f72ef109f11"
LALAMU_TREE="8146fa9fdd2f577ebe02bc7205a61bb14e20d3e7"
RAR2_PIN="703808408fd919e564a90cdc236e81db3c04af8b"
T987_PIN="fa714fe958999325649430dad53c10edac42246a"
T984_PIN="14ac75ae0346b3bdbeeada110e1f463dda6cbb27"
T963_PIN="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
T971_PIN="cd38c8d6a545737f9f99821076340505db5e149c"
POI_NAMES=(
"51318.pub","60685.pub","LinkAt0And10.pub","LinkAt10.pub",
"LinkAt10And20And30.pub","LinkAt10And20And30And40.pub",
"LinkAt10Longer.pub","LinkAt20.pub","Sample.pub","Sample2.pub",
"Sample2000.pub","Sample2_2010.pub","Sample3.pub","Sample3_2010.pub",
"Sample4.pub","Sample4_2010.pub","Sample98.pub","SampleBrochure.pub",
"SampleNewsletter.pub","Sample_2010.pub","Simple.pub"
)
ASPOSE_NAMES=(
"christmas.pub","computer-classes-flyer.pub","easter-egg-hunt-flyer.pub",
"florist-flyer.pub","halloween-flyer.pub"
)
SOURCE_CATEGORY_ORDER={"apache_poi":0,"aspose_dotnet":1,"file_format":2}
SCAN_SCHEMA="sk1.cfb-diag-pub-t-991.census.v1"
SHA_RE="0123456789abcdef"
SCANNER="sk1_pub_t_991_external_census"
WRITER="sk1_pub_t_984_inverse_cfb"

def git(cwd,*args):
    return subprocess.check_output(["git",*args],cwd=cwd,text=True).strip()
def sha(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def get_module(path,name):
    sp=importlib.util.spec_from_file_location(name,path)
    assert sp and sp.loader
    m=importlib.util.module_from_spec(sp)
    sp.loader.exec_module(m)
    return m
def check_repo(root,pin):
    assert git(root,"rev-parse","HEAD")==pin, "immutable source commit mismatch"
def source_paths(poi:Path,aspose:Path,filefmt:Path):
    base_poi=poi/"test-data/publisher"
    base_aspose=aspose/"Examples/Data"
    base_mm=filefmt/"fixtures/document"
    assert {p.name for p in base_poi.iterdir() if p.suffix==".pub" and
            not p.name.startswith("clusterfuzz-testcase-")}==set(POI_NAMES)
    assert {p.name for p in base_aspose.iterdir() if p.suffix==".pub"}==set(ASPOSE_NAMES)
    assert (base_mm/"sample.pub").stat().st_size==12288
    return ([("apache_poi",poi,"test-data/publisher/"+name)
             for name in POI_NAMES]+
            [("aspose_dotnet",aspose,"Examples/Data/"+name)
             for name in ASPOSE_NAMES]+
            [("file_format",filefmt,"fixtures/document/sample.pub")])
def read_poi_manifest(rar2:Path):
    m=json.loads((rar2/"tools/reader_corpus_manifest_v1.json").read_text())
    rows={r["name"]:r for r in m["fixtures"]}
    assert len(POI_NAMES)==21 and all(x in rows for x in POI_NAMES)
    return rows

def summarize(records):
    cats=Counter();status=Counter();counts=Counter()
    fields=Counter();seen=set();unique_parsed=set();unique_fe=set()
    match=finals=0;failure=[];writer_state=Counter();distinct_inverse=set()
    for row in records:
        cats[row["category"]]+=1
        status[row["census"]["status"]]+=1
        counts["previously_in_625"]+=int(row["overlap_625"])
        counts["previously_in_rar_1556"]+=int(row["overlap_rar_1556"])
        counts["sha_duplicates_within_27"]+=int(row["duplicate_within_batch"])
        counts["poi_sha_manifest_valid"]+=int(row["poi_manifest_verified"] is True)
        fresh=not row["overlap_625"] and not row["duplicate_within_batch"]
        counts["outside_625_unique_sha"]+=int(fresh)
        c=row["census"]
        if c["status"]!="NATURAL_SYID_PARSED":
            continue
        fields["parsed_corpus_rows"]+=1
        if fresh:
            unique_parsed.add(row["source_sha256"])
            fields["outside_625_natural_parseable"]+=1
        if c["is_fe_ff_boundary"]:
            fields["natural_fe_ff_source_rows"]+=1
            if fresh:
                unique_fe.add(row["source_sha256"])
                fields["outside_625_natural_fe_ff"]+=1
                w=row["writer"]
                assert isinstance(w,dict)
                writer_state[w["status"]]+=1
                p=w["probe"]
                if p is None:continue
                for st in p["stories"]:
                    for pair in st["pairs"]:
                        if not pair["both_single_pass"]:
                            counts["initial_pair_blocked"]+=1
                            continue
                        counts["initial_pair_both_pass"]+=1
                        for arm,key in (("insert_then_delete","insert_delete"),
                                        ("delete_then_insert","delete_insert")):
                            step=pair[arm]
                            counts["inverse_"+step["status"]]+=1
                            if step["status"]!="HOSTED_PASS":continue
                            finals+=1
                            distinct_inverse.add(row["source_sha256"])
                            raw=pair[key+"_raw"];cfb=pair[key+"_cfb"]
                            hd=c["syid_header"];new=hd+2 if hd<=0xfffffffd else None
                            n=sum(a!=b for a,b in zip(
                                hd.to_bytes(4,"little"),new.to_bytes(4,"little"))) if new is not None else None
                            ok=(new is not None and
                               raw["equal_length"] is True and raw["extra_bytes"]==0 and
                               raw["changed_same_offset_bytes"]==n and
                               cfb["source_syid_first_dword"]==hd and
                               cfb["final_syid_first_dword"]==new and
                               cfb["syid_first_dword_delta"]==2 and
                               cfb["syid_first_dword_changed_bytes"]==n and
                               cfb["quill_differing_byte_positions_equal_len"]==n and
                               cfb["quill_changed_bytes_outside_syid_first_dword"]==0 and
                               cfb["same_quill_TEXT_payload_bytes"] is True and
                               cfb["same_quill_story_syid_sequence"] is True and
                               cfb["matched_descriptor_sequence"] is True and
                               cfb["non_quill_streams_changed"]==0 and
                               cfb["missing_cfb_paths"]==0 and
                               cfb["added_cfb_paths"]==0 and
                               cfb["cfb_entry_type_changes"]==0)
                            if ok:match+=1
                            else:failure.append({"sha256":row["source_sha256"],
                                  "story_ordinal":st["story_ordinal"],"arm":arm,
                                  "actual_raw_changes":raw["changed_same_offset_bytes"],
                                  "expected_raw_changes":n})
    return {
        "source_paths":len(records),
        "source_categories":dict(sorted(cats.items())),
        "quill_syid_parser_status":dict(sorted(status.items())),
        "overlap_census":dict(sorted(counts.items())),
        "original_source_syid_population":dict(sorted(fields.items())),
        "distinct_non625_original_syid_parsed":len(unique_parsed),
        "distinct_non625_original_low_FE_FF":len(unique_fe),
        "writer_status_on_original_outside_625_FE_FF":dict(sorted(writer_state.items())),
        "writer_inverse_materialized_final_files":finals,
        "writer_inverse_distinct_original_sha":len(distinct_inverse),
        "writer_inverse_exact_only_syid_plus_2":match,
        "writer_inverse_physical_counterexamples":failure,
        "native_publisher_saveas":"NOT_EVALUATED",
        "source_bytes_artifact_exported":False
    }

def main()->int:
    ap=argparse.ArgumentParser()
    for v in ("poi","aspose","file_format","lalamu","rar2","reference_987"):
        ap.add_argument("--"+v.replace("_","-"),required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    opts=ap.parse_args()
    poi=opts.poi.resolve(strict=True);asp=opts.aspose.resolve(strict=True)
    ff=opts.file_format.resolve(strict=True);la=opts.lalamu.resolve(strict=True)
    rar2=opts.rar2.resolve(strict=True);r987=opts.reference_987.resolve(strict=True)
    out=opts.output.resolve();out.mkdir(parents=True,exist_ok=True)
    for root,pin in [(poi,POI_PIN),(asp,ASPOSE_PIN),(ff,FILE_FORMAT_PIN),
                     (la,LALAMU_PIN),(rar2,RAR2_PIN),(r987,T987_PIN)]:
        check_repo(root,pin)
    assert git(poi,"rev-parse","HEAD:test-data/publisher")==POI_TREE
    assert git(la,"rev-parse","HEAD:pub-corpus/corpus/native/unclassified")==LALAMU_TREE
    old=la/"pub-corpus/corpus/native/unclassified"
    prior_names={x.stem for x in old.iterdir() if x.is_file() and x.suffix==".pub"}
    assert len(prior_names)==625 and all(len(s)==64 and set(s)<=set(SHA_RE) for s in prior_names)
    rar_sha={
      v for v in (rar2/"tools/corpus/receipts/current-rar-1556.sha256.txt").read_text().split()
      if len(v)==64 and set(v)<=set(SHA_RE)
    }
    assert len(rar_sha)==1556
    manifest=read_poi_manifest(rar2)
    spec=source_paths(poi,asp,ff);assert len(spec)==27
    binary_dir=rar2/"tools/native-pub-candidate-cli/target/release/examples"
    scanner=binary_dir/SCANNER;writer=binary_dir/WRITER
    if not scanner.is_file() or not writer.is_file():
        ap.error("strict frozen original Quill census and Writer binaries missing")
    inherited=get_module(r987/"experiments/cfb/diag/pub-t-987/run.py","original_t987_writer_probe")
    records=[];seen=set()
    with tempfile.TemporaryDirectory(prefix="sk1-pub-t991-original-source-bytes-") as td:
        stage=Path(td)/"sha-pub";stage.mkdir()
        for kind,root,relative in spec:
            source=root/relative
            raw=source.read_bytes()
            src_sha=sha(raw)
            assert len(raw)>=8
            git_blob=git(root,"rev-parse","HEAD:"+relative)
            assert git(root,"hash-object",str(source))==git_blob
            if kind=="apache_poi":
                row=manifest[source.name]
                assert src_sha==row["sha256"] and len(raw)==row["byte_len"],"canonical POI fixture SHA/size drift"
                manifest_verified=True
            else:manifest_verified=None
            dup=src_sha in seen
            if not dup:
                target=stage/(src_sha+".pub")
                target.write_bytes(raw)
            seen.add(src_sha)
            records.append({
               "category":kind,"source_sha256":src_sha,
               "source_bytes":len(raw),"source_git_blob_sha1":git_blob,
               "poi_manifest_verified":manifest_verified,
               "duplicate_within_batch":dup,
               "overlap_625":src_sha in prior_names,
               "overlap_rar_1556":src_sha in rar_sha,
               "census":None,"writer":None
            })
        # The original T987 Rust parser scans all exact-source SHA copies once;
        # only cardinality/source-safe schema changed in ephemeral generated source.
        safe=Path(td)/"census.json"
        cmd=subprocess.run([str(scanner),str(stage),str(safe)],
             check=False,capture_output=True,timeout=500)
        if cmd.returncode or not safe.is_file():
            raise RuntimeError("frozen T987 Quill first-DWORD census did not complete")
        c=json.loads(safe.read_text())
        assert set(c)=={"schema","planned_pub","source_immutable_sha_verified","rows"}
        assert c["schema"]==SCAN_SCHEMA
        assert c["planned_pub"]==c["source_immutable_sha_verified"]==len(seen)
        census={x["source_sha256"]:x for x in c["rows"]}
        assert set(census)==seen
        for row in records:
            obs=census[row["source_sha256"]]
            assert obs["source_bytes"]==row["source_bytes"]
            row["census"]=obs
            if (not row["duplicate_within_batch"]
                and not row["overlap_625"]
                and obs["status"]=="NATURAL_SYID_PARSED"
                and obs["is_fe_ff_boundary"]):
                row["writer"]=inherited.writer_probe(obs,stage,writer)
    plan={
       "schema":"sk1.cfb-diag-pub-t-991.plan.v1",
       "sources":[{"category":"apache_poi","commit":POI_PIN,"tree":POI_TREE,"count":21},
                  {"category":"aspose_dotnet","commit":ASPOSE_PIN,"count":5},
                  {"category":"file_format","commit":FILE_FORMAT_PIN,"count":1}],
       "all_source_paths":27,
       "original_quill_scanner_from_t987":T987_PIN,
       "original_writer_from_t984":T984_PIN,
       "original_t963_helper":T963_PIN,
       "original_t971_source_selector":T971_PIN,
       "upstream_pub_writer":RAR2_PIN,
       "previous_625_donor":LALAMU_PIN,
       "previous_625_tree":LALAMU_TREE,
       "previous_full_rar_authority_count":1556,
       "source_immutable":True,
       "writer_only_on_sha_disjoint_natural_FE_FF":True,
       "synthetic_SYID_header_patch":False,
       "native_publisher_saveas":"NOT_EVALUATED",
       "source_bytes_artifact_exported":False}
    (out/"plan.json").write_text(json.dumps(plan,ensure_ascii=True,indent=2)+"\n")
    (out/"records.json").write_text(json.dumps(records,ensure_ascii=True,indent=2)+"\n")
    report={
       "schema":"sk1.cfb-diag-pub-t-991.report.v1",
       "plan_sha256":sha((out/"plan.json").read_bytes()),
       "summary":summarize(records),"records":records,
       "source_bytes_artifact_exported":False,
       "native_publisher_saveas":"NOT_EVALUATED"
    }
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=True,indent=2)+"\n")
    sm=report["summary"]
    print(json.dumps({
        "all_27_sources_verified":len(records),
        "unique_sha":len(seen),
        "outside_625":sm["overlap_census"].get("outside_625_unique_sha",0),
        "new_natural_quill_syid":sm["distinct_non625_original_syid_parsed"],
        "new_original_fe_ff":sm["distinct_non625_original_low_FE_FF"],
        "true_writer_finals":sm["writer_inverse_materialized_final_files"],
        "counterexamples":len(sm["writer_inverse_physical_counterexamples"])
    },sort_keys=True))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
