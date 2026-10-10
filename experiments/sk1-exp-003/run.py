#!/usr/bin/env python3
"""SK1-EXP-003: matched insertion/deletion on EXACT EXP-002 source and offsets.

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
SOURCE_SAFE_SCHEMA = "sk1.same-offset-growth.v1"


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
        with tempfile.TemporaryDirectory(prefix="sk1-exp003-pub-") as tempdir:
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
    controls = {slot: Counter() for slot in ("first", "second", "middle")}
    per_slot = {slot: {"delete_one": Counter(), "insert_one": Counter()}
                for slot in ("first", "second", "middle")}
    pairs = {slot: Counter() for slot in ("first", "second", "middle")}
    discordances = []
    n_story = n_positions = n_attempts = 0
    unavailable = 0
    for row in rows:
        if row["status"] != "EVALUATED":
            unavailable += 1
            continue
        for story in row.get("stories", []):
            n_story += 1
            attempts = story["attempts"]
            if len(attempts) % 2:
                raise ValueError("unpaired arms in Story")
            for i in range(0, len(attempts), 2):
                delete_arm, insert_arm = attempts[i:i+2]
                slot = delete_arm["slot"]
                if slot not in pairs or delete_arm["operation"] != "delete_one" or insert_arm["operation"] != "insert_one" or insert_arm["slot"] != slot:
                    raise ValueError("pair names/order drift")
                if (delete_arm["offset_utf16"] != insert_arm["offset_utf16"] or
                    delete_arm["ascii_rank"] != insert_arm["ascii_rank"]):
                    raise ValueError("pair positions drift")
                n_positions += 1
                n_attempts += 2
                da, ia = categorized(delete_arm), categorized(insert_arm)
                per_slot[slot]["delete_one"][da] += 1
                per_slot[slot]["insert_one"][ia] += 1
                controls[slot][da] += 1
                paired = ("both_pass" if da == ia == "HOSTED_PASS" else
                          "delete_only" if da == "HOSTED_PASS" else
                          "insert_only" if ia == "HOSTED_PASS" else "both_fail")
                pairs[slot][paired] += 1
                if da != ia:
                    discordances.append({
                        "source_sha256": row["source_sha256"],
                        "story_ordinal": story["story_ordinal"],
                        "slot": slot,
                        "offset_utf16": delete_arm["offset_utf16"],
                        "delete_outcome": da,
                        "insert_outcome": ia,
                    })
    return {
        "source_count": len(rows), "evaluated_sources": len(rows) - unavailable,
        "not_evaluated_sources": unavailable,
        "story_cases": n_story,
        "matched_positions": n_positions,
        "arm_attempts": n_attempts,
        "deletion_control": {k: dict(sorted(v.items())) for k,v in controls.items()},
        "outcomes_by_slot_and_arm": {
            k: {arm: dict(sorted(counter.items())) for arm,counter in v.items()}
            for k,v in per_slot.items()},
        "matched_pair_outcomes": {k:dict(sorted(v.items())) for k,v in pairs.items()},
        "discordant_witnesses": discordances
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rar2", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = args.rar2.resolve(strict=True)
    binary = root / "tools/native-pub-candidate-cli/target/release/examples/sk1_exp_003_same_offset"
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
        "schema": "sk1.exp003.plan.v1", "upstream_commit": UPSTREAM,
        "source_manifest": common.MANIFEST_URL,
        "source_count": len(sources),
        "source_sha256": [x["sha256"] for x in sources],
        "slot_plan": ["first", "second", "middle"],
        "operation_arms": ["delete_one", "insert_one"],
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
        "schema": "sk1.exp003.report.v1",
        "upstream_commit": UPSTREAM,
        "source_manifest": common.MANIFEST_URL,
        "native_publisher_acceptance": "NOT_EVALUATED",
        "product_pub_download_authorized": False,
        "summary": summary,
        "records": rows
    }
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    expected = {
        "first": {"HOSTED_PASS": 11, "quill_edit_touches_fd_boundary": 53, "quill_token_layer": 1},
        "second": {"HOSTED_PASS": 64, "quill_token_layer": 1},
        "middle": {"HOSTED_PASS": 63, "quill_token_layer": 1},
    }
    expected_denominators = {"first": 65, "second": 65, "middle": 64}
    if (summary["evaluated_sources"] != SOURCE_COUNT or summary["story_cases"] != 65
        or summary["matched_positions"] != sum(expected_denominators.values())
        or summary["deletion_control"] != expected):
        print(json.dumps({
            "result": "INCOMPLETE_OR_BASELINE_DRIFT",
            "evaluated_sources": summary["evaluated_sources"],
            "story_cases": summary["story_cases"],
            "matched_positions": summary["matched_positions"],
            "deletion_control": summary["deletion_control"]
        }, sort_keys=True))
        return 2
    print(json.dumps({
        "result": "EXPERIMENT_COMPLETED",
        "evaluated_sources": summary["evaluated_sources"],
        "story_cases": summary["story_cases"],
        "matched_positions": summary["matched_positions"],
        "arm_attempts": summary["arm_attempts"],
        "matched_pair_outcomes": summary["matched_pair_outcomes"],
        "insertion_outcomes": {k:v["insert_one"] for k,v in summary["outcomes_by_slot_and_arm"].items()}
    }, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
