#!/usr/bin/env python3
"""Strict acceptance of execution, never a predicted semantic outcome."""
import json
import sys
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text())
assert r["schema"]=="sk1-quill-exp-pub-t-996.v1"
assert r["task_id"]=="PUB-T-996" and r["native_publisher"]=="NOT_EVALUATED"
assert r["parent_science_source_commit"]=="87a6733516ad6ffd1b6b97a3176f359bfeb60ca1"
assert r["poi_commit"]=="ae62bb5116b9aee19ebd5834e3a82066132c9f7f"
pin={"60685":("37d3dce70e1786e948edd5592527f90be1fae2ff",119296,10),
     "51318":("728811c92dff5694520e56b6c020533b29d5295d",88576,4)}
assert set(r["samples"])==set(pin)
for name,s in r["samples"].items():
    blob,size,n=pin[name]
    assert (s["git_blob_sha1"],s["input_size"])==(blob,size)
    assert s["status"]=="EXECUTED",f"{name}: {s.get('error_class')}"
    assert s["physical_controls"]["known_property_records"]==n
    assert s["baseline_stable"] and s["text_control_detected"]
    assert s["nonempty_import"] and s["broken_magic_rejected"]
    assert s["interpretation_eligible"]
    assert s["conclusion"] in ("DETECTED_KNOWN_STYLE_CHANGE","KNOWN_STYLE_CHANGE_NOT_DETECTED")
    c=s["cases"]
    assert c["baseline_one"]["input_changed_bytes"]==0
    assert c["baseline_two"]["input_changed_bytes"]==0
    assert not c["broken_magic"]["imported"]
    expected={"60685":{"spaceafter_first_plus_1pt","spaceafter_all_plus_1pt",
                         "spaceafter_all_zero"},
              "51318":{"alignment_first_low_left","alignment_all_low_left",
                        "alignment_all_high_zero"}}[name]
    assert set(s["known_field_results"])==expected
    for case in expected:
       assert c[case]["input_changed_bytes"]>0
       assert s["known_field_results"][case] in (
           "SAME_PROJECTION","DIFFERENT_PROJECTION","FAILED_IMPORT")
    assert c["text_positive"]["input_changed_bytes"]>0
print("SK1 T996 source-safe known-style-control report PASS; Publisher not evaluated")
