#!/usr/bin/env python3
"""Produce source-free PUB075 reference previews from existing genuine Publisher PDF 64x64 fingerprints.
DO NOT represent the upscaled previews as high-resolution Publisher renders.
"""
import base64
import hashlib
import json
from pathlib import Path
import sys
import zlib
from PIL import Image

source = Path(sys.argv[1])
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
data = json.loads(source.read_text())
assert data["grid"]["width"] == data["grid"]["height"] == 64
cases = [c for c in data["pairs"] if c["basename"] == "075_082319ac283c99f1"]
assert len(cases) == 1
case = cases[0]
assert case["pub_sha256"] == "082319ac283c99f1b2e5d05fe428bccfd4123ef498267b35b492bba991a3b6e0"
assert len(case["pages"]) == 27
manifest = []
for i, page in enumerate(case["pages"], start=1):
    assert int(page["page"]) == i
    raw = zlib.decompress(base64.b64decode(page["rgb_zlib_base64"]))
    assert len(raw) == 64*64*3
    assert hashlib.sha256(raw).hexdigest() == page["grid_sha256"]
    img = Image.frombytes("RGB", (64,64), raw)
    img.save(out/f"PUB075_Publisher_reference_{i:02d}_64.png")
    img.resize((864,1221), Image.Resampling.NEAREST).save(out/f"PUB075_Publisher_reference_{i:02d}_upscaled.png")
    manifest.append({"page":i,"reference_grid_sha256":page["grid_sha256"],
                     "reference_media_pt":[page["media_width_pt"],page["media_height_pt"]]})
(out/"manifest.json").write_text(json.dumps({"fixture":case["basename"],
    "provenance":"Pre-existing genuine Microsoft Publisher PDF fingerprint, 64x64 RGB",
    "limitations":"Upscaled from 64x64; no missing detail can be recovered, not a Chaptera render.",
    "pages":manifest},indent=2)+"\n")
print("Verified 27 Publisher reference pages, 54 previews")
