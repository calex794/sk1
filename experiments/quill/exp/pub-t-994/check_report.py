#!/usr/bin/env python3
"""Independent, strict status acceptance. SCIENCE result may be non-discriminating."""
import json
import sys
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text())
assert r["schema"]=="sk1-quill-exp-pub-t-994.v1"
assert r["task_id"]=="PUB-T-994" and r["native_publisher"]=="NOT_EVALUATED"
assert r["poi_commit"]=="ae62bb5116b9aee19ebd5834e3a82066132c9f7f"
pins={"60685":("37d3dce70e1786e948edd5592527f90be1fae2ff",119296,1),
      "51318":("728811c92dff5694520e56b6c020533b29d5295d",88576,0x5a)}
assert set(r["samples"])==set(pins)
for name,s in r["samples"].items():
    sha,n,high=pins[name]
    assert (s["git_blob_sha1"],s["input_size"],s["natural_high"])==(sha,n,high)
    assert s["status"]=="EXECUTED",f"{name}: did not complete processing: {s.get('error_class')}"
    assert len(s["input_sha256"])==64
    c=s["cases"]
    assert set(c)=={"baseline_one","baseline_two","id30_first_zero",
        "id30_first_ff","id30_all_zero","header_stsh1_xor",
        "headers_four_xor","text_positive","broken_magic"}
    assert c["baseline_one"]["input_changed_bytes"]==0
    assert c["baseline_two"]["input_changed_bytes"]==0
    assert c["id30_first_zero"]["input_changed_bytes"]==1
    assert c["id30_first_ff"]["input_changed_bytes"]==1
    assert c["header_stsh1_xor"]["input_changed_bytes"]==1
    assert c["headers_four_xor"]["input_changed_bytes"]==4
    assert c["broken_magic"]["input_changed_bytes"]==1
    assert s["negative_control_rejected"],"negative magic must fail"
    assert s["physical_controls"]["natural_nonzero_absent13_records"]>0
    assert s["physical_controls"]["positive_text_changed_bytes"]>0
    assert s["physical_controls"]["paragraph_records"]>0
    assert set(s["mutation_results"])=={"id30_first_zero","id30_first_ff",
        "id30_all_zero","header_stsh1_xor","headers_four_xor"}
    if s["interpretation_eligible"]:
        assert s["baseline_stable"] and s["positive_control_detected"]
        assert s["nonempty_import"]
        assert s["conclusion"]=="INTERPRETABLE"
    else:
        assert s["conclusion"]=="NON_DISCRIMINATING"
print("SK1 PUB-T-994 source-safe report gate PASS; no Microsoft Publisher inference")
