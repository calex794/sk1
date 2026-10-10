//! SK1-QUILL-EXP-PUB-T-953: sequence/order experiment using ONLY pinned rar2 Writer.
//! All PUB and Story bytes stay in ephemeral worker memory/directory.
use anyhow::{ensure, Context, Result};
use pub_editor::{EditorSession, Sha256Digest, open_mature_0x2c_editor};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{env, fs, io::{Cursor, Write}};

fn sha256(bytes: &[u8]) -> Sha256Digest {
    let hash = Sha256::digest(bytes);
    let mut out = [0_u8; 32];
    out.copy_from_slice(&hash);
    Sha256Digest::from_bytes(out)
}
fn safe_code(raw: &str) -> &str {
    if raw.len() <= 64 && !raw.is_empty()
        && raw.bytes().all(|b| b.is_ascii_lowercase() || b == b'_') { raw }
    else { "unclassified_writer_guard" }
}
struct Step { receipt: Value, bytes: Option<Vec<u8>> }
fn failed(status: &str) -> Step {
    Step { receipt: json!({"status":status}), bytes:None }
}
fn writer_failed(code: &str) -> Step {
    Step { receipt:json!({"status":"WRITER_BLOCKED", "writer_code":safe_code(code)}), bytes:None }
}

/// Validate a materialized step, from EXACT input candidate, including all
/// non-target Story semantics, SYID provenance, and EditorProject byte replay.
fn step(input: &[u8], syid: u32, before: &str, after: &str) -> Step {
    let input_hash = sha256(input);
    let mut editor = match open_mature_0x2c_editor(input, input_hash) {
        Ok(x) => x, Err(_) => return failed("SOURCE_EDITOR_OPEN_BLOCKED")
    };
    let id = match pub_reader::derive_pub_story_id(&input_hash, syid) {
        Ok(x) => x, Err(_) => return failed("STORY_ID_UNAVAILABLE")
    };
    if !editor.graph().stories.get(&id).is_some_and(|s| s.text == before) {
        return failed("STORY_INPUT_MISMATCH");
    }
    let original_graph = editor.graph().stories.clone();
    if editor.replace_story_text(id, after.to_owned()).is_err() {
        return failed("CANONICAL_EDIT_REJECTED");
    }
    let project = editor.project();
    let candidate = match editor.materialize_mature_0x2c_native_pub_candidate(input) {
        Ok(x) => x, Err(e) => return writer_failed(e.code())
    };
    if candidate.source_hash != input_hash || candidate.output_hash != sha256(&candidate.bytes)
        || candidate.bytes == input {
        return failed("WRITER_HASH_OR_NO_CHANGE");
    }
    let reopened = match open_mature_0x2c_editor(&candidate.bytes, candidate.output_hash) {
        Ok(x) => x, Err(_) => return failed("READER_REOPEN_BLOCKED")
    };
    let expected_id = match pub_reader::derive_pub_story_id(&candidate.output_hash, syid) {
        Ok(x) => x, Err(_) => return failed("OUTPUT_STORY_ID_UNAVAILABLE")
    };
    if candidate.output_story_id != expected_id ||
        !reopened.graph().stories.get(&expected_id).is_some_and(|s| s.text == after) {
        return failed("TARGET_SEMANTIC_MISMATCH");
    }
    let verified_siblings = (|| -> Result<bool> {
        let source_quill = pub_cfb::read_stream_reader(
            Cursor::new(input), pub_reader::QUILL_STREAM_PATH)?;
        let candidate_quill = pub_cfb::read_stream_reader(
            Cursor::new(&candidate.bytes), pub_reader::QUILL_STREAM_PATH)?;
        let source_catalog = pub_quill::parse_confirmed_story_catalog(
            pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &source_quill)?;
        let output_catalog = pub_quill::parse_confirmed_story_catalog(
            pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &candidate_quill)?;
        let mut original_ids: Vec<_> = source_catalog.stories.iter().map(|s| s.syid.0).collect();
        let mut output_ids: Vec<_> = output_catalog.stories.iter().map(|s| s.syid.0).collect();
        original_ids.sort_unstable();
        output_ids.sort_unstable();
        if original_ids != output_ids || original_ids.windows(2).any(|a| a[0] == a[1]) ||
            original_graph.len() != reopened.graph().stories.len() { return Ok(false); }
        let mut matched = 0_usize;
        let mut target_found = false;
        for s in &source_catalog.stories {
            let old_id = pub_reader::derive_pub_story_id(&input_hash, s.syid.0)?;
            let new_id = pub_reader::derive_pub_story_id(&candidate.output_hash, s.syid.0)?;
            let Some(old) = original_graph.get(&old_id) else { continue; };
            matched += 1;
            if s.syid.0 == syid {
                target_found = old_id == id && new_id == expected_id;
            } else if !reopened.graph().stories.get(&new_id)
                .is_some_and(|new| new.text == old.text) {
                return Ok(false);
            }
        }
        Ok(target_found && matched == original_graph.len())
    })();
    if !matches!(verified_siblings, Ok(true)) { return failed("SYID_OR_SIBLING_MISMATCH"); }
    let mut replay = match open_mature_0x2c_editor(input, input_hash) {
        Ok(x) => x, Err(_) => return failed("REPLAY_SOURCE_OPEN_BLOCKED")
    };
    if replay.apply_project(&project).is_err() {
        return failed("PROJECT_REPLAY_BLOCKED");
    }
    let replay_candidate = match replay.materialize_mature_0x2c_native_pub_candidate(input) {
        Ok(x) => x, Err(_) => return failed("PROJECT_REPLAY_WRITER_BLOCKED")
    };
    if replay_candidate.bytes != candidate.bytes || sha256(input) != input_hash {
        return failed("PROJECT_REPLAY_BYTE_MISMATCH");
    }
    Step {
        receipt: json!({"status":"HOSTED_PASS",
            "candidate_sha256":candidate.output_hash.to_string(),
            "reader_semantic_reopen":true,
            "syid_siblings_preserved":true,
            "project_replay_byte_equal":true,
            "source_immutable":true}),
        bytes: Some(candidate.bytes),
    }
}

/// ASCII edit at an exact previous-position UTF-16 offset.
/// Delete a single ASCII alphanumeric; never delete CR or a surrogate.
fn delete_at_utf16(text: &str, offset: usize) -> Result<String> {
    let mut units = 0_usize;
    for (idx, ch) in text.char_indices() {
        if units == offset {
            ensure!(ch.is_ascii_alphanumeric(), "not an ASCII text edit at requested offset");
            let mut out = text.to_owned();
            out.remove(idx);
            return Ok(out);
        }
        units += ch.len_utf16();
    }
    anyhow::bail!("UTF-16 offset missing")
}
fn rank_offset(text: &str, rank: usize) -> Result<usize> {
    let mut seen = 0_usize;
    for (idx, ch) in text.char_indices() {
        if ch.is_ascii_alphanumeric() {
            if seen == rank { return Ok(text[..idx].encode_utf16().count()); }
            seen += 1;
        }
    }
    anyhow::bail!("ASCII rank missing")
}
fn need<'a>(w: &'a Value, key: &str) -> Result<&'a Value> {
    w.get(key).with_context(|| format!("missing {key}"))
}
fn required_number(w: &Value, key: &str) -> Result<usize> {
    usize::try_from(need(w,key)?.as_u64().context("invalid nonnegative number")?)
        .context("usize overflow")
}
fn required_hash(w: &Value, key: &str) -> Result<&str> {
    let s = need(w,key)?.as_str().context("expected string")?;
    ensure!(s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit()),
        "invalid pinned SHA");
    Ok(s)
}
fn probe(source: &[u8], expected_sha: &str, witness: &Value) -> Result<Value> {
    ensure!(sha256(source).to_string() == expected_sha, "input SHA drift");
    ensure!(required_hash(witness,"source_sha256")? == expected_sha,"witness mismatch");
    let source_hash = sha256(source);
    let ordinal = required_number(witness,"story_ordinal")?;
    let story_len = required_number(witness,"story_utf16_len")?;
    let a_rank = required_number(witness,"a_ascii_rank")?;
    let b_rank = required_number(witness,"b_ascii_rank")?;
    let a_offset = required_number(witness,"a_offset_utf16")?;
    let b_offset = required_number(witness,"b_offset_utf16")?;
    let expected_a = required_hash(witness,"expected_a_sha256")?;
    let expected_b = required_hash(witness,"expected_b_sha256")?;
    ensure!(a_offset != b_offset, "overlapping operations");
    let editor = open_mature_0x2c_editor(source, source_hash)?;
    let eligible = editor.graph().stories.iter()
        .filter(|(id, s)| editor.can_replace_story_text(**id).is_ok()
            && s.text.chars().any(|c| c.is_ascii_alphanumeric()))
        .take(3)
        .map(|(id, s)| (*id, s.text.clone()))
        .collect::<Vec<_>>();
    let (story_id, before) = eligible.get(ordinal).context("missing eligible Story")?;
    ensure!(before.encode_utf16().count() == story_len, "Story length drift");
    ensure!(rank_offset(before, a_rank)? == a_offset &&
        rank_offset(before,b_rank)? == b_offset,"position drift");
    let original_quill = pub_cfb::read_stream_reader(
        Cursor::new(source), pub_reader::QUILL_STREAM_PATH)?;
    let catalog = pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &original_quill)?;
    let mut matching = catalog.stories.iter()
        .filter(|s| pub_reader::derive_pub_story_id(&source_hash,s.syid.0)
            .is_ok_and(|id| id == *story_id));
    let syid = matching.next().context("target SYID missing")?.syid.0;
    ensure!(matching.next().is_none(), "nonunique SYID target");
    let after_a = delete_at_utf16(before, a_offset)?;
    let after_b = delete_at_utf16(before, b_offset)?;
    let final_ab = delete_at_utf16(&after_a,
        b_offset - usize::from(a_offset < b_offset))?;
    let final_ba = delete_at_utf16(&after_b,
        a_offset - usize::from(b_offset < a_offset))?;
    ensure!(final_ab == final_ba, "offset remapping changed final semantics");
    let a = step(source,syid,before,&after_a);
    let b = step(source,syid,before,&after_b);
    let a_single_sha = a.receipt["candidate_sha256"].as_str().unwrap_or("");
    let b_single_sha = b.receipt["candidate_sha256"].as_str().unwrap_or("");
    let baseline_match = a.receipt["status"] == "HOSTED_PASS" &&
        b.receipt["status"] == "HOSTED_PASS" &&
        a_single_sha == expected_a && b_single_sha == expected_b;
    let ab = if baseline_match {
        step(a.bytes.as_ref().context("missing A intermediate")?,
            syid,&after_a,&final_ab).receipt
    } else { json!({"status":"NOT_EVALUATED_BASELINE_DRIFT"}) };
    let ba = if baseline_match {
        step(b.bytes.as_ref().context("missing B intermediate")?,
            syid,&after_b,&final_ba).receipt
    } else { json!({"status":"NOT_EVALUATED_BASELINE_DRIFT"}) };
    let both_pass = ab["status"] == "HOSTED_PASS" && ba["status"] == "HOSTED_PASS";
    let byte_equal = if both_pass {
        Some(ab["candidate_sha256"] == ba["candidate_sha256"])
    } else { None };
    ensure!(sha256(source).to_string() == expected_sha, "source mutated");
    Ok(json!({
        "schema":"sk1.quill-exp-pub-t-953.probe.v1",
        "source_sha256":expected_sha,
        "source_bytes":source.len(),
        "story_ordinal":ordinal,
        "story_utf16_len":story_len,
        "a_rank":a_rank,
        "b_rank":b_rank,
        "a_offset_utf16":a_offset,
        "b_offset_utf16":b_offset,
        "ab_second_offset_utf16":b_offset-usize::from(a_offset<b_offset),
        "ba_second_offset_utf16":a_offset-usize::from(b_offset<a_offset),
        "original_immutable":true,
        "expected_a_sha256":expected_a,
        "expected_b_sha256":expected_b,
        "single_a":a.receipt,
        "single_b":b.receipt,
        "singles_baseline_match":baseline_match,
        "ab_second":ab,
        "ba_second":ba,
        "both_sequential_pass":both_pass,
        "same_final_semantic_text_by_construction":true,
        "same_final_pub_bytes":byte_equal,
        "publisher_native_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":false
    }))
}
fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let input = args.next().context("source path")?;
    let source_sha = args.next().context("expected source SHA")?;
    let witness_path = args.next().context("witness JSON")?;
    let output_path = args.next().context("receipt JSON")?;
    ensure!(args.next().is_none(), "unexpected args");
    ensure!(source_sha.len()==64 && source_sha.bytes().all(|b| b.is_ascii_hexdigit()),
        "invalid source SHA");
    let bytes = fs::read(input)?;
    ensure!(bytes.len() <= 12*1024*1024, "size exceeds cap");
    let witness: Value = serde_json::from_slice(&fs::read(witness_path)?)?;
    let report = probe(&bytes,&source_sha,&witness)?;
    let mut file = fs::OpenOptions::new().write(true).create_new(true).open(output_path)?;
    file.write_all(&serde_json::to_vec_pretty(&report)?)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    println!("{}",serde_json::to_string(&json!({
        "source_sha256":source_sha,
        "story_ordinal":report["story_ordinal"],
        "singles_baseline_match":report["singles_baseline_match"],
        "ab_second":report["ab_second"]["status"],
        "ba_second":report["ba_second"]["status"]}))?);
    Ok(())
}
