//! Cross-fixture, offline-only Story writer discriminator.
//!
//! All inputs are pinned public Apache POI fixture blobs already stored in the
//! repository. Never exports PUB bytes or grants Publisher-native save authority.
//! The positive Sample3 control catches broken harness/Writer plumbing.
use anyhow::{Context, Result, bail, ensure};
use pub_editor::{EditorSession, Sha256Digest, open_mature_0x2c_editor};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{env, fs, io::Write};

const ACCEPTED_CONTROL_SHA: &str =
    "b9b789f35a34e016faceb27acf50bf0621273a7d612762ecc17c56ca450fe715";
const SAMPLE3_SOURCE_SHA: &str =
    "424c69173ff08948c2529c8084b4ac2403f1ff1057146f4edd02fc29b44481fc";
const POSITIVE_MARKER: &str = "345678";
const MAX_STORIES_PER_FIXTURE: usize = 8;

const SAMPLE3_B64: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../vendor/producer-a/crates/pub-quill/tests/fixtures/Sample3.pub.b64"
));
const SAMPLE4_B64: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../vendor/producer-a/crates/pub-quill/tests/fixtures/Sample4.pub.b64"
));
const LINK_AT_10_B64: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../vendor/producer-a/crates/pub-quill/tests/fixtures/LinkAt10.pub.b64"
));
const PUB_60685_B64: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../vendor/producer-a/crates/pub-quill/tests/fixtures/60685.pub.b64"
));
const SAMPLE_B64: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/../../vendor/producer-a/crates/pub-reader/tests/fixtures/Sample.pub.b64"
));

fn sha256(bytes: &[u8]) -> Sha256Digest {
    let hash = Sha256::digest(bytes);
    let mut digest = [0_u8; 32];
    digest.copy_from_slice(&hash);
    Sha256Digest::from_bytes(digest)
}

// Strict, dependency-free decoding of checked-in fixture bytes, no external I/O.
fn decode_fixture(encoded: &str) -> Result<Vec<u8>> {
    let cleaned = encoded
        .bytes()
        .filter(|b| !b.is_ascii_whitespace())
        .collect::<Vec<_>>();
    ensure!(!cleaned.is_empty() && cleaned.len() % 4 == 0, "invalid fixture base64 framing");
    let value = |b: u8| -> Result<u8> {
        match b {
            b'A'..=b'Z' => Ok(b - b'A'),
            b'a'..=b'z' => Ok(b - b'a' + 26),
            b'0'..=b'9' => Ok(b - b'0' + 52),
            b'+' => Ok(62),
            b'/' => Ok(63),
            _ => bail!("invalid fixture base64 alphabet"),
        }
    };
    let mut out = Vec::with_capacity(cleaned.len() / 4 * 3);
    for (index, chunk) in cleaned.chunks_exact(4).enumerate() {
        let last = index == cleaned.len() / 4 - 1;
        ensure!(last || (chunk[2] != b'=' && chunk[3] != b'='), "early fixture base64 padding");
        ensure!(chunk[2] != b'=' || chunk[3] == b'=', "invalid fixture base64 padding");
        let a = value(chunk[0])?;
        let b = value(chunk[1])?;
        let c = if chunk[2] == b'=' { 0 } else { value(chunk[2])? };
        let d = if chunk[3] == b'=' { 0 } else { value(chunk[3])? };
        out.push((a << 2) | (b >> 4));
        if chunk[2] != b'=' {
            out.push((b << 4) | (c >> 2));
        }
        if chunk[3] != b'=' {
            out.push((c << 6) | d);
        }
    }
    Ok(out)
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

fn positive_control() -> Result<Value> {
    let source = decode_fixture(SAMPLE3_B64)?;
    let source_hash = sha256(&source);
    ensure!(source_hash.to_string() == SAMPLE3_SOURCE_SHA, "control source fixture changed");
    let mut editor = open_mature_0x2c_editor(&source, source_hash)
        .context("positive control Editor open failed")?;
    let eligible = editor
        .graph()
        .stories
        .iter()
        .filter(|(id, story)| {
            story.text.matches(POSITIVE_MARKER).count() == 1
                && editor.can_replace_story_text(**id).is_ok()
        })
        .map(|(id, story)| (*id, story.text.clone()))
        .collect::<Vec<_>>();
    ensure!(eligible.len() == 1, "positive control Story identity/eligibility ambiguous");
    let (id, before) = &eligible[0];
    let after = before.replacen(POSITIVE_MARKER, "34567", 1);
    editor
        .replace_story_text(*id, after.clone())
        .context("positive control edit failed")?;
    let accepted = verify_candidate(&editor, &source, &after)?;
    ensure!(accepted["output_sha256"] == ACCEPTED_CONTROL_SHA, "Publisher-approved positive control SHA drift");
    Ok(json!({
        "fixture": "Sample3",
        "source_sha256": source_hash.to_string(),
        "source_byte_len": source.len(),
        "result": "positive_control_exact_native_publisher_accepted_pair",
        "receipt": accepted
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
    ensure!(source_hash.to_string() == expected_sha, "SHA input changed");
    let mut out = json!({
        "schema": "sk1.writer-hosted-applicability.v1",
        "source_sha256": expected_sha,
        "source_bytes": source.len(),
        "publisher_native_acceptance": "NOT_EVALUATED",
        "product_download_authorized": false,
        "attempts": [],
        "result": "NOT_EVALUATED"
    });
    let editor = match open_mature_0x2c_editor(source, source_hash) {
        Ok(editor) => editor,
        Err(_) => {
            out["result"] = json!("SOURCE_EDITOR_OPEN_BLOCKED");
            return Ok(out);
        }
    };
    let baseline_stories = editor.graph().stories.clone();
    out["source_story_count"] = json!(baseline_stories.len());
    let eligible = baseline_stories.iter()
        .filter(|(id, story)| editor.can_replace_story_text(**id).is_ok()
            && story.text.char_indices().any(|(_, c)| c.is_ascii_alphanumeric()))
        .take(max_stories)
        .map(|(id, story)| (*id, story.text.clone()))
        .collect::<Vec<_>>();
    out["eligible_story_attempts"] = json!(eligible.len());
    if eligible.is_empty() {
        out["result"] = json!("NO_PLAIN_EDITABLE_STORY");
        return Ok(out);
    }
    let mut attempts = vec![];
    for (id, before) in eligible {
        let Some((position, ch)) = before.char_indices().find(|(_, c)| c.is_ascii_alphanumeric()) else { continue };
        for variant in ["ascii_replace", "ascii_delete"] {
            let mut after = before.clone();
            if variant == "ascii_replace" {
                let replacement = if ch == 'X' { "Y" } else { "X" };
                after.replace_range(position..position + ch.len_utf8(), replacement);
            } else {
                after.remove(position);
            }
            let mut attempt = json!({
                "arm": variant,
                "before_utf16_units": before.encode_utf16().count(),
                "after_utf16_units": after.encode_utf16().count(),
                "result": "NOT_EVALUATED"
            });
            let mut edited = open_mature_0x2c_editor(source, source_hash)
                .context("already-open source became unavailable")?;
            if edited.replace_story_text(id, after.clone()).is_err() {
                attempt["result"] = json!("CANONICAL_EDIT_REJECTED");
                attempts.push(attempt);
                continue;
            }
            match verify_candidate(&edited, source, &after) {
                Ok(receipt) => {
                    let candidate = edited.materialize_mature_0x2c_native_pub_candidate(source)?;
                    let reopened = open_mature_0x2c_editor(&candidate.bytes, candidate.output_hash)?;
                    // Canonical StoryIds are salted with each file's SHA. Compare
                    // underlying Quill SYIDs across Writer output instead of
                    // treating expected source-ID changes as corruption.
                    let syid_preservation = (|| -> Result<bool> {
                        let source_quill = pub_cfb::read_stream_reader(
                            std::io::Cursor::new(source), pub_reader::QUILL_STREAM_PATH)?;
                        let output_quill = pub_cfb::read_stream_reader(
                            std::io::Cursor::new(&candidate.bytes), pub_reader::QUILL_STREAM_PATH)?;
                        let source_catalog = pub_quill::parse_confirmed_story_catalog(
                            pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &source_quill)?;
                        let output_catalog = pub_quill::parse_confirmed_story_catalog(
                            pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &output_quill)?;
                        let mut source_syids = source_catalog.stories.iter()
                            .map(|story| story.syid.0).collect::<Vec<_>>();
                        let mut output_syids = output_catalog.stories.iter()
                            .map(|story| story.syid.0).collect::<Vec<_>>();
                        source_syids.sort_unstable();
                        output_syids.sort_unstable();
                        if source_syids != output_syids
                            || source_syids.windows(2).any(|pair| pair[0] == pair[1])
                            || reopened.graph().stories.len() != baseline_stories.len() {
                            return Ok(false);
                        }
                        let mut matched_source_graph = 0;
                        let mut found_target = false;
                        for entry in &source_catalog.stories {
                            let source_id = pub_reader::derive_pub_story_id(
                                &source_hash, entry.syid.0)?;
                            let output_id = pub_reader::derive_pub_story_id(
                                &candidate.output_hash, entry.syid.0)?;
                            let Some(original) = baseline_stories.get(&source_id) else { continue };
                            matched_source_graph += 1;
                            if source_id == id {
                                found_target = output_id == candidate.output_story_id;
                            } else if !reopened.graph().stories.get(&output_id)
                                .is_some_and(|next| next.text == original.text) {
                                return Ok(false);
                            }
                        }
                        Ok(found_target && matched_source_graph == baseline_stories.len())
                    })();
                    let (outcome, verified) = match syid_preservation {
                        Ok(true) => ("HOSTED_PASS", true),
                        Ok(false) => ("SYID_OR_UNRELATED_STORY_MISMATCH", false),
                        Err(_) => ("SYID_VERIFICATION_UNAVAILABLE", false),
                    };
                    attempt["result"] = json!(outcome);
                    attempt["output_sha256"] = receipt["output_sha256"].clone();
                    attempt["candidate_bytes"] = receipt["output_byte_len"].clone();
                    attempt["project_replay_byte_equal"] = receipt["editor_project_replay_byte_equal"].clone();
                    attempt["quill_syid_and_other_story_text_preserved"] = json!(verified);
                }
                Err(error) => {
                    let reason = error.to_string();
                    attempt["result"] = json!(safe_error_class(&reason));
                    if let Some(code) = safe_writer_code(&reason) {
                        attempt["writer_blocker_code"] = json!(code);
                    }
                }
            }
            attempts.push(attempt);
        }
    }
    out["attempts"] = json!(attempts);
    out["result"] = json!("EVALUATED");
    ensure!(sha256(source) == source_hash, "source was mutated");
    Ok(out)
}

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let input_path = args.next().context("input path")?;
    let expected_sha = args.next().context("expected SHA256")?;
    let output_path = args.next().context("output receipt path")?;
    let max_stories = args.next().unwrap_or_else(|| "3".to_string()).parse::<usize>()?;
    ensure!(max_stories > 0 && max_stories <= 3, "max-stories 1..3");
    ensure!(args.next().is_none(), "too many arguments");
    ensure!(expected_sha.len() == 64 && expected_sha.bytes().all(|b| b.is_ascii_hexdigit()), "invalid expected SHA");
    let input = fs::read(&input_path)?;
    ensure!(input.len() <= 12 * 1024 * 1024, "input exceeds 12 MiB limit");
    let report = probe(&input, &expected_sha, max_stories)?;
    let mut file = fs::OpenOptions::new().write(true).create_new(true).open(output_path)?;
    file.write_all(&serde_json::to_vec_pretty(&report)?)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    println!("{}", serde_json::to_string(&json!({"source_sha256": expected_sha, "result": report["result"]}))?);
    Ok(())
}
