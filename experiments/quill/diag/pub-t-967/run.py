#!/usr/bin/env python3
"""PUB-T-967: blind read-only Quill growth-envelope predictions, never Writer."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parent
BASE=HERE.parents[2]
SPEC=importlib.util.spec_from_file_location("sk1_exp005_safe_public_intake",BASE/"sk1-exp-005"/"run.py")
assert SPEC and SPEC.loader
source=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(source)

RAR2_PIN="703808408fd919e564a90cdc236e81db3c04af8b"
LALAMU_PIN="f78cc6f455f4dc222868f9cc035511a6ca7a91ea"
PREVIOUS_SCIENTIFIC_SHA="4ed320411bb5bebf23ea5a4c31c336d3fba74ce1"
PREVIOUS_ZIP_SHA="ab73d6206663523929843616e196287563468b0ac8988005842349afc206aeb9"
PREVIOUS_RUN=38086685517
BINARY="sk1_pub_t_967_growth_readonly"
EXPECTED_SOURCE_COUNT=14
CODES={"quill_growth_would_discard_descriptor","quill_growth_would_discard_unknown"}
PRED_CODES=CODES|{"quill_insufficient_capacity","PREDICTED_PASS_UNEXPECTED"}

def read_labels():
    data=(HERE/"witnesses.psv").read_bytes()
    content=data.decode("utf-8")
    assert PREVIOUS_ZIP_SHA in content and RAR2_PIN in content and LALAMU_PIN in content
    labels={}
    for line in content.splitlines():
        if not line or line.startswith("#"):continue
        parts=line.split("|")
        assert len(parts)==7,"invalid witness fields"
        sha=parts[0]
        assert len(sha)==64 and all(c in "0123456789abcdef" for c in sha)
        ordinal,offset,length,pass_n,fail_n=map(int,parts[1:6])
        code=parts[6]
        assert code in CODES and 0<=ordinal<512 and 0<=offset<length<1_000_000
        assert 1<=pass_n<=8192 and fail_n==pass_n+1
        assert sha not in labels
        labels[sha]={
            "source_sha256":sha,"story_ordinal":ordinal,
            "offset_utf16":offset,"before_utf16":length,
            "last_pass_utf16":pass_n,"first_fail_utf16":fail_n,
            "first_fail_guard":code
        }
    assert len(labels)==EXPECTED_SOURCE_COUNT
    assert Counter(x["first_fail_guard"] for x in labels.values())=={
        "quill_growth_would_discard_descriptor":11,
        "quill_growth_would_discard_unknown":3
    }
    return labels,hashlib.sha256(data).hexdigest()

def source_row(row:dict, binary:Path, label:dict)->dict:
    rec={
        "source_sha256":row["sha256"],"source_host":row["host"],
        "source_bytes":row["size"],"status":"NOT_EVALUATED",
        "reason":"NOT_STARTED","structural":None,
        "matches_empirical_threshold":None,"matches_empirical_guard":None,
        "predicted_minus_empirical_units":None
    }
    try:
        data=source.download(row)
        if len(data)!=row["size"] or hashlib.sha256(data).hexdigest()!=row["sha256"]:
            rec["reason"]="SOURCE_SHA_DRIFT"
            return rec
        if not data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            rec["reason"]="SOURCE_CFB_INVALID"
            return rec
        with tempfile.TemporaryDirectory(prefix="sk1-pub-t-967-") as folder:
            folder=Path(folder)
            original=folder/"original.pub"
            out=folder/"readonly_receipt.json"
            original.write_bytes(data)
            proc=subprocess.run([str(binary),str(original),row["sha256"],str(out)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=80,check=False)
            if proc.returncode!=0 or not out.is_file():
                rec["reason"]="SOURCE_READONLY_PROBE_UNAVAILABLE"
                return rec
            evidence=json.loads(out.read_text(encoding="utf-8"))
        if (evidence.get("schema")!="sk1.quill-diag-pub-t-967.source-envelope.v1"
            or evidence.get("source_sha256")!=row["sha256"]
            or evidence.get("source_bytes")!=row["size"]
            or evidence.get("writer_invoked") is not False
            or evidence.get("candidate_generated") is not False
            or evidence.get("source_immutable") is not True
            or evidence.get("native_publisher_acceptance")!="NOT_EVALUATED"
            or evidence.get("product_pub_download_authorized") is not False):
            rec["reason"]="INVALID_STRUCTURAL_RECEIPT"
            return rec
        matched_identity=(evidence.get("selected_story_ordinal")==label["story_ordinal"]
            and evidence.get("selected_offset_utf16")==label["offset_utf16"]
            and evidence.get("selected_story_utf16_len")==label["before_utf16"])
        if not matched_identity:
            rec["reason"]="STORY_OR_OFFSET_IDENTITY_CHANGED"
            return rec
        predicted_n=evidence.get("source_only_predicted_max_growth_utf16")
        predicted_fail=evidence.get("source_only_predicted_first_failure_utf16")
        predicted_code=evidence.get("source_only_predicted_first_failure_guard")
        if (type(predicted_n) is not int or not 0<=predicted_n<=8192 or
            predicted_fail!=predicted_n+1 or predicted_code not in PRED_CODES):
            rec["reason"]="INVALID_PREDICTION"
            return rec
        rec.update({
            "status":"EVALUATED","reason":"BLIND_PREDICTION_RECORDED",
            "structural":evidence,
            "matches_empirical_threshold":predicted_n==label["last_pass_utf16"],
            "matches_empirical_guard":predicted_code==label["first_fail_guard"],
            "predicted_minus_empirical_units":predicted_n-label["last_pass_utf16"]
        })
    except Exception:
        # Raw exception may include source URLs, host paths or private bytes.
        rec["reason"]="BOUNDED_HTTP_OR_PROBE_UNAVAILABLE"
    return rec

def summarize(rows:list[dict], labels:dict)->dict:
    status=Counter(); threshold=Counter(); guard=Counter(); factors=Counter()
    diagnostics=[]; evaluated_sources=set()
    for row in rows:
        status[row["status"]]+=1
        key=row["source_sha256"]
        lab=labels[key]
        if row["status"]!="EVALUATED":
            diagnostics.append({"source_sha256":key,"status":row["status"],
                "reason":row["reason"]})
            continue
        evidence=row["structural"]
        evaluated_sources.add(key)
        threshold["MATCH" if row["matches_empirical_threshold"] else "MISMATCH"]+=1
        guard["MATCH" if row["matches_empirical_guard"] else "MISMATCH"]+=1
        factors[evidence["limiting_factors"]]+=1
        diagnostics.append({
            "source_sha256":key,
            "status":"EVALUATED",
            "source_story_ordinal":evidence["selected_story_ordinal"],
            "source_offset_utf16":evidence["selected_offset_utf16"],
            "empirical_last_pass":lab["last_pass_utf16"],
            "source_only_prediction":evidence["source_only_predicted_max_growth_utf16"],
            "empirical_first_guard":lab["first_fail_guard"],
            "source_only_first_guard":evidence["source_only_predicted_first_failure_guard"],
            "matches_threshold":row["matches_empirical_threshold"],
            "matches_guard":row["matches_empirical_guard"],
            "gap_bytes":evidence["pre_anchor_gap_bytes"],
            "trailing_zero_bytes":evidence["trailing_zero_bytes"],
            "descriptor_clearance_bytes":evidence["nontext_descriptor_clearance_bytes"],
            "limiting_factors":evidence["limiting_factors"]
        })
    return {
        "predeclared_sources":EXPECTED_SOURCE_COUNT,
        "evaluated_sources":len(evaluated_sources),
        "source_status":dict(sorted(status.items())),
        "empirical_guard_counts":dict(sorted(Counter(
            x["first_fail_guard"] for x in labels.values()).items())),
        "threshold_prediction_agreement":dict(sorted(threshold.items())),
        "first_guard_prediction_agreement":dict(sorted(guard.items())),
        "limiting_factors":dict(sorted(factors.items())),
        "per_source_diagnostics":diagnostics,
        "writer_invoked":False,
        "original_962_writer_outcomes_only":True,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":False,
    }

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--rar2",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    binary=a.rar2.resolve(strict=True)/"tools/native-pub-candidate-cli/target/release/examples"/BINARY
    if not binary.is_file():p.error("read-only Rust inspector absent")
    assert source.RAR2_PIN==RAR2_PIN and source.LALAMU_PIN==LALAMU_PIN
    labels,labels_sha=read_labels()
    manifest=source.candidates()
    assert len(manifest)==source.EXPECTED_ATTEMPTED==62
    indexed={r["sha256"]:r for r in manifest}
    assert len(indexed)==62 and all(k in indexed for k in labels)
    selected=[indexed[sha] for sha in labels]
    assert sum(r["size"] for r in selected)<=50*1024*1024
    out=a.out.resolve()
    out.mkdir(parents=True,exist_ok=True)
    plan={
        "schema":"sk1.quill-diag-pub-t-967.plan.v1",
        "upstream_rar2_sha":RAR2_PIN,"source_lalamu_sha":LALAMU_PIN,
        "upstream_source_manifest":source.NEW_MANIFEST,
        "historical_experiment":"SK1-QUILL-EXP-PUB-T-962",
        "historical_scientific_sha":PREVIOUS_SCIENTIFIC_SHA,
        "historical_source_safe_artifact_zip_sha256":PREVIOUS_ZIP_SHA,
        "historical_actions_run_id":PREVIOUS_RUN,
        "pre_registered_witnesses_sha256":labels_sha,
        "witnesses":list(labels.values()),"predeclared_sources":EXPECTED_SOURCE_COUNT,
        "prediction_blind_to_labels":True,"writer_invoked":False,
        "scope":"read-only structural threshold prediction at existing 962 second ASCII offset, not another Writer run",
        "native_publisher_acceptance":"NOT_EVALUATED"
    }
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf8")
    rows=[]
    for r in selected:
        rows.append(source_row(r,binary,labels[r["sha256"]]))
        (out/"records.json").write_text(json.dumps(rows,indent=2)+"\n",encoding="utf8")
    s=summarize(rows,labels)
    report={
        "schema":"sk1.quill-diag-pub-t-967.report.v1",
        "upstream_rar2_sha":RAR2_PIN,
        "pre_registered_witnesses_sha256":labels_sha,
        "summary":s,"records":rows,
        "writer_invoked":False,"native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":False
    }
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf8")
    complete=(s["evaluated_sources"]==14 and
        all(r["status"]=="EVALUATED" for r in rows))
    print(json.dumps({"result":"COMPLETE" if complete else "NOT_EVALUATED",
        "evaluated":s["evaluated_sources"],"threshold":s["threshold_prediction_agreement"],
        "first_guard":s["first_guard_prediction_agreement"],
        "limiting_factors":s["limiting_factors"]},sort_keys=True))
    return 0 if complete else 2
if __name__=="__main__":
    sys.exit(main())
