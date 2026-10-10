#!/usr/bin/env python3
"""SK1-EXP-004: inspect pinned public sources, correlate structural envelope to
EXP-003 authenticated source-level blocker witnesses. No PUB or Story bytes in output.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

SOURCE_GATE = Path(__file__).resolve().parents[1] / "sk1-exp-001" / "run.py"
spec = importlib.util.spec_from_file_location("sk1_approved_legacy_source_gate", SOURCE_GATE)
assert spec and spec.loader
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)

RAR2_PIN = "703808408fd919e564a90cdc236e81db3c04af8b"
# EXACT source SHA labels derived from independently verified
# EXP-003 GitHub Actions artifact 11679124237, sha256:d8c02e32...
# These identify 10 sources with at least one non-FD insertion attempt blocked
# by quill_growth_would_discard_unknown. They are not raw PUB content.
GROWTH_BLOCKED = frozenset((
    "16ea75ba3cba286af382619a9edc2d7940d3e4f74a83577520b470c9fbc2852d",
    "e2eb919082535195ec24651305aec687d9e891ef7658b379deb94ec7c3b17190",
    "c19fb45f346d671fa9746a1ac6e5fa083a72b184adfa617a565d8e14b4151ebd",
    "03abbe9703be14805df1bde2fdf30688a5971153134d16b428d1943022a15178",
    "9271c1e5e57fa885d953a9d4cee5a4ccb5e10ac9a93c0a5aa7027683b6cece77",
    "fa901f49124264ab5cca37ec98deb07ef83b13ffc91666af719cce0c0f73f186",
    "f2990235617259921c959ddff24dc30ca438ed44dc0126b57e6943fa4b6e7dcc",
    "1a6e4aa289ff277267be9db81763ccc859da4288aed31c6de85ee7f77fdee41a",
    "c13eb49efa38041a767d326cd231160457c4c13c3bf252c6dc167cd57f07b4bb",
    "96e54c5e7a4ff57042fb6ec2f91526713b98fe6f34a66bff2e10839492a2a424",
))
# These 3 sources had no evaluable ordinary Story in EXP-003. We deliberately
# exclude them from confusion-matrix denominators, even if Quill parses.
NO_EDIT_LABEL = frozenset((
    "2b1a2c5183d2fa83fdf9b0e0bf386bc0861b034e08f00fb3fc4171857c097576",
    "990cf478aed51a6e7fdd63556bf7402699d6a3eb1fdabaf8b18a621353878a46",
    "78ef44d22b5b1aa2cc031d03a039ab6ff7c472b8dad2869c32dd1aee7d7667bb",
))
CHECKED_CORPUS_SIZE = 26
RESEARCH_LABEL_URL = (
    "https://github.com/calex794/sk1/actions/runs/38078248161/artifacts/11679124237"
)
BINARY_NAME = "sk1_exp_004_anchor_census"
ALLOWED_OUTCOMES = {
    "INSPECTED", "QUILL_STREAM_MISSING_OR_BROKEN",
    "QUILL_STORY_CATALOG_UNPARSEABLE", "TEXT_DESCRIPTOR_NON_UNIQUE",
    "ALIGNED_SERVICE_ANCHOR_MISSING", "STRUCTURAL_RANGE_INVALID"
}


def inspect_source(row: dict, binary: Path) -> dict:
    result = {
        "source_sha256": row["sha256"], "source_type": row["source_type"],
        "expected_exp003_label": ("GROWTH_BLOCKED" if row["sha256"] in GROWTH_BLOCKED else
                                 "NO_ELIGIBLE_STORY" if row["sha256"] in NO_EDIT_LABEL else
                                 "GROWTH_ALLOWED_AT_SECOND"),
        "status": "NOT_EVALUATED",
        "reason": "NOT_STARTED",
    }
    try:
        data = common.retrieve(row["url"], min(row["size"]+1, common.MAX_FILE_BYTES))
        if len(data) != row["size"] or common.digest(data) != row["sha256"]:
            result["reason"] = "SOURCE_SHA_OR_SIZE_DRIFT"
            return result
        if not data.startswith(bytes.fromhex("d0cf11e0a1b11ae1")):
            result["reason"] = "NOT_CFB"
            return result
        with tempfile.TemporaryDirectory(prefix="sk1-exp004-") as d:
            inp = Path(d) / "source.pub"
            out = Path(d) / "safe.json"
            inp.write_bytes(data)
            proc = subprocess.run(
                [str(binary), str(inp), row["sha256"], str(out)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=120, check=False,
            )
            if proc.returncode != 0 or not out.is_file():
                result["reason"] = "INSPECTOR_FAILED"
                # stderr or raw exception text could reveal Story contents.
                return result
            structure = json.loads(out.read_text(encoding="utf-8"))
        if (structure.get("schema") != "sk1.exp004.quill-anchor-envelope.v1"
            or structure.get("source_sha256") != row["sha256"]
            or structure.get("source_bytes") != row["size"]
            or structure.get("scope") != "read_only_structural_inspection"
            or structure.get("publisher_save_authorized") is not False
            or structure.get("native_publisher_acceptance") != "NOT_EVALUATED"):
            result["reason"] = "INVALID_SOURCE_SAFE_RECEIPT"
            return result
        if structure.get("outcome") not in ALLOWED_OUTCOMES:
            result["reason"] = "UNKNOWN_STRUCTURAL_CLASS"
            return result
        result["status"] = "EVALUATED"
        result["reason"] = structure["outcome"]
        if structure["outcome"] == "INSPECTED":
            for field in (
                "quill_length","descriptor_count","story_count",
                "text_start","text_end","first_fd_anchor","gap_before_anchor_bytes",
                "tail2_nonzero_count","trailing_zero_bytes",
                "descriptor_payload_overlaps_tail2","tail2_descriptor_tags",
                "descriptor_metadata_inside_move_window","predicted_plus_one_gate"
            ):
                result[field] = structure[field]
    except Exception as exc:
        result["reason"] = type(exc).__name__.upper()
    return result


def summarize(records: list[dict]) -> dict:
    matrix = Counter()
    guard = Counter()
    ownership = defaultdict(Counter)
    descriptive_gap = defaultdict(list)
    for r in records:
        label = r["expected_exp003_label"]
        if r["status"] != "EVALUATED" or r["reason"] != "INSPECTED":
            if label != "NO_ELIGIBLE_STORY":
                matrix["UNRESOLVED_"+label] += 1
            continue
        pred = r["predicted_plus_one_gate"]
        guard[pred] += 1
        ownership[label]["named_payload" if r["descriptor_payload_overlaps_tail2"]
                          else "no_named_payload"] += 1
        ownership[label]["tail_nonzero" if r["tail2_nonzero_count"]
                          else "tail_zero"] += 1
        descriptive_gap[label].append(r["gap_before_anchor_bytes"])
        if label == "NO_ELIGIBLE_STORY":
            continue
        blocked = (label == "GROWTH_BLOCKED")
        predicted = (pred == "NONZERO_UNKNOWN_ANCHOR_TAIL")
        matrix["TP" if blocked and predicted else
               "FN" if blocked else
               "FP" if predicted else "TN"] += 1
    return {
        "corpus_sources": len(records),
        "evaluated_source_count": sum(x["status"] == "EVALUATED" for x in records),
        "inspected_quill_count": sum(x["reason"] == "INSPECTED" for x in records),
        "expected_growth_blocked_sources": len(GROWTH_BLOCKED),
        "expected_no_eligible_sources": len(NO_EDIT_LABEL),
        "confusion_known_eligible_sources": dict(sorted(matrix.items())),
        "static_guard_classes": dict(sorted(guard.items())),
        "tail_ownership_by_prior_label": {
            k:dict(sorted(c.items())) for k,c in sorted(ownership.items())
        },
        "gap_bytes_by_prior_label": {
            k:{"count":len(v),"min":min(v),"max":max(v)}
            for k,v in sorted(descriptive_gap.items())
        }
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--rar2", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    root = args.rar2.resolve(strict=True)
    binary = root / "tools/native-pub-candidate-cli/target/release/examples" / BINARY_NAME
    if not binary.is_file():
        p.error("static inspector not built")
    rows = common.candidates(common.load_manifest(None))
    if len(rows) != CHECKED_CORPUS_SIZE or len(set(x["sha256"] for x in rows)) != CHECKED_CORPUS_SIZE:
        raise RuntimeError("pinned source manifest or intake denominator drifted")
    found = set(x["sha256"] for x in rows)
    if not GROWTH_BLOCKED <= found or not NO_EDIT_LABEL <= found or GROWTH_BLOCKED & NO_EDIT_LABEL:
        raise RuntimeError("EXP-003 evidence label SHA corpus mismatch")
    if sum(row["size"] for row in rows) > common.MAX_TOTAL_BYTES:
        raise RuntimeError("total transfer byte budget exceeded")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema":"sk1.exp004.plan.v1", "rar2_pin": RAR2_PIN,
        "exp003_evidence":RESEARCH_LABEL_URL,
        "source_manifest":common.MANIFEST_URL,
        "source_sha256":[x["sha256"] for x in rows],
        "expected_blocked_source_sha256": sorted(GROWTH_BLOCKED),
        "unevaluable_exp003_sha256": sorted(NO_EDIT_LABEL),
        "read_only":True,
        "interpretation":"static two-byte anchor geometry; NOT a writer acceptance oracle",
    }
    (output/"plan.json").write_text(json.dumps(plan,indent=2)+"\n")
    records = []
    for row in rows:
        records.append(inspect_source(row,binary))
        (output/"records.json").write_text(json.dumps(records,indent=2)+"\n")
    report = {
        "schema":"sk1.exp004.report.v1", "rar2_pin":RAR2_PIN,
        "exp003_evidence":RESEARCH_LABEL_URL,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":False,
        "summary":summarize(records),
        "records":records,
    }
    (output/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    summary = report["summary"]
    # Invariant must hold for evidence to be interpretable; a falsified
    # hypothesis (FP/FN) itself is an acceptable, reportable result.
    if (summary["evaluated_source_count"] != CHECKED_CORPUS_SIZE
        or summary["confusion_known_eligible_sources"].get("UNRESOLVED_GROWTH_BLOCKED",0)):
        print(json.dumps({"research_gate":"INCOMPLETE", "summary":summary},sort_keys=True))
        return 2
    print(json.dumps({"research_gate":"COMPLETE","summary":summary},indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
