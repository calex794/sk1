//! SK1-EXP-003: matched +/- 1 UTF-16 edits at the SAME Quill Story offset.
//! No new Writer, no source/candidate PUB persistence outside worker temp.
//! Original Writer and EditorProject remain owned by pinned rar2.
use anyhow::{Context, Result, ensure};
use pub_editor::{EditorSession, Sha256Digest, open_mature_0x2c_editor};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{env, fs, io::{Write, Cursor}, collections::HashSet};

fn sha256(bytes: &[u8]) -> Sha256Digest {
    let hash = Sha256::digest(bytes);
    let mut digest = [0_u8; 32];
    digest.copy_from_slice(&hash);
    Sha256Digest::from_bytes(digest)
}

// This checks an actual EditorProject replay as well as the Writer's own Reader
// reopen, and does not conflate either with Microsoft Publisher SaveAs.
fn verify_candidate(
    edited: &EditorSession,
    source: &[u8],
    expected_after: &str,
) -> Result<Value> {
    let source_hash = sha256(source);
    let project = edited.project();
    let candidate = edited
        .materialize_mature_0x2c_native_pub_candidate(source)
        .map_err(|error| anyhow::anyhow!("writer_blocked:{}", error.code()))?;
    ensure!(candidate.source_hash == source_hash, "Writer changed source identity");
    ensure!(candidate.output_hash == sha256(&candidate.bytes), "candidate hash mismatch");
    ensure!(candidate.bytes != source, "candidate did not differ from source");

    let reopened = open_mature_0x2c_editor(&candidate.bytes, candidate.output_hash)
        .context("Editor cannot reopen Writer candidate")?;
    let persisted_text = reopened
        .graph()
        .stories
        .get(&candidate.output_story_id)
        .context("Reader reopened candidate without target Story")?;
    ensure!(persisted_text.text == expected_after, "reopened Story semantic mismatch");

    let mut replay = open_mature_0x2c_editor(source, source_hash)
        .context("fresh Editor cannot reopen immutable original")?;
    replay
        .apply_project(&project)
        .context("EditorProject history replay failed")?;
    let replay_candidate = replay
        .materialize_mature_0x2c_native_pub_candidate(source)
        .map_err(|error| anyhow::anyhow!("replay_writer_blocked:{}", error.code()))?;
    ensure!(replay_candidate.bytes == candidate.bytes, "replayed EditorProject changed candidate bytes");
    ensure!(sha256(source) == source_hash, "immutable source changed");
    Ok(json!({
        "output_sha256": candidate.output_hash.to_string(),
        "output_byte_len": candidate.bytes.len(),
        "reader_semantic_reopen": true,
        "editor_project_replay_byte_equal": true,
        "source_immutable": true
    }))
}

fn safe_error_class(error: &str) -> &'static str {
    if error.starts_with("writer_blocked:") { "writer_blocked" }
    else if error.starts_with("Editor cannot reopen") || error.starts_with("Reader reopened") { "reader_or_editor_reopen_blocked" }
    else if error.starts_with("EditorProject history replay") || error.starts_with("replay_writer_blocked:")
        || error.starts_with("replayed EditorProject") { "project_replay_blocked" }
    else { "bounded_candidate_validation_failed" }
}

fn safe_writer_code(error: &str) -> Option<&str> {
    error.strip_prefix("writer_blocked:")
        .or_else(|| error.strip_prefix("replay_writer_blocked:"))
        .filter(|s| !s.is_empty() && s.len() <= 64
            && s.bytes().all(|b| b.is_ascii_lowercase() || b == b'_'))
}


fn probe(source: &[u8], expected_sha: &str, max_stories: usize) -> Result<Value> {
    let source_hash = sha256(source);
    ensure!(source_hash.to_string() == expected_sha, "source SHA drift");
    let mut report = json!({
        "schema": "sk1.same-offset-growth.v1",
        "source_sha256": expected_sha,
        "source_byte_len": source.len(),
        "result": "NOT_EVALUATED",
        "publisher_native_acceptance": "NOT_EVALUATED",
        "product_pub_download_authorized": false,
        "stories": []
    });
    let editor = match open_mature_0x2c_editor(source, source_hash) {
        Ok(editor) => editor,
        Err(_) => {
            report["result"] = json!("SOURCE_EDITOR_OPEN_BLOCKED");
            return Ok(report);
        }
    };
    let baseline_stories = editor.graph().stories.clone();
    report["source_story_count"] = json!(baseline_stories.len());
    let eligible = baseline_stories.iter()
        .filter(|(id, story)| editor.can_replace_story_text(**id).is_ok()
            && story.text.chars().any(|c| c.is_ascii_alphanumeric()))
        .take(max_stories)
        .map(|(id, story)| (*id, story.text.clone()))
        .collect::<Vec<_>>();
    report["eligible_story_attempts"] = json!(eligible.len());
    if eligible.is_empty() {
        report["result"] = json!("NO_PLAIN_EDITABLE_STORY");
        return Ok(report);
    }
    let mut cases = Vec::new();
    for (ordinal, (id, before)) in eligible.into_iter().enumerate() {
        let letters: Vec<(usize, char)> = before.char_indices()
            .filter(|(_, c)| c.is_ascii_alphanumeric()).collect();
        if letters.is_empty() { continue; }
        let n = letters.len();
        let picks = [
            ("first", 0),
            ("second", 1.min(n - 1)),
            ("middle", (n - 1) / 2),
        ];
        let mut used_bytes = HashSet::new();
        let mut attempts = Vec::new();
        for (slot, ordinal_position) in picks {
            let (byte_offset, ch) = letters[ordinal_position];
            if !used_bytes.insert(byte_offset) { continue; }
            let before_units = before.encode_utf16().count();
            let at_units = before[..byte_offset].encode_utf16().count();
            let prev_is_cr = before[..byte_offset].chars().last() == Some('\r');
            let next_is_cr = before[byte_offset + ch.len_utf8()..].chars().next() == Some('\r');
            // Both arms start from the exact same immutable input. No chained edits.
            for operation in ["delete_one", "insert_one"] {
                let mut after = before.clone();
                if operation == "delete_one" {
                    after.remove(byte_offset);
                } else {
                    // Avoid ambiguous insertion-diff alignment at runs of equal
                    // characters: marker differs from both immediate neighbors.
                    let prev = before[..byte_offset].chars().last();
                    let marker = ['X', 'Q', 'Z'].into_iter()
                        .find(|&c| Some(c) != prev && c != ch)
                        .context("cannot choose unambiguous ASCII marker")?;
                    after.insert(byte_offset, marker);
                }
                let mut item = json!({
                "operation": operation,
                "delta_utf16": if operation == "delete_one" { -1 } else { 1 },
                "before_utf16_units": before_units,
                "after_utf16_units": after.encode_utf16().count(),
                "slot": slot,
                "ascii_rank": ordinal_position,
                "ascii_total": n,
                "offset_utf16": at_units,
                "story_utf16_len": before_units,
                "relative_per_mille": if before_units == 0 { 0 } else { at_units * 1000 / before_units },
                "prev_is_cr": prev_is_cr,
                "next_is_cr": next_is_cr,
                "result": "NOT_EVALUATED"
            });
            let mut edited = open_mature_0x2c_editor(source, source_hash)
                .context("known-openable source unavailable during replay")?;
            if edited.replace_story_text(id, after.clone()).is_err() {
                item["result"] = json!("CANONICAL_EDIT_REJECTED");
                attempts.push(item);
                continue;
            }
            match verify_candidate(&edited, source, &after) {
                Ok(receipt) => {
                    let candidate = edited.materialize_mature_0x2c_native_pub_candidate(source)?;
                    let reopened = open_mature_0x2c_editor(&candidate.bytes, candidate.output_hash)?;
                    // StoryId is salted with the PUB SHA. Map untouched stories by
                    // original Quill SYID; old & new StoryId must differ by source hash.
                    let verified = (|| -> Result<bool> {
                        let source_quill = pub_cfb::read_stream_reader(
                            Cursor::new(source), pub_reader::QUILL_STREAM_PATH)?;
                        let output_quill = pub_cfb::read_stream_reader(
                            Cursor::new(&candidate.bytes), pub_reader::QUILL_STREAM_PATH)?;
                        let source_catalog = pub_quill::parse_confirmed_story_catalog(
                            pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &source_quill)?;
                        let output_catalog = pub_quill::parse_confirmed_story_catalog(
                            pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &output_quill)?;
                        let mut initial = source_catalog.stories.iter().map(|s| s.syid.0).collect::<Vec<_>>();
                        let mut final_ids = output_catalog.stories.iter().map(|s| s.syid.0).collect::<Vec<_>>();
                        initial.sort_unstable();
                        final_ids.sort_unstable();
                        if initial != final_ids || initial.windows(2).any(|a| a[0] == a[1])
                            || reopened.graph().stories.len() != baseline_stories.len() {
                            return Ok(false);
                        }
                        let mut matched = 0;
                        let mut found_target = false;
                        for s in &source_catalog.stories {
                            let old_id = pub_reader::derive_pub_story_id(&source_hash, s.syid.0)?;
                            let new_id = pub_reader::derive_pub_story_id(&candidate.output_hash, s.syid.0)?;
                            let Some(original) = baseline_stories.get(&old_id) else { continue };
                            matched += 1;
                            if old_id == id {
                                found_target = new_id == candidate.output_story_id;
                            } else if !reopened.graph().stories.get(&new_id)
                                .is_some_and(|actual| actual.text == original.text) {
                                return Ok(false);
                            }
                        }
                        Ok(found_target && matched == baseline_stories.len())
                    })();
                    let (status, syid_verified) = match verified {
                        Ok(true) => ("HOSTED_PASS", true),
                        Ok(false) => ("SYID_OR_UNRELATED_STORY_MISMATCH", false),
                        Err(_) => ("SYID_VERIFICATION_UNAVAILABLE", false),
                    };
                    item["result"] = json!(status);
                    item["replay_byte_equal"] = receipt["editor_project_replay_byte_equal"].clone();
                    item["quill_syid_siblings_preserved"] = json!(syid_verified);
                    item["candidate_sha256"] = receipt["output_sha256"].clone();
                }
                Err(error) => {
                    let reason = error.to_string();
                    item["result"] = json!(safe_error_class(&reason));
                    if let Some(code) = safe_writer_code(&reason) {
                        item["writer_blocker_code"] = json!(code);
                    }
                }
            }
            attempts.push(item);
            }
        }
        cases.push(json!({
            "story_ordinal": ordinal,
            "story_utf16_len": before.encode_utf16().count(),
            "ascii_total": n,
            "attempts": attempts
        }));
    }
    report["stories"] = json!(cases);
    report["result"] = json!("EVALUATED");
    ensure!(sha256(source) == source_hash, "immutable source was changed");
    Ok(report)
}

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let input = args.next().context("source .pub path")?;
    let expected_sha = args.next().context("source sha256")?;
    let output = args.next().context("unused receipt path")?;
    let max_stories = args.next().unwrap_or_else(|| "3".to_string()).parse::<usize>()?;
    ensure!(args.next().is_none() && (1..=3).contains(&max_stories), "invalid arguments");
    ensure!(expected_sha.len() == 64
        && expected_sha.bytes().all(|b| b.is_ascii_hexdigit()), "invalid source SHA");
    let bytes = fs::read(input)?;
    ensure!(bytes.len() <= 12 * 1024 * 1024, "source exceeds 12MiB");
    let report = probe(&bytes, &expected_sha, max_stories)?;
    let mut f = fs::OpenOptions::new().write(true).create_new(true).open(output)?;
    f.write_all(&serde_json::to_vec_pretty(&report)?)?;
    f.write_all(b"\n")?;
    f.sync_all()?;
    println!("{}", serde_json::to_string(&json!({
        "source_sha256": expected_sha, "result": report["result"],
        "story_count": report["eligible_story_attempts"]
    }))?);
    Ok(())
}
