#!/usr/bin/env python3
"""PUB-T-983: strict independent arithmetic and output-schema gate."""
from collections import Counter
import json
from pathlib import Path
import re
import sys

SHA256=re.compile(r"^[0-9a-f]{64}$")
SHA1=re.compile(r"^[0-9a-f]{40}$")
FILE_KEYS={"schema","status","source_sha256","source_bytes","stream_count",
 "stream_bytes","quill_bytes","measurements","output_bytes",
 "logical_streams_equal","native_publisher_acceptance"}
MEAS_KEYS={"op","repeat","peak_live_new_heap_bytes","allocated_bytes_total",
 "allocation_calls","read_calls","source_read_bytes","source_seeks","elapsed_us"}
OPS=("inspect","read_quill","identity_replace")
STATES={"EVALUATED","NO_QUILL","NOT_EVALUATED","PROBE_UNAVAILABLE"}
REASONS={"NOT_STARTED","OK","redirect_not_allowed","http_non_200",
 "source_size_drift","source_git_blob_sha_drift","source_unavailable",
 "PROCESS_OR_TIMEOUT","PROCESS_FAILED","BAD_RECEIPT"}
EXPECTED_NAMES={"51318.pub","60685.pub","LinkAt10And20And30And40.pub",
 "Sample2000.pub","Sample2_2010.pub","Sample3.pub","Sample4.pub",
 "Sample98.pub","SampleBrochure.pub","SampleNewsletter.pub"}
PIN="703808408fd919e564a90cdc236e81db3c04af8b"
APACHE="ae62bb5116b9aee19ebd5834e3a82066132c9f7f"

def mid(values):
    x=sorted(values)
    return x[len(x)//2]

def check(folder:Path):
    assert {p.name for p in folder.iterdir()}=={"plan.json","records.json","report.json"}
    plan=json.loads((folder/"plan.json").read_text(encoding="utf-8"))
    records=json.loads((folder/"records.json").read_text(encoding="utf-8"))
    report=json.loads((folder/"report.json").read_text(encoding="utf-8"))
    assert set(plan)=={"schema","apache_pin","rar2_pin","inputs","ops","repeats",
      "measurement_unit","publication","native_publisher_acceptance"}
    assert plan["schema"]=="sk1.pub-t-983.plan.v1"
    assert plan["apache_pin"]==APACHE and plan["rar2_pin"]==PIN
    assert plan["ops"]==list(OPS) and plan["repeats"]==3
    assert plan["measurement_unit"]=="new_live_allocations_during_single_call"
    assert plan["publication"]=="source_safe_statistics_only"
    assert plan["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert isinstance(plan["inputs"],list) and len(plan["inputs"])==10
    assert {x["fixture"] for x in plan["inputs"]}==EXPECTED_NAMES
    assert len(records)==10
    assert set(report)=={"schema","apache_pin","rar2_pin",
        "native_publisher_acceptance","source_pub_export_allowed","summary","records"}
    assert report["schema"]=="sk1.pub-t-983.report.v1"
    assert report["apache_pin"]==APACHE and report["rar2_pin"]==PIN
    assert report["native_publisher_acceptance"]=="NOT_EVALUATED"
    assert report["source_pub_export_allowed"] is False and report["records"]==records
    statuses=Counter();by_op={k:{"peaks":[],"alloc":[],"reads":[],"calls":[],"time":[],"ratio":[]}
        for k in OPS}
    verified=0;preserved=0
    for p,r in zip(plan["inputs"],records):
        assert set(p)=={"fixture","expected_bytes","git_blob_sha1"}
        assert set(r)=={"fixture","git_blob_sha1","expected_bytes",
             "source_sha256","status","reason","probe"}
        assert p=={k:r[k] for k in ("fixture","expected_bytes","git_blob_sha1")}
        assert SHA1.fullmatch(p["git_blob_sha1"])
        assert 0<p["expected_bytes"]<=512*1024 and type(p["expected_bytes"]) is int
        assert r["status"] in STATES and r["reason"] in REASONS
        if r["source_sha256"] is not None:
            assert isinstance(r["source_sha256"],str) and SHA256.fullmatch(r["source_sha256"])
            verified+=1
        statuses[r["status"]]+=1
        if r["probe"] is None:
            assert r["status"] in {"NOT_EVALUATED","PROBE_UNAVAILABLE"}
            continue
        assert r["status"] in {"EVALUATED","NO_QUILL"}
        assert r["reason"]=="OK" and r["source_sha256"] is not None
        d=r["probe"]
        assert isinstance(d,dict) and set(d)==FILE_KEYS
        assert d["schema"]=="sk1.pub-t-983.file.v1"
        assert d["status"]==r["status"]
        assert d["source_sha256"]==r["source_sha256"] and d["source_bytes"]==r["expected_bytes"]
        assert d["native_publisher_acceptance"]=="NOT_EVALUATED"
        for key in ("source_bytes","stream_count","stream_bytes","quill_bytes"):
            assert type(d[key]) is int and 0<=d[key]<=1_000_000
        assert d["stream_count"]<=200 and d["stream_bytes"]<=3_000_000
        assert isinstance(d["measurements"],list)
        if d["status"]=="NO_QUILL":
            assert d["measurements"]==[]
            assert d["logical_streams_equal"] is None and d["output_bytes"] is None
            assert d["quill_bytes"]==0
            continue
        preserved+=int(d["logical_streams_equal"] is True)
        assert d["logical_streams_equal"] is True
        assert type(d["output_bytes"]) is int and 0<d["output_bytes"]<=2*d["source_bytes"]
        assert 0<d["quill_bytes"]<=d["stream_bytes"]
        assert len(d["measurements"])==9
        assert {(m["op"],m["repeat"]) for m in d["measurements"]}=={
           (op,i) for op in OPS for i in range(3)}
        for m in d["measurements"]:
            assert isinstance(m,dict) and set(m)==MEAS_KEYS
            assert m["op"] in OPS and type(m["repeat"]) is int and 0<=m["repeat"]<=2
            for key in MEAS_KEYS-{"op","repeat"}:
                assert type(m[key]) is int and 0<=m[key]<1_000_000_000,key
        for op in OPS:
            vals=[m for m in d["measurements"] if m["op"]==op]
            assert len(vals)==3
            z=by_op[op]
            peak=mid([m["peak_live_new_heap_bytes"] for m in vals])
            assert peak>0,("zero heap in CFB operation",op)
            z["peaks"].append(peak)
            z["alloc"].append(mid([m["allocated_bytes_total"] for m in vals]))
            z["reads"].append(mid([m["source_read_bytes"] for m in vals]))
            z["calls"].append(mid([m["read_calls"] for m in vals]))
            z["time"].append(mid([m["elapsed_us"] for m in vals]))
            z["ratio"].append(round(peak/r["expected_bytes"],4))
    expected_ops={}
    for op,z in by_op.items():
        N=len(z["peaks"])
        expected_ops[op]={
           "samples":N,
           "median_peak_bytes":mid(z["peaks"]) if N else 0,
           "max_peak_bytes":max(z["peaks"]) if N else 0,
           "median_allocated_bytes":mid(z["alloc"]) if N else 0,
           "median_read_bytes":mid(z["reads"]) if N else 0,
           "median_read_calls":mid(z["calls"]) if N else 0,
           "median_elapsed_us":mid(z["time"]) if N else 0,
           "median_peak_over_pub":mid([int(x*10000) for x in z["ratio"]])/10000 if N else 0,
           "max_peak_over_pub":max(z["ratio"]) if N else 0,
        }
    summary={"attempted":10,"sha_verified":verified,
     "evaluated":statuses["EVALUATED"],
     "status_counts":dict(sorted(statuses.items())),
     "logical_stream_identity_success":preserved,
     "per_operation":expected_ops}
    assert report["summary"]==summary,"summary does not independently reconcile"
    print("PUB-T-983 VERIFIED SOURCE-SAFE RECEIPT:",summary["evaluated"],
        "CFB sources, peaks", {k:v["median_peak_over_pub"] for k,v in expected_ops.items()})
if __name__=="__main__":
    check(Path(sys.argv[1]))
