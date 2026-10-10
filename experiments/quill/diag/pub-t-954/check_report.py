#!/usr/bin/env python3
"""PUB-T-954 fail-closed, no-Writer, no-payload TOKN diagnostic receipt gate."""
from __future__ import annotations
import collections,hashlib,json,re,sys
from pathlib import Path

SOURCE=re.compile(r"^[a-f0-9]{64}$")
UPSTREAM="703808408fd919e564a90cdc236e81db3c04af8b"
EXP002="651cb720c17ee9c42330173513c077b88b01a3176f580343e841d6a0498cc273"
FINGERPRINT={
"schema","source_sha256","source_bytes","story_ordinal","story_syid","story_catalog_index",
"story_utf16_len","story_ascii_count","eligible_stories_inspected","quill_stream_length",
"quill_descriptor_nodes","quill_descriptor_count","source_tokn_descriptor_count",
"target_tokn_descriptor_count","target_parsed_tokn_chunk_count","target_tcd_chunk_count",
"fdpp_descriptor_count","fdpc_descriptor_count","btep_descriptor_count","btec_descriptor_count",
"parsed_plc_token_count","parsed_first_phase_block_count","parsed_second_phase_block_count",
"parsed_opaque_property_block_count","parsed_target_record_count",
"parsed_known_token_kind_count","parsed_known_token_length_count","parsed_boundary_count",
"parsed_has_target_section","parsed_has_opaque_tail","parsed_opaque_tail_length",
"writer_guard_predicts_tokn","writer_called","source_immutable",
"publisher_native_acceptance","product_download_authorized"
}
WITNESS={"source_sha256","story_ordinal","story_utf16_len","story_ascii_count",
         "exp002_label","sampling_stratum"}
RECORD={"source_sha256","story_ordinal","status","reason","probe"}
SUMMARY={
"registered_stories","registered_sources","evaluated_stories","excluded_stories",
"two_pass_reproduced","positive_label_count","control_label_count",
"confusion","matched_control_strata","parsed_target_tokn_chunks",
"parsed_effective_tokn_tokens","same_pub_control_with_foreign_tokn",
"observations","non_evaluated","native_publisher_acceptance","writer_changed"
}
OBS={"source_sha256","story_ordinal","story_syid","exp002_label","sampling_stratum",
     "has_target_tokn_descriptor","has_tokn_elsewhere_in_source","plc_tokens_in_target"}

def exact(x,keys):
    assert isinstance(x,dict) and set(x)==keys,(set(x)-keys,keys-set(x))

def read_witness_file():
    p=Path(__file__).resolve().parent/"witnesses.psv"
    data=p.read_bytes();assert EXP002 in data.decode()
    lines=[x for x in data.decode().splitlines() if x and not x.startswith("#")]
    assert len(lines)==13
    rows=[]
    for line in lines:
        f=line.split("|");assert len(f)==6
        sha,ordinal,units,ascii_total,label,stratum=f
        assert SOURCE.fullmatch(sha)
        rows.append({"source_sha256":sha,"story_ordinal":int(ordinal),
            "story_utf16_len":int(units),"story_ascii_count":int(ascii_total),
            "exp002_label":label,"sampling_stratum":stratum})
    assert len(set((x["source_sha256"],x["story_ordinal"]) for x in rows))==13
    assert len(set(x["source_sha256"] for x in rows))==11
    assert collections.Counter(x["exp002_label"] for x in rows)=={
        "TOKN_BLOCKED":1,"NON_TOKN_PASS":12}
    assert collections.Counter(x["sampling_stratum"] for x in rows)=={
        "positive":1,"same_source_control":2,"matched_control":10}
    positive=next(x for x in rows if x["sampling_stratum"]=="positive")
    assert positive["source_sha256"]=="1e7f38b3ce1d0d956815992b15d361c405fc4bbdced5cdabb3c4581327cc183e"
    assert positive["story_ordinal"]==2 and positive["story_utf16_len"]==6
    assert all(x["source_sha256"]==positive["source_sha256"] for x in rows
               if x["sampling_stratum"]=="same_source_control")
    assert all(x["story_utf16_len"]==6 for x in rows
               if x["sampling_stratum"]=="matched_control")
    return rows,hashlib.sha256(data).hexdigest()

def check(root:Path):
    witnesses,hashvalue=read_witness_file()
    plan=json.loads((root/"plan.json").read_text(encoding="utf-8"))
    records=json.loads((root/"records.json").read_text(encoding="utf-8"))
    report=json.loads((root/"report.json").read_text(encoding="utf-8"))
    exact(plan,{"schema","upstream_commit","exp002_zip_sha256",
        "exp002_artifact_id","witness_sha256","source_manifest","witnesses",
        "hypothesis","read_only_passes","writer_invoked"})
    assert plan["schema"]=="sk1.quill-diag-pub-t-954.plan.v1"
    assert plan["upstream_commit"]==UPSTREAM
    assert plan["exp002_zip_sha256"]==EXP002 and plan["exp002_artifact_id"]==11678607165
    assert plan["witness_sha256"]==hashvalue and plan["witnesses"]==witnesses
    assert plan["source_manifest"].startswith(
        "https://raw.githubusercontent.com/Lalalalendia/rar2/"+UPSTREAM+"/")
    assert plan["read_only_passes"]==2 and plan["writer_invoked"] is False
    exact(report,{"schema","upstream_commit","exp002_zip_sha256","witness_sha256",
        "summary","records","writer_invoked","native_publisher_acceptance"})
    assert report["schema"]=="sk1.quill-diag-pub-t-954.report.v1"
    assert report["upstream_commit"]==UPSTREAM and report["exp002_zip_sha256"]==EXP002
    assert report["witness_sha256"]==hashvalue and report["records"]==records
    assert report["writer_invoked"] is False and report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert isinstance(records,list) and len(records)==13
    identities={(w["source_sha256"],w["story_ordinal"]):w for w in witnesses}
    observed=set(); confusion=collections.Counter();sums=collections.Counter();notes=[]
    allowed_num=FINGERPRINT-{"schema","source_sha256",
        "writer_guard_predicts_tokn","writer_called","source_immutable",
        "publisher_native_acceptance","product_download_authorized",
        "parsed_has_target_section","parsed_has_opaque_tail"}
    for r in records:
        exact(r,RECORD)
        identity=(r["source_sha256"],r["story_ordinal"])
        assert identity in identities and identity not in observed
        observed.add(identity)
        w=identities[identity]
        assert r["status"]=="EVALUATED" and r["reason"]=="READ_ONLY_TWO_PASS_MATCH"
        q=r["probe"];exact(q,FINGERPRINT)
        assert q["schema"]=="sk1.quill-diag-pub-t-954.probe.v1"
        assert q["source_sha256"]==identity[0]
        assert q["story_ordinal"]==identity[1]
        assert q["story_utf16_len"]==w["story_utf16_len"]
        assert q["story_ascii_count"]==w["story_ascii_count"]
        assert q["writer_called"] is False and q["source_immutable"] is True
        assert q["publisher_native_acceptance"]=="NOT_EVALUATED"
        assert q["product_download_authorized"] is False
        for x in allowed_num:
            assert type(q[x]) is int and 0<=q[x]<=12*1024*1024,x
        for x in ("parsed_has_target_section","parsed_has_opaque_tail","writer_guard_predicts_tokn"):
            assert type(q[x]) is bool,x
        assert q["target_tokn_descriptor_count"]==q["target_parsed_tokn_chunk_count"]
        assert q["target_tokn_descriptor_count"]<=q["source_tokn_descriptor_count"]
        assert q["writer_guard_predicts_tokn"]==(q["target_tokn_descriptor_count"]>0)
        assert q["parsed_first_phase_block_count"]==q["parsed_plc_token_count"]
        assert q["parsed_second_phase_block_count"]==q["parsed_plc_token_count"]
        assert q["parsed_boundary_count"]==q["parsed_plc_token_count"] + q["target_parsed_tokn_chunk_count"]
        assert q["parsed_known_token_kind_count"]<=q["parsed_plc_token_count"]
        assert q["parsed_known_token_length_count"]<=q["parsed_plc_token_count"]
        is_tokn=w["exp002_label"]=="TOKN_BLOCKED"
        pred=q["writer_guard_predicts_tokn"]
        confusion["tp" if is_tokn and pred else "fn" if is_tokn else "fp" if pred else "tn"]+=1
        sums["chunks"]+=q["target_parsed_tokn_chunk_count"]
        sums["tokens"]+=q["parsed_plc_token_count"]
        if w["sampling_stratum"]=="same_source_control" and q["source_tokn_descriptor_count"]>0:
            sums["same_source_other"]+=1
        notes.append({"source_sha256":identity[0],"story_ordinal":identity[1],
            "story_syid":q["story_syid"],"exp002_label":w["exp002_label"],
            "sampling_stratum":w["sampling_stratum"],
            "has_target_tokn_descriptor":q["target_tokn_descriptor_count"]>0,
            "has_tokn_elsewhere_in_source":
                q["source_tokn_descriptor_count"]>0 and q["target_tokn_descriptor_count"]==0,
            "plc_tokens_in_target":q["parsed_plc_token_count"]})
    assert observed==set(identities)
    s=report["summary"];exact(s,SUMMARY)
    assert s["registered_stories"]==s["evaluated_stories"]==s["two_pass_reproduced"]==13
    assert s["registered_sources"]==11 and s["excluded_stories"]==0
    assert s["positive_label_count"]==1 and s["control_label_count"]==12
    assert s["confusion"]=={k:confusion[k] for k in ("tp","fp","fn","tn")}
    assert s["matched_control_strata"]=={"same_source":2,"length6_other_source":10}
    assert s["parsed_target_tokn_chunks"]==sums["chunks"]
    assert s["parsed_effective_tokn_tokens"]==sums["tokens"]
    assert s["same_pub_control_with_foreign_tokn"]==sums["same_source_other"]
    assert s["observations"]==notes and s["non_evaluated"]==[]
    assert s["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert s["writer_changed"] is False
    print("SK1 PUB-T-954 SOURCE-SAFE VERIFY PASS",
        json.dumps({"confusion":s["confusion"],"cases":13,
            "two_pass":13,"TOKN_chunks":s["parsed_target_tokn_chunks"],
            "TOKN_tokens":s["parsed_effective_tokn_tokens"]},sort_keys=True))

if __name__=="__main__":
    assert len(sys.argv)==2
    check(Path(sys.argv[1]))
