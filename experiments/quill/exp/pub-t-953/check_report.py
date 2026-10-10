#!/usr/bin/env python3
"""Strict schema + source-safe outcome gate for SK1 PUB-T-953."""
import hashlib, json, re, sys
from pathlib import Path
from collections import Counter
SHA=re.compile(r"^[0-9a-f]{64}$")
CODE=re.compile(r"^[a-z_]{1,64}$")
UPSTREAM="703808408fd919e564a90cdc236e81db3c04af8b"
EXP002="651cb720c17ee9c42330173513c077b88b01a3176f580343e841d6a0498cc273"
PROBE_KEYS={"schema","source_sha256","source_bytes","story_ordinal","story_utf16_len",
"a_rank","b_rank","a_offset_utf16","b_offset_utf16",
"ab_second_offset_utf16","ba_second_offset_utf16","original_immutable",
"expected_a_sha256","expected_b_sha256","single_a","single_b",
"singles_baseline_match","ab_second","ba_second","both_sequential_pass",
"same_final_semantic_text_by_construction","same_final_pub_bytes",
"publisher_native_acceptance","product_pub_download_authorized"}
PASS_KEYS={"status","candidate_sha256","reader_semantic_reopen",
"syid_siblings_preserved","project_replay_byte_equal","source_immutable"}
FAILS={"SOURCE_EDITOR_OPEN_BLOCKED","STORY_ID_UNAVAILABLE","STORY_INPUT_MISMATCH",
"CANONICAL_EDIT_REJECTED","WRITER_BLOCKED","WRITER_HASH_OR_NO_CHANGE",
"READER_REOPEN_BLOCKED","OUTPUT_STORY_ID_UNAVAILABLE","TARGET_SEMANTIC_MISMATCH",
"SYID_OR_SIBLING_MISMATCH","REPLAY_SOURCE_OPEN_BLOCKED","PROJECT_REPLAY_BLOCKED",
"PROJECT_REPLAY_WRITER_BLOCKED","PROJECT_REPLAY_BYTE_MISMATCH"}
def exact(x,fields): assert isinstance(x,dict) and set(x)==fields,(set(x)-fields,fields-set(x))
def check_step(x,positive=False):
    assert isinstance(x,dict) and "status" in x
    if x["status"]=="HOSTED_PASS":
        exact(x,PASS_KEYS)
        assert SHA.fullmatch(x["candidate_sha256"])
        assert all(x[k] is True for k in PASS_KEYS-{"status","candidate_sha256"})
    else:
        assert not positive and x["status"] in FAILS
        if x["status"]=="WRITER_BLOCKED":
            exact(x,{"status","writer_code"})
            assert CODE.fullmatch(x["writer_code"])
        else: exact(x,{"status"})
def check(folder):
    plan=json.loads((folder/"plan.json").read_text())
    rows=json.loads((folder/"records.json").read_text())
    report=json.loads((folder/"report.json").read_text())
    exact(plan,{"schema","upstream_commit","exp002_zip_sha256",
        "exp002_github_artifact_id","witnesses_sha256","manifest_url",
        "source_count","pair_count","witnesses","scope"})
    assert plan["schema"]=="sk1.quill-exp-pub-t-953.plan.v1"
    assert plan["upstream_commit"]==UPSTREAM and plan["exp002_zip_sha256"]==EXP002
    assert plan["exp002_github_artifact_id"]==11678607165
    assert plan["source_count"]==23 and plan["pair_count"]==24
    assert plan["manifest_url"].startswith("https://raw.githubusercontent.com/Lalalalendia/rar2/"+UPSTREAM+"/")
    text=(Path(__file__).resolve().parent/"witnesses.psv").read_bytes()
    assert hashlib.sha256(text).hexdigest()==plan["witnesses_sha256"]
    lines=[l for l in text.decode().splitlines() if l and not l.startswith("#")]
    assert len(lines)==24
    witnesses=plan["witnesses"]
    assert isinstance(witnesses,list) and len(witnesses)==24
    wfields={"source_sha256","story_ordinal","story_utf16_len","a_ascii_rank",
        "a_offset_utf16","expected_a_sha256","b_ascii_rank",
        "b_offset_utf16","expected_b_sha256"}
    for w,line in zip(witnesses,lines):
        exact(w,wfields)
        assert [w["source_sha256"],str(w["story_ordinal"]),str(w["story_utf16_len"]),
            str(w["a_ascii_rank"]),str(w["a_offset_utf16"]),w["expected_a_sha256"],
            str(w["b_ascii_rank"]),str(w["b_offset_utf16"]),w["expected_b_sha256"]]==line.split("|")
        assert all(SHA.fullmatch(w[k]) for k in ("source_sha256","expected_a_sha256","expected_b_sha256"))
        assert w["a_offset_utf16"]!=w["b_offset_utf16"]
    assert len({(w["source_sha256"],w["story_ordinal"]) for w in witnesses})==24
    assert len({w["source_sha256"] for w in witnesses})==23
    exact(report,{"schema","upstream_commit","exp002_zip_sha256","witnesses_sha256",
        "native_publisher_acceptance","product_pub_download_authorized","summary","records"})
    assert report["schema"]=="sk1.quill-exp-pub-t-953.report.v1"
    assert report["upstream_commit"]==UPSTREAM and report["exp002_zip_sha256"]==EXP002
    assert report["witnesses_sha256"]==plan["witnesses_sha256"]
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["product_pub_download_authorized"] is False
    assert rows==report["records"] and len(rows)==24
    ab=Counter();ba=Counter();cnt=Counter();sensitive=[];sources=set()
    by_identity={(w["source_sha256"],w["story_ordinal"]):w for w in witnesses}
    assert len(by_identity)==24
    observed=set()
    for row in rows:
        identity=(row["source_sha256"],row["story_ordinal"])
        assert identity in by_identity and identity not in observed
        observed.add(identity)
        w=by_identity[identity]
        exact(row,{"source_sha256","source_type","source_bytes","story_ordinal",
            "status","reason","record"})
        assert row["status"]=="EVALUATED" and row["reason"]=="OBSERVED"
        assert row["source_sha256"]==w["source_sha256"]
        assert row["story_ordinal"]==w["story_ordinal"]
        assert row["source_type"] in ("github","institutional-web")
        assert type(row["source_bytes"]) is int and 0<row["source_bytes"]<=12*1024*1024
        p=row["record"];exact(p,PROBE_KEYS)
        assert p["schema"]=="sk1.quill-exp-pub-t-953.probe.v1"
        assert p["source_sha256"]==w["source_sha256"] and p["source_bytes"]==row["source_bytes"]
        assert p["story_ordinal"]==w["story_ordinal"] and p["story_utf16_len"]==w["story_utf16_len"]
        assert p["a_rank"]==w["a_ascii_rank"] and p["b_rank"]==w["b_ascii_rank"]
        a=w["a_offset_utf16"];b=w["b_offset_utf16"]
        assert p["a_offset_utf16"]==a and p["b_offset_utf16"]==b
        assert p["ab_second_offset_utf16"]==b-int(a<b)
        assert p["ba_second_offset_utf16"]==a-int(b<a)
        assert p["original_immutable"] is True and p["singles_baseline_match"] is True
        assert p["same_final_semantic_text_by_construction"] is True
        assert p["publisher_native_acceptance"]=="NOT_EVALUATED"
        assert p["product_pub_download_authorized"] is False
        check_step(p["single_a"],True);check_step(p["single_b"],True)
        assert p["expected_a_sha256"]==w["expected_a_sha256"]==p["single_a"]["candidate_sha256"]
        assert p["expected_b_sha256"]==w["expected_b_sha256"]==p["single_b"]["candidate_sha256"]
        check_step(p["ab_second"]);check_step(p["ba_second"])
        s=p["ab_second"]["status"];t=p["ba_second"]["status"]
        ab[s]+=1;ba[t]+=1
        ap=s=="HOSTED_PASS";bp=t=="HOSTED_PASS"
        assert p["both_sequential_pass"]==(ap and bp)
        if ap:cnt["ab_pass"]+=1
        if bp:cnt["ba_pass"]+=1
        if ap and bp:
            cnt["both_pass"]+=1
            assert type(p["same_final_pub_bytes"]) is bool
            cnt["both_pass_byte_equal" if p["same_final_pub_bytes"] else "both_pass_byte_different"]+=1
        else:
            assert p["same_final_pub_bytes"] is None
            cnt["only_ab_pass" if ap else "only_ba_pass" if bp else "neither_pass"]+=1
        if ap!=bp:
            sensitive.append({"source_sha256":row["source_sha256"],
                "story_ordinal":row["story_ordinal"],
                "a_offset_utf16":a,"b_offset_utf16":b,
                "ab_second":p["ab_second"],"ba_second":p["ba_second"]})
        sources.add(row["source_sha256"])
    assert observed==set(by_identity)
    q=report["summary"]
    exact(q,{"sources_selected","sources_evaluated","pairs_selected","pairs_evaluated",
        "pairs_not_evaluated","baseline_pairs_verified","baseline_drift",
        "ab_pass","ba_pass","both_pass","only_ab_pass","only_ba_pass","neither_pass",
        "both_pass_byte_equal","both_pass_byte_different","ab_second_status","ba_second_status",
        "order_sensitive_witnesses","native_publisher_acceptance",
        "product_pub_download_authorized"})
    assert q["sources_selected"]==q["sources_evaluated"]==len(sources)==23
    assert q["pairs_selected"]==q["pairs_evaluated"]==q["baseline_pairs_verified"]==24
    assert q["pairs_not_evaluated"]==q["baseline_drift"]==0
    for k in ("ab_pass","ba_pass","both_pass","only_ab_pass","only_ba_pass",
        "neither_pass","both_pass_byte_equal","both_pass_byte_different"):
        assert q[k]==cnt[k],k
    assert q["ab_second_status"]==dict(sorted(ab.items()))
    assert q["ba_second_status"]==dict(sorted(ba.items()))
    assert q["order_sensitive_witnesses"]==sensitive
    assert q["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert q["product_pub_download_authorized"] is False
    print("SK1 PUB-T-953 SOURCE-SAFE VERIFIED",len(rows),"pairs",len(sources),"sources",dict(cnt))
if __name__=="__main__":
    assert len(sys.argv)==2
    check(Path(sys.argv[1]))
