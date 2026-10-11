#!/usr/bin/env python3
"""PUB-T-983: immutable Apache fixtures and bounded original pub_cfb profiling."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import urllib.request
import urllib.error

APACHE="ae62bb5116b9aee19ebd5834e3a82066132c9f7f"
RAR2="703808408fd919e564a90cdc236e81db3c04af8b"
INPUTS=[
("51318.pub",88576,"728811c92dff5694520e56b6c020533b29d5295d"),
("60685.pub",119296,"37d3dce70e1786e948edd5592527f90be1fae2ff"),
("LinkAt10And20And30And40.pub",64512,"d19ddc46a34afc5c89f90873283a0bbe501ca39d"),
("Sample2000.pub",61440,"2c6174e5e89235f08a3e5883c785c4951728d855"),
("Sample2_2010.pub",73216,"74f4566056a39ee880c847b5dd4b8234762a9489"),
("Sample3.pub",72192,"4f19bec93d25f3d80501490dd108abef4f09b6cb"),
("Sample4.pub",72192,"445df85f092970c36d4b3003d375331a707d6b3c"),
("Sample98.pub",61440,"8adffda77aefed96e3afda319e2698d43dd478cb"),
("SampleBrochure.pub",161792,"00deec14dc6cff6d8a47b120d6d84e7e20c72166"),
("SampleNewsletter.pub",291840,"94900925af5832c493784f3cb51563f838a64df8"),
]
STEPS=("inspect","read_quill","identity_replace")
REPEATS=3
FIELD_KEYS={"op","repeat","peak_live_new_heap_bytes","allocated_bytes_total",
 "allocation_calls","read_calls","source_read_bytes","source_seeks","elapsed_us"}
RESULT_KEYS={"schema","status","source_sha256","source_bytes",
 "stream_count","stream_bytes","quill_bytes","measurements",
 "output_bytes","logical_streams_equal","native_publisher_acceptance"}

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,url):
        raise ValueError("redirect_not_allowed")

def download(name:str,size:int,blob:str)->bytes:
    url=f"https://raw.githubusercontent.com/apache/poi/{APACHE}/test-data/publisher/{name}"
    request=urllib.request.Request(url,headers={"User-Agent":"SK1-T983-CFB-Memory-Research/1"})
    opener=urllib.request.build_opener(NoRedirect)
    with opener.open(request,timeout=18) as response:
        if response.status!=200:
            raise ValueError("http_non_200")
        raw=response.read(size+1)
    if len(raw)!=size:
        raise ValueError("source_size_drift")
    git=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    if git!=blob:raise ValueError("source_git_blob_sha_drift")
    return raw

def one(row:tuple,probe:Path)->dict:
    name,size,blob=row
    record={"fixture":name,"git_blob_sha1":blob,"expected_bytes":size,
        "source_sha256":None,"status":"NOT_EVALUATED","reason":"NOT_STARTED",
        "probe":None}
    try:
        raw=download(name,size,blob)
    except (OSError,ValueError,urllib.error.URLError) as exc:
        tag=(str(exc).split("(")[0] if isinstance(exc,ValueError) else "source_unavailable")
        record["reason"]=tag if tag in {"redirect_not_allowed","http_non_200",
            "source_size_drift","source_git_blob_sha_drift"} else "source_unavailable"
        return record
    record["source_sha256"]=hashlib.sha256(raw).hexdigest()
    record["status"]="SHA_VERIFIED";record["reason"]="OK"
    with tempfile.TemporaryDirectory(prefix="sk1-t983-") as temp:
        base=Path(temp)
        path=base/"original.pub";receipt=base/"safe_receipt.json"
        path.write_bytes(raw)
        try:
            proc=subprocess.run([str(probe),str(path),record["source_sha256"],str(receipt)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180,check=False)
        except (OSError,subprocess.TimeoutExpired):
            record["status"]="PROBE_UNAVAILABLE";record["reason"]="PROCESS_OR_TIMEOUT"
            return record
        if proc.returncode!=0 or not receipt.is_file():
            record["status"]="PROBE_UNAVAILABLE";record["reason"]="PROCESS_FAILED"
            return record
        try:
            result=json.loads(receipt.read_text(encoding="utf-8"))
            if not isinstance(result,dict) or set(result)!=RESULT_KEYS:
                raise ValueError("invalid_result_schema")
            if (result.get("schema")!="sk1.pub-t-983.file.v1"
                or result.get("status") not in {"EVALUATED","NO_QUILL"}
                or result.get("source_sha256")!=record["source_sha256"]
                or result.get("source_bytes")!=size
                or result.get("native_publisher_acceptance")!="NOT_EVALUATED"):
                raise ValueError("invalid_result_header")
            if result["status"]=="EVALUATED":
                if (result.get("logical_streams_equal") is not True
                    or type(result.get("quill_bytes")) is not int
                    or result["quill_bytes"]<=0
                    or len(result.get("measurements",[]))!=9):
                    raise ValueError("invalid_measurement_body")
                for m in result["measurements"]:
                    if not isinstance(m,dict) or set(m)!=FIELD_KEYS:
                        raise ValueError("unsafe_metric_fields")
                expected={(op,i) for op in STEPS for i in range(REPEATS)}
                if {(m["op"],m["repeat"]) for m in result["measurements"]}!=expected:
                    raise ValueError("incomplete_trials")
            elif result.get("measurements")!=[]:
                raise ValueError("nonquill_measurements")
            record["probe"]=result
            record["status"]="EVALUATED" if result["status"]=="EVALUATED" else "NO_QUILL"
        except (KeyError,TypeError,ValueError):
            record["status"]="PROBE_UNAVAILABLE";record["reason"]="BAD_RECEIPT"
    return record

def median(nums:list[int])->int:
    nums=sorted(nums)
    return nums[len(nums)//2]

def summarize(rows:list[dict])->dict:
    status=Counter(r["status"] for r in rows)
    per_operation={}
    for op in STEPS:
        peaks=[];alloc=[];read_bytes=[];io_calls=[];durations=[]
        source_ratios=[]
        for row in rows:
            if row["status"]!="EVALUATED":continue
            m=[x for x in row["probe"]["measurements"] if x["op"]==op]
            p=median([x["peak_live_new_heap_bytes"] for x in m])
            a=median([x["allocated_bytes_total"] for x in m])
            rd=median([x["source_read_bytes"] for x in m])
            calls=median([x["read_calls"] for x in m])
            micros=median([x["elapsed_us"] for x in m])
            peaks.append(p);alloc.append(a);read_bytes.append(rd)
            io_calls.append(calls);durations.append(micros)
            source_ratios.append(round(p/row["expected_bytes"],4))
        per_operation[op]={
            "samples":len(peaks),
            "median_peak_bytes":median(peaks) if peaks else 0,
            "max_peak_bytes":max(peaks) if peaks else 0,
            "median_allocated_bytes":median(alloc) if alloc else 0,
            "median_read_bytes":median(read_bytes) if peaks else 0,
            "median_read_calls":median(io_calls) if io_calls else 0,
            "median_elapsed_us":median(durations) if durations else 0,
            "median_peak_over_pub":median([int(x*10000) for x in source_ratios])/10000 if source_ratios else 0,
            "max_peak_over_pub":max(source_ratios) if source_ratios else 0
        }
    return {
        "attempted":len(rows),"sha_verified":sum(r["source_sha256"] is not None for r in rows),
        "evaluated":status["EVALUATED"],"status_counts":dict(sorted(status.items())),
        "logical_stream_identity_success":sum(
           r["probe"]["logical_streams_equal"] is True for r in rows if r["status"]=="EVALUATED"),
        "per_operation":per_operation
    }

def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--rar2",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    binary=(args.rar2.resolve()/"tools/native-pub-candidate-cli/target/release/examples/"
        "sk1_pub_t_983_profile")
    if not binary.is_file():parser.error("pinned pub_cfb profiler binary not found")
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    plan={"schema":"sk1.pub-t-983.plan.v1","apache_pin":APACHE,"rar2_pin":RAR2,
      "inputs":[{"fixture":n,"expected_bytes":s,"git_blob_sha1":h} for n,s,h in INPUTS],
      "ops":list(STEPS),"repeats":REPEATS,"measurement_unit":"new_live_allocations_during_single_call",
      "publication":"source_safe_statistics_only","native_publisher_acceptance":"NOT_EVALUATED"}
    (out/"plan.json").write_text(json.dumps(plan,indent=2)+"\n",encoding="utf-8")
    rows=[]
    for row in INPUTS:
        rows.append(one(row,binary))
        (out/"records.json").write_text(json.dumps(rows,indent=2)+"\n",encoding="utf-8")
    report={"schema":"sk1.pub-t-983.report.v1","apache_pin":APACHE,"rar2_pin":RAR2,
      "native_publisher_acceptance":"NOT_EVALUATED","source_pub_export_allowed":False,
      "summary":summarize(rows),"records":rows}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    s=report["summary"]
    print(json.dumps({"attempted":s["attempted"],"sha_verified":s["sha_verified"],
      "evaluated":s["evaluated"],"logical_stream_identity_success":s["logical_stream_identity_success"],
      "median_peak_over_pub":{k:v["median_peak_over_pub"] for k,v in s["per_operation"].items()}},sort_keys=True))
    return 0 if s["evaluated"]>=8 and s["logical_stream_identity_success"]==s["evaluated"] else 2

if __name__=="__main__":raise SystemExit(main())
