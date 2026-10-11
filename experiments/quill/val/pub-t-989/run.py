#!/usr/bin/env python3
"""One-shot source-safe Rust Writer check. Never collects PUB/Quill bytes."""
import argparse
import json
import re
import subprocess
from pathlib import Path

TASK = "PUB-T-989"
SOURCE = "22a322ed10d9fe8a4ade45acf83bebd0442b691b"
WRITER_BLOB = "b33aaf4d261a98efb7d9d487ed73852cbd0ec168"
FIXTURE_BLOB = "1584a0df824a560a2e7f45e375a71fd312562aba"
WRITER = "vendor/producer-a/crates/pub-quill/src/writer.rs"
FIXTURE = "vendor/producer-a/crates/pub-quill/tests/fixtures/Sample3.pub.b64"
MARKER = "    #[test]\n    fn apache_poi_sample3_to_sample4_matches_owned_structural_projection() {"
NAME = "apache_poi_sample3_opaque_stsh_and_font_survive_story_shrink"


def run_cmd(args, cwd):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--rar2", required=True)
    p.add_argument("--out", required=True)
    a = p.parse_args()
    source = Path(a.rar2).resolve()
    out = Path(a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    plan = {
        "schema": "sk1-quill-val-pub-t-989-plan/v1",
        "task_id": TASK,
        "source_repository": "Lalalalendia/rar2",
        "source_commit": SOURCE,
        "writer_git_blob_sha1": WRITER_BLOB,
        "sample3_git_blob_sha1": FIXTURE_BLOB,
        "test_name": NAME,
        "tested_arms": ["original", "mutated_two_opaque_bytes"],
        "publisher_native": "NOT_EVALUATED",
        "privacy": "no_raw_pub_quill_or_story_export",
    }
    (out / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    result = {
        "schema": "sk1-quill-val-pub-t-989-result/v1",
        "task_id": TASK,
        "source_commit": SOURCE,
        "writer_git_blob_sha1": WRITER_BLOB,
        "sample3_git_blob_sha1": FIXTURE_BLOB,
        "test_name": NAME,
        "rust_test_status": "NOT_EVALUATED",
        "publisher_native": "NOT_EVALUATED",
        "source_repo_modified_persistently": False,
        "expected_opaque_payload_comparisons": 8,
    }
    report = out / "report.json"
    def finish(code, label):
        result["stage"] = label
        report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("SK1 PUB-T-989 stage=" + label + " rust_test_status=" + result["rust_test_status"])
        return code

    if run_cmd(["git", "rev-parse", "HEAD"], source).stdout.strip() != SOURCE:
        return finish(1, "source_commit_mismatch")
    for path, expected in [(WRITER, WRITER_BLOB), (FIXTURE, FIXTURE_BLOB)]:
        probe = run_cmd(["git", "hash-object", path], source)
        if probe.returncode != 0 or probe.stdout.strip() != expected:
            return finish(1, "source_blob_mismatch")
    target = source / WRITER
    original = target.read_text(encoding="utf-8")
    if original.count(MARKER) != 1 or NAME in original:
        return finish(1, "injection_precondition_failed")
    snippet = (Path(__file__).parent / "opaque_test.rs").read_text(encoding="utf-8")
    if snippet.count("fn " + NAME + "()") != 1:
        return finish(1, "injection_test_identity_failed")
    target.write_text(original.replace(MARKER, snippet + MARKER), encoding="utf-8")
    changed = run_cmd(["git", "diff", "--name-only"], source).stdout.strip().splitlines()
    if changed != [WRITER]:
        return finish(1, "unexpected_checkout_modification")
    result["source_injection_verified"] = True

    command = [
        "cargo", "test", "--manifest-path",
        str(source / "vendor/producer-a/Cargo.toml"),
        "-p", "pub-quill", NAME, "--", "--nocapture"
    ]
    try:
        proc = subprocess.run(
            command, cwd=source, capture_output=True, text=True,
            errors="replace", timeout=2400, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return finish(1, "cargo_missing_or_timeout")

    result["cargo_exit_code"] = proc.returncode
    output = proc.stdout + "\n" + proc.stderr
    # Safe classifier: do not print Cargo output or private source snippets.
    result["cargo_diagnostics"] = {
        "rustc_error_codes": sorted(set(re.findall(r"error\[E([0-9]{4})\]", output))),
        "missing_target": bool(re.search(r"no test target|no package named", output, re.I)),
        "missing_dependency": bool(re.search(r"failed to (download|get|load|select)|network failure|lock file.*needs to be updated", output, re.I)),
        "rustc_compile_failure": bool(re.search(r"could not compile|error: aborting", output, re.I)),
        "test_panicked": "FAILED" in output and "panicked" in output,
        "cargo_has_lockfile": (source / "vendor/producer-a/Cargo.lock").is_file(),
        "output_line_count": len(output.splitlines()),
    }
    count = len(re.findall(r"test [^\n]*" + re.escape(NAME) + r" \.\.\. ok", output))
    summary = bool(re.search(
        r"test result: ok\.\s+1 passed;\s+0 failed;", output
    ))
    result["passing_named_test_lines"] = count
    result["one_test_pass_summary"] = summary
    if proc.returncode == 0 and count == 1 and summary:
        result["rust_test_status"] = "PASS"
        result["stsh_chunks"] = 3
        result["font_chunks"] = 1
        result["source_arms"] = 2
        result["opaque_payload_comparisons_pass"] = 8
        return finish(0, "real_rust_completed")

    # Never print raw cargo/panic output or byte arrays to public Actions logs.
    result["rust_test_status"] = "FAIL" if proc.returncode else "NOT_EVALUATED"
    return finish(1, "real_rust_failed_or_unverified")


if __name__ == "__main__":
    raise SystemExit(main())
