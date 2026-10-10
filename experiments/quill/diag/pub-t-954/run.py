#!/usr/bin/env python3
"""PUB-T-954: SHA-pinned TOKN-vs-ordinary Story diagnostic, read-only only."""
from __future__ import annotations
import argparse, collections, hashlib, importlib.util, json, re, subprocess, sys, tempfile
from pathlib import Path

BASE=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("sk1_shared_intake", BASE/"sk1-exp-001"/"run.py")
assert SPEC and SPEC.loader
common=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(common)
UPSTREAM="703808408fd919e564a90cdc236e81db3c04af8b"
EXP002_ZIP="651cb720c17ee9c42330173513c077b88b01a3176f580343e841d6a0498cc273"
TOKN_SOURCE="1e7f38b3ce1d0d956815992b15d361c405fc4bbdced5cdabb3c4581327cc183e"
SHA=re.compile(r"^[0-9a-f]{64}$")
CFB=bytes.fromhex("d0cf11e0a1b11ae1")

def witnesses()->tuple[list[dict],str]:
    data=(HERE/"witnesses.psv").read_bytes()
    rows=[]
    assert EXP002_ZIP in data.decode(), "wrong prior evidence"
    for line in data.decode().splitlines():
        if not line or line.startswith("#"):continue
        parts=line.split("|")
        assert len(parts)==6, "witness fields"
        source,ordinal,length,ascii_total,label,stratum=parts
        assert SHA.fullmatch(source) and label in ("TOKN_BLOCKED","NON_TOKN_PASS")
        assert stratum in ("positive","same_source_control","matched_control")
        story=int(ordinal); units=int(length); ascii_count=int(ascii_total)
        assert 0<=story<3 and 0<ascii_count<=units and units<5000000
        rows.append({"source_sha256":source,"story_ordinal":story,
            "story_utf16_len":units,"story_ascii_count":ascii_count,
            "exp002_label":label,"sampling_stratum":stratum})
    assert len(rows)==13
    assert len({(r["source_sha256"],r["story_ordinal"]) for r in rows})==13
    assert len({r["source_sha256"] for r in rows})==11
    assert sum(r["exp002_label"]=="TOKN_BLOCKED" for r in rows)==1
    assert sum(r["sampling_stratum"]=="same_source_control" for r in rows)==2
    assert sum(r["sampling_stratum"]=="matched_control" for r in rows)==10
    assert all(r["source_sha256"]==TOKN_SOURCE for r in rows if
        r["sampling_stratum"] in ("positive","same_source_control"))
    assert all(r["story_utf16_len"]==6 for r in rows if
        r["sampling_stratum"]=="matched_control")
    return rows,hashlib.sha256(data).hexdigest()

def evaluate(source:dict, cases:list[dict], binary:Path)->list[dict]:
    sha=source["sha256"]
    def not_eval(reason):
        return [{"source_sha256":sha,"story_ordinal":w["story_ordinal"],
            "status":"NOT_EVALUATED","reason":reason} for w in cases]
    try:
        raw=common.retrieve(source["url"], min(source["size"]+1,common.MAX_FILE_BYTES))
        if len(raw)!=source["size"] or common.digest(raw)!=sha:
            return not_eval("SOURCE_SHA_OR_SIZE_DRIFT")
        if not raw.startswith(CFB):return not_eval("CFB_SIGNATURE_MISSING")
        rows=[]
        with tempfile.TemporaryDirectory(prefix="sk1-tokn-diag-") as tmp:
            temp=Path(tmp)
            original=temp/"original.pub"
            original.write_bytes(raw)
            for i,w in enumerate(cases):
                got=[]
                for repeat in (0,1):
                    out=temp/f"receipt-{i}-{repeat}.json"
                    args=[str(binary),str(original),sha,str(w["story_ordinal"]),
                        str(w["story_utf16_len"]),str(w["story_ascii_count"]),str(out)]
                    cp=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        timeout=90,check=False)
                    if cp.returncode or not out.is_file():
                        return not_eval("READ_ONLY_PROBE_FAILED")
                    try:
                        got.append(json.loads(out.read_text(encoding="utf-8")))
                    except (OSError,ValueError):
                        return not_eval("PROBE_JSON_INVALID")
                if got[0]!=got[1]:
                    return not_eval("TWO_READ_ONLY_PASSES_DIFFER")
                p=got[0]
                if (p.get("schema")!="sk1.quill-diag-pub-t-954.probe.v1"
                    or p.get("writer_called") is not False
                    or p.get("source_sha256")!=sha
                    or p.get("story_ordinal")!=w["story_ordinal"]
                    or p.get("source_immutable") is not True
                    or p.get("publisher_native_acceptance")!="NOT_EVALUATED"
                    or p.get("product_download_authorized") is not False):
                    return not_eval("INVALID_READ_ONLY_RECEIPT")
                rows.append({"source_sha256":sha,"story_ordinal":w["story_ordinal"],
                    "status":"EVALUATED","reason":"READ_ONLY_TWO_PASS_MATCH",
                    "probe":p})
            if common.digest(original.read_bytes())!=sha:
                raise ValueError("SOURCE_MUTATED")
        return rows
    except Exception:
        return not_eval("SOURCE_OR_HARNESS_UNAVAILABLE")

def summarize(rows:list[dict],w:list[dict])->dict:
    labels={(z["source_sha256"],z["story_ordinal"]):z for z in w}
    matrix=collections.Counter()
    diagnostics=collections.Counter()
    exclusions=[]
    samples=[]
    for row in rows:
        key=(row["source_sha256"],row["story_ordinal"])
        witness=labels[key]
        if row["status"]!="EVALUATED":
            exclusions.append({"source_sha256":key[0],"story_ordinal":key[1],
                "reason":row["reason"]})
            continue
        p=row["probe"]
        exp=witness["exp002_label"]=="TOKN_BLOCKED"
        pred=p["writer_guard_predicts_tokn"]
        matrix["tp" if pred and exp else
            "fp" if pred and not exp else
            "fn" if exp and not pred else "tn"]+=1
        diagnostics["parsed_tokn_chunks"]+=p["target_parsed_tokn_chunk_count"]
        diagnostics["parsed_tokn_effective_tokens"]+=p["parsed_plc_token_count"]
        if witness["sampling_stratum"]=="same_source_control" and p["source_tokn_descriptor_count"]>0:
            diagnostics["same_pub_non_tokn_stories_with_other_story_tokn"]+=1
        samples.append({"source_sha256":key[0],"story_ordinal":key[1],
            "story_syid":p["story_syid"],"exp002_label":witness["exp002_label"],
            "sampling_stratum":witness["sampling_stratum"],
            "has_target_tokn_descriptor":p["target_tokn_descriptor_count"]>0,
            "has_tokn_elsewhere_in_source":p["source_tokn_descriptor_count"]>0 and
                p["target_tokn_descriptor_count"]==0,
            "plc_tokens_in_target":p["parsed_plc_token_count"]})
    return {"registered_stories":13,"registered_sources":11,
        "evaluated_stories":len(samples),
        "excluded_stories":len(exclusions),
        "two_pass_reproduced":len(samples),
        "positive_label_count":1,"control_label_count":12,
        "confusion":{"tp":matrix["tp"],"fp":matrix["fp"],"fn":matrix["fn"],"tn":matrix["tn"]},
        "matched_control_strata":{"same_source":2,"length6_other_source":10},
        "parsed_target_tokn_chunks":diagnostics["parsed_tokn_chunks"],
        "parsed_effective_tokn_tokens":diagnostics["parsed_tokn_effective_tokens"],
        "same_pub_control_with_foreign_tokn":diagnostics["same_pub_non_tokn_stories_with_other_story_tokn"],
        "observations":samples,"non_evaluated":exclusions,
        "native_publisher_acceptance":"NOT_EVALUATED","writer_changed":False}

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--rar2",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    args=ap.parse_args()
    root=args.rar2.resolve(strict=True)
    binary=root/"tools/native-pub-candidate-cli/target/release/examples/sk1_quill_diag_pub_t_954"
    if not binary.is_file():ap.error("expected read-only binary missing")
    cases,witness_sha=witnesses()
    manifest=common.load_manifest(None)
    admitted=common.candidates(manifest)
    assert len(admitted)==26 and len({a["sha256"] for a in admitted})==26
    lookup={s["sha256"]:s for s in admitted}
    assert all(w["source_sha256"] in lookup for w in cases)
    group=collections.defaultdict(list)
    for w in cases:group[w["source_sha256"]].append(w)
    assert sum(lookup[s]["size"] for s in group) <= common.MAX_TOTAL_BYTES
    plan={"schema":"sk1.quill-diag-pub-t-954.plan.v1",
        "upstream_commit":UPSTREAM,"exp002_zip_sha256":EXP002_ZIP,
        "exp002_artifact_id":11678607165,"witness_sha256":witness_sha,
        "source_manifest":common.MANIFEST_URL,"witnesses":cases,
        "hypothesis":"TOKN descriptor option_a equals target Story ordinal; read-only classification",
        "read_only_passes":2,"writer_invoked":False}
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    (output/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    observations=[]
    for sha, witnesses_per_source in group.items():
        observations.extend(evaluate(lookup[sha],witnesses_per_source,binary))
        (output/"records.json").write_text(json.dumps(observations,indent=2)+"\n",encoding="utf-8")
    summary=summarize(observations,cases)
    report={"schema":"sk1.quill-diag-pub-t-954.report.v1",
        "upstream_commit":UPSTREAM,"exp002_zip_sha256":EXP002_ZIP,
        "witness_sha256":witness_sha,
        "summary":summary,"records":observations,"writer_invoked":False,
        "native_publisher_acceptance":"NOT_EVALUATED"}
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"result":"COMPLETE" if summary["evaluated_stories"]==13 else "NOT_EVALUATED",
        "confusion":summary["confusion"],
        "cases":summary["evaluated_stories"],
        "two_pass":summary["two_pass_reproduced"],
        "tokn_parsed":summary["parsed_target_tokn_chunks"],
        "samples":summary["observations"]},sort_keys=True))
    return 0 if summary["evaluated_stories"]==13 else 2

if __name__=="__main__":sys.exit(main())
