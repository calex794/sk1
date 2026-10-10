#!/usr/bin/env python3
"""SK1-EXP-001: public, pinned, disposable Writer experiment driver.

Receipts only; no PUB data or source Story text leaves the worker.
"""
from __future__ import annotations
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request

PINNED_RAR2 = "703808408fd919e564a90cdc236e81db3c04af8b"
MANIFEST_URL = (
    "https://raw.githubusercontent.com/Lalalalendia/rar2/" + PINNED_RAR2
    + "/tools/corpus/receipts/lalamu-materialized-35-input-2026-09-29.json"
)
EXCLUDED = {
    "424c69173ff08948c2529c8084b4ac2403f1ff1057146f4edd02fc29b44481fc", # Sample3
    "42195f7ad23d911219fea3ec88e66e867e9b9a6821a16dd1b535e2aa9d57a11b", # Sample4
    "6fefdef46b87c767150878dc384549cb2d2ec2ac54de25f8ddb3a5628301107e", # Sample
}
ALLOWED_HOSTS = {"raw.githubusercontent.com", "sclera.be", "www.sclera.be"}
MAX_FILE_BYTES = 12 * 1024 * 1024
MAX_TOTAL_BYTES = 120 * 1024 * 1024
TIMEOUT_SECONDS = 45

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

class RestrainedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def validate_url(url: str) -> None:
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https" or (p.hostname or "").lower() not in ALLOWED_HOSTS:
        raise ValueError("URL is outside the explicitly allowed HTTPS hosts")
    if p.username or p.password or p.port not in (None, 443):
        raise ValueError("noncanonical URL credentials/port")
    if p.query or p.fragment:
        raise ValueError("query/fragment not admitted")
    if not p.path.lower().endswith(".pub"):
        raise ValueError("not a direct .pub locator")
    if p.hostname:
        try:
            ipaddress.ip_address(p.hostname)
        except ValueError:
            pass
        else:
            raise ValueError("IP address literal is not allowed")

def retrieve(url: str, limit: int) -> bytes:
    validate_url(url)
    opener = urllib.request.build_opener(RestrainedRedirects())
    request = urllib.request.Request(url, headers={"User-Agent": "sk1-exp-001-research/1.0"})
    with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
        declared = response.headers.get("Content-Length")
        if declared is not None and int(declared) > limit:
            raise ValueError("source exceeds byte limit")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("source exceeds byte limit")
    return data

def load_manifest(source: Path | None) -> dict:
    if source:
        return json.loads(source.read_text(encoding="utf-8"))
    request = urllib.request.Request(MANIFEST_URL, headers={"User-Agent": "sk1-exp-001-research/1.0"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        data = response.read(100_000 + 1)
    if len(data) > 100_000:
        raise ValueError("manifest unreasonably large")
    return json.loads(data)

def candidates(raw: dict) -> list[dict]:
    if raw.get("schema") != "rar2-lalamu-materialized-35-input-v1":
        raise ValueError("unrecognized manifest schema")
    files = raw.get("files")
    if not isinstance(files, list) or len(files) != 35:
        raise ValueError("manifest row count drift")
    seen = set()
    result = []
    for f in files:
        sha = f.get("sha256")
        size = f.get("size")
        url = f.get("source_url")
        if not isinstance(sha, str) or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            raise ValueError("bad manifest SHA")
        if sha in seen:
            raise ValueError("duplicate fixture SHA")
        seen.add(sha)
        if not isinstance(size, int) or size <= 0:
            raise ValueError("bad manifest size")
        if not isinstance(url, str):
            raise ValueError("missing URL")
        if sha in EXCLUDED:
            continue
        if size > MAX_FILE_BYTES:
            continue
        try:
            validate_url(url)
        except ValueError:
            continue
        result.append({"sha256": sha, "size": size, "source_type": f["source_type"], "url": url})
    return result

def process(row: dict, root: Path, max_stories: int) -> dict:
    receipt = {
        "source_sha256": row["sha256"],
        "source_type": row["source_type"],
        "source_bytes": row["size"],
        "status": "NOT_EVALUATED",
        "reason": "NOT_STARTED"
    }
    try:
        raw = retrieve(row["url"], min(row["size"] + 1, MAX_FILE_BYTES))
        if len(raw) != row["size"] or digest(raw) != row["sha256"]:
            receipt["reason"] = "SOURCE_BYTES_OR_SHA_DRIFT"
            return receipt
        if not raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            receipt["reason"] = "NOT_CFB_MAGIC"
            return receipt
        with tempfile.TemporaryDirectory(prefix="sk1-source-") as d:
            inp = Path(d) / "in.pub"
            out = Path(d) / "result.json"
            inp.write_bytes(raw)
            completed = subprocess.run([
                "cargo", "run", "--quiet", "--manifest-path",
                str(root / "tools/native-pub-candidate-cli/Cargo.toml"),
                "--release", "--example", "sk1_exp_001_writer_probe",
                "--", str(inp), row["sha256"], str(out), str(max_stories)
            ], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=240, check=False)
            if completed.returncode or not out.exists():
                receipt["reason"] = "HARNESS_OR_COMPILATION_ERROR"
                # Deliberately omit stderr/stdout (may include untrusted data).
                return receipt
            result = json.loads(out.read_text(encoding="utf-8"))
        if result.get("source_sha256") != row["sha256"] or result.get("schema") != "sk1.writer-hosted-applicability.v1":
            receipt["reason"] = "INVALID_HARNESS_RECEIPT"
            return receipt
        receipt["status"] = "EVALUATED"
        receipt["reason"] = result["result"]
        receipt["source_story_count"] = result.get("source_story_count", 0)
        receipt["eligible_story_attempts"] = result.get("eligible_story_attempts", 0)
        receipt["attempts"] = result.get("attempts", [])
    except Exception as e:
        receipt["reason"] = type(e).__name__.upper()
    return receipt

def summarize(records: list[dict]) -> dict:
    summary = {"source_count": len(records), "evaluated": 0, "not_evaluated": 0, "arms": {}}
    for row in records:
        if row["status"] == "EVALUATED":
            summary["evaluated"] += 1
        else:
            summary["not_evaluated"] += 1
        for attempt in row.get("attempts", []):
            arm = summary["arms"].setdefault(attempt["arm"], {})
            key = attempt["result"]
            arm[key] = arm.get(key, 0) + 1
    return summary

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rar2", type=Path, required=True)
    ap.add_argument("--manifest", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--max-sources", type=int, default=35)
    ap.add_argument("--max-stories", type=int, default=3)
    ap.add_argument("--index-only", action="store_true")
    args = ap.parse_args()
    args.rar2 = args.rar2.resolve(strict=True)  # subprocess cwd changes; manifest must stay absolute
    if not (1 <= args.max_sources <= 35 and 1 <= args.max_stories <= 3):
        ap.error("limits out of bounds")
    raw = load_manifest(args.manifest)
    rows = candidates(raw)[:args.max_sources]
    args.out.mkdir(parents=True, exist_ok=True)
    plan = {"schema": "sk1.exp001.plan.v1", "upstream_commit": PINNED_RAR2,
            "manifest_url": MANIFEST_URL, "selected": [
                {"source_sha256": x["sha256"], "size": x["size"], "source_type": x["source_type"]}
                for x in rows
            ], "candidate_count": len(rows),
            "fence": "hosted Writer/Reader only, not native Publisher compatibility"}
    (args.out / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    if args.index_only:
        print(json.dumps({"selected": len(rows), "index_only": True}))
        return 0
    records = []
    budget = 0
    for row in rows:
        if budget + row["size"] > MAX_TOTAL_BYTES:
            records.append({"source_sha256": row["sha256"], "status": "NOT_EVALUATED", "reason": "TOTAL_BYTE_BUDGET"})
            continue
        budget += row["size"]
        records.append(process(row, args.rar2, args.max_stories))
        # Resume after interrupt; never store source or candidate bytes.
        (args.out / "records.json").write_text(json.dumps(records, indent=2) + "\n")
    report = {"schema": "sk1.exp001.result.v1", "upstream_commit": PINNED_RAR2,
              "corpus_manifest": MANIFEST_URL, "summary": summarize(records), "records": records,
              "native_publisher_acceptance": "NOT_EVALUATED", "product_pub_download_authorized": False}
    (args.out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report["summary"], indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
