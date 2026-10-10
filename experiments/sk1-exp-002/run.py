#!/usr/bin/env python3
"""SK1-EXP-002: controlled position contrast on the EXACT EXP-001 public sources.

Uses EXP-001's locked source-acquisition and SHA/URL gates, not another crawler.
Outputs source-safe metrics, never source/candidate PUB or text.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

BASE = Path(__file__).resolve().parents[1]
SHARED = BASE / "sk1-exp-001" / "run.py"
SPEC = importlib.util.spec_from_file_location("sk1_exp_001_source_gate", SHARED)
assert SPEC and SPEC.loader
common = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(common)

UPSTREAM = "703808408fd919e564a90cdc236e81db3c04af8b"
SOURCE_COUNT = 26
EXPECTED_FIRST = {"HOSTED_PASS": 11, "quill_edit_touches_fd_boundary": 53, "quill_token_layer": 1}
SOURCE_SAFE_SCHEMA = "sk1.fd-position-sweep.v1"


def process(row: dict, binary: Path) -> dict:
    receipt = {
        "source_sha256": row["sha256"], "source_type": row["source_type"],
        "source_bytes": row["size"], "status": "NOT_EVALUATED", "result": "NOT_STARTED"
    }
    try:
        raw = common.retrieve(row["url"], min(row["size"] + 1, common.MAX_FILE_BYTES))
        if len(raw) != row["size"] or common.digest(raw) != row["sha256"]:
            receipt["result"] = "SHA_OR_SIZE_MISMATCH"
            return receipt
        if not raw.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            receipt["result"] = "CFB_MAGIC_MISSING"
            return receipt
        with tempfile.TemporaryDirectory(prefix="sk1-exp002-pub-") as tempdir:
            source = Path(tempdir) / "source.pub"
            destination = Path(tempdir) / "observation.json"
            source.write_bytes(raw)
            proc = subprocess.run(
                [str(binary), str(source), row["sha256"], str(destination), "3"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False, timeout=300,
            )
            if proc.returncode != 0 or not destination.is_file():
                receipt["result"] = "PROBE_PROCESS_FAILED"
                # Never print stdout/stderr: these may carry untrusted source bytes.
                return receipt
            result = json.loads(destination.read_text(encoding="utf-8"))
        if (result.get("source_sha256") != row["sha256"]
            or result.get("schema") != SOURCE_SAFE_SCHEMA
            or result.get("publisher_native_acceptance") != "NOT_EVALUATED"
            or result.get("product_pub_download_authorized") is not False):
            receipt["result"] = "MALFORMED_PROBE_RECEIPT"
            return receipt
        receipt.update({
            "status": "EVALUATED",
            "result": result["result"],
            "source_story_count": result.get("source_story_count", 0),
            "eligible_story_attempts": result.get("eligible_story_attempts", 0),
            "stories": result.get("stories", []),
        })
    except Exception as exc:
        receipt["result"] = type(exc).__name__.upper()
    return receipt


def categorized(a: dict) -> str:
    return a.get("writer_blocker_code", "writer_blocked_unknown") if a["result"] == "writer_blocked" else a["result"]


def summarize(rows: list[dict]) -> dict:
    slots: dict[str, Counter] = defaultdict(Counter)
    first_counter = Counter()
    blocker_codes = Counter()
    story_cases = 0
    attempted = 0
    partial_source_count = 0
    first_fd_recoveries = 0
    first_failed_any_later_pass = 0
    first_pass_then_later_blocked = 0
    witnesses = []
    for row in rows:
        if row["status"] != "EVALUATED":
            partial_source_count += 1
            continue
        for story in row.get("stories", []):
            story_cases += 1
            atts = story.get("attempts", [])
            if not atts or atts[0]["slot"] != "first":
                raise ValueError("missing first-position control")
            first = categorized(atts[0])
            first_counter[first] += 1
            other = [a for a in atts[1:] if a["result"] == "HOSTED_PASS"]
            attempted += len(atts)
            for a in atts:
                slots[a["slot"]][categorized(a)] += 1
                if a["result"] == "writer_blocked":
                    blocker_codes[a.get("writer_blocker_code", "unknown")] += 1
            if first != "HOSTED_PASS" and other:
                first_failed_any_later_pass += 1
                if first == "quill_edit_touches_fd_boundary":
                    first_fd_recoveries += 1
                witnesses.append({
                    "source_sha256": row["source_sha256"],
                    "story_ordinal": story["story_ordinal"],
                    "first_result": first,
                    "new_pass_slots": [a["slot"] for a in other],
                    "new_pass_offsets_utf16": [a["offset_utf16"] for a in other]
                })
            if first == "HOSTED_PASS" and any(a["result"] != "HOSTED_PASS" for a in atts[1:]):
                first_pass_then_later_blocked += 1
    return {
        "corpus_count": len(rows),
        "evaluated_sources": len(rows) - partial_source_count,
        "not_evaluated_sources": partial_source_count,
        "story_cases": story_cases,
        "attempted_deletions": attempted,
        "first_control": dict(sorted(first_counter.items())),
        "by_slot": {k: dict(sorted(v.items())) for k, v in sorted(slots.items())},
        "writer_blocker_codes_all_positions": dict(sorted(blocker_codes.items())),
        "first_fd_boundary_recovered_by_nonfirst_position": first_fd_recoveries,
        "first_any_failure_recovered_by_nonfirst_position": first_failed_any_later_pass,
        "first_pass_then_later_not_pass_all": first_pass_then_later_blocked,
        "recoverable_story_witnesses": witnesses,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rar2", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = args.rar2.resolve(strict=True)
    binary = root / "tools/native-pub-candidate-cli/target/release/examples/sk1_exp_002_fd_sweep"
    if not binary.is_file():
        ap.error("experiment-specific binary not built")
    raw = common.load_manifest(None)
    sources = common.candidates(raw)
    if len(sources) != SOURCE_COUNT:
        raise ValueError("manifest/allowlist drift: expected exactly 26 distinct SHA sources")
    if sum(s["size"] for s in sources) > common.MAX_TOTAL_BYTES:
        raise ValueError("selected sources exceed the stated total byte budget")

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema": "sk1.exp002.plan.v1", "upstream_commit": UPSTREAM,
        "source_manifest": common.MANIFEST_URL,
        "source_count": len(sources),
        "source_sha256": [x["sha256"] for x in sources],
        "slot_plan": ["first", "second", "q25", "middle", "q75", "last"],
        "max_stories_per_source": 3,
        "scope": "hosted Writer/Reader and EditorProject only",
    }
    (out / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    rows = []
    for row in sources:
        rows.append(process(row, binary))
        (out / "records.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    summary = summarize(rows)
    report = {
        "schema": "sk1.exp002.report.v1",
        "upstream_commit": UPSTREAM,
        "source_manifest": common.MANIFEST_URL,
        "native_publisher_acceptance": "NOT_EVALUATED",
        "product_pub_download_authorized": False,
        "summary": summary,
        "records": rows
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if summary["evaluated_sources"] != SOURCE_COUNT or summary["first_control"] != EXPECTED_FIRST:
        print(json.dumps({
            "result": "INCOMPLETE_OR_BASELINE_DRIFT",
            "source_count": summary["corpus_count"],
            "evaluated_sources": summary["evaluated_sources"],
            "story_cases": summary["story_cases"],
            "first_control": summary["first_control"]
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "result": "EXPERIMENT_COMPLETED",
        "evaluated_sources": summary["evaluated_sources"],
        "story_cases": summary["story_cases"],
        "attempted_deletions": summary["attempted_deletions"],
        "first_fd_boundary_recovered_by_nonfirst_position": summary["first_fd_boundary_recovered_by_nonfirst_position"],
        "by_slot": summary["by_slot"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
