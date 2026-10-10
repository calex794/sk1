//! SK1-QUILL-EXP-PUB-T-956: inverse +/-1 Story compositions using ONLY pinned rar2 Writer.
//! All PUB and Story bytes stay in ephemeral worker memory/directory.
use anyhow::{ensure, Context, Result};
use pub_editor::{Sha256Digest, open_mature_0x2c_editor};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{env, fs, io::{Cursor, Write}, collections::HashSet};

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


fn inspect_source(source: &[u8], expected_sha: &str) -> Result<Value> {
    ensure!(sha256(source).to_string()==expected_sha, "source SHA drift");
    let source_hash=sha256(source);
    let mut report=json!({
        "schema":"sk1.quill-exp-pub-t-956.inverse.v1",
        "source_sha256":expected_sha,
        "source_bytes":source.len(),
        "result":"NOT_EVALUATED",
        "publisher_native_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":false,
        "stories":[]
    });
    let editor=match open_mature_0x2c_editor(source,source_hash){
        Ok(e)=>e,
        Err(_)=>{
            report["result"]=json!("SOURCE_EDITOR_OPEN_BLOCKED");
            return Ok(report);
        }
    };
    let eligible=editor.graph().stories.iter()
        .filter(|(id,s)|editor.can_replace_story_text(**id).is_ok()
             && s.text.chars().any(|c|c.is_ascii_alphanumeric()))
        .take(3)
        .map(|(id,s)|(*id,s.text.clone()))
        .collect::<Vec<_>>();
    report["eligible_story_count"]=json!(eligible.len());
    if eligible.is_empty(){
        report["result"]=json!("NO_PLAIN_EDITABLE_STORY");
        return Ok(report);
    }
    let original_quill=pub_cfb::read_stream_reader(
        Cursor::new(source),pub_reader::QUILL_STREAM_PATH)?;
    let catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &original_quill)?;
    let mut out_stories=Vec::new();
    for (story_ordinal,(id,before)) in eligible.into_iter().enumerate() {
        let mut syids=catalog.stories.iter()
            .filter(|s|pub_reader::derive_pub_story_id(&source_hash,s.syid.0)
                .is_ok_and(|story_id|story_id==id));
        let target_syid=syids.next().context("target SYID missing")?.syid.0;
        ensure!(syids.next().is_none(),"ambiguous target SYID");
        let letters=before.char_indices().filter(|(_,c)|c.is_ascii_alphanumeric())
            .collect::<Vec<_>>();
        let n=letters.len();
        ensure!(n>0,"eligible Story lacks letters");
        let picks=[("first",0_usize),("second",1_usize.min(n-1)),("middle",(n-1)/2)];
        let mut attempted_offsets=HashSet::new();
        let mut pairs=Vec::new();
        for (slot,rank) in picks {
            let (byte_index,ch)=letters[rank];
            if !attempted_offsets.insert(byte_index){continue;}
            let original_offset=before[..byte_index].encode_utf16().count();
            let previous=before[..byte_index].chars().last();
            let next=before[byte_index+ch.len_utf8()..].chars().next();
            let reversible_offset_unambiguous=previous!=Some(ch) && next!=Some(ch);
            let marker=['X','Q','Z'].into_iter().find(|&c|{
                Some(c)!=previous && c!=ch
            }).context("missing distinct insert marker")?;
            let mut insert_text=before.clone();
            insert_text.insert(byte_index,marker);
            let mut delete_text=before.clone();
            delete_text.remove(byte_index);
            let baseline_insert=step(source,target_syid,&before,&insert_text);
            let baseline_delete=step(source,target_syid,&before,&delete_text);
            let both_single_pass=baseline_insert.receipt["status"]=="HOSTED_PASS" &&
                baseline_delete.receipt["status"]=="HOSTED_PASS";
            let mut pair=json!({
                "slot":slot,"ascii_rank":rank,"ascii_total":n,
                "offset_utf16":original_offset,
                "story_utf16_length":before.encode_utf16().count(),
                "ambiguous_reverse_delete_insert_offset":!reversible_offset_unambiguous,
                "single_insert":baseline_insert.receipt,
                "single_delete":baseline_delete.receipt,
                "both_single_pass":both_single_pass,
                "insert_then_delete":{"status":"NOT_EVALUATED_BASELINE_NOT_BOTH_PASS"},
                "delete_then_insert":{"status":"NOT_EVALUATED_BASELINE_NOT_BOTH_PASS"},
                "insert_delete_returns_original_bytes":Value::Null,
                "delete_insert_returns_original_bytes":Value::Null,
                "both_final_byte_equal":Value::Null
            });
            if both_single_pass{
                // Both inverse paths start independently from the original PUB.
                // A fresh editor is opened inside step for each intermediate PUB.
                let reverse_insert=step(
                    baseline_insert.bytes.as_ref().context("missing insert candidate")?,
                    target_syid,&insert_text,&before);
                let reverse_delete=step(
                    baseline_delete.bytes.as_ref().context("missing delete candidate")?,
                    target_syid,&delete_text,&before);
                let insert_delete_pass=reverse_insert.receipt["status"]=="HOSTED_PASS";
                let delete_insert_pass=reverse_delete.receipt["status"]=="HOSTED_PASS";
                pair["insert_then_delete"]=reverse_insert.receipt;
                pair["delete_then_insert"]=reverse_delete.receipt;
                if insert_delete_pass{
                    pair["insert_delete_returns_original_bytes"]=json!(
                        reverse_insert.bytes.as_ref().is_some_and(|bytes|bytes==source));
                }
                if delete_insert_pass{
                    pair["delete_insert_returns_original_bytes"]=json!(
                        reverse_delete.bytes.as_ref().is_some_and(|bytes|bytes==source));
                }
                if insert_delete_pass && delete_insert_pass{
                    pair["both_final_byte_equal"]=json!(
                        reverse_insert.bytes==reverse_delete.bytes);
                }
            }
            pairs.push(pair);
        }
        out_stories.push(json!({
            "story_ordinal":story_ordinal,
            "story_utf16_length":before.encode_utf16().count(),
            "ascii_total":n,
            "pairs":pairs
        }));
    }
    report["result"]=json!("EVALUATED");
    report["stories"]=json!(out_stories);
    ensure!(sha256(source).to_string()==expected_sha, "original changed in memory");
    Ok(report)
}

fn main()->Result<()> {
    let mut args=env::args().skip(1);
    let input=args.next().context("source input")?;
    let expected_sha=args.next().context("SHA")?;
    let output=args.next().context("output receipt")?;
    ensure!(args.next().is_none(),"invalid extra args");
    ensure!(expected_sha.len()==64 &&
            expected_sha.bytes().all(|b|b.is_ascii_hexdigit()),"invalid SHA");
    let raw=fs::read(input)?;
    ensure!(raw.len()<=12*1024*1024,"max source bytes exceeded");
    let report=inspect_source(&raw,&expected_sha)?;
    let mut f=fs::OpenOptions::new().create_new(true).write(true).open(output)?;
    f.write_all(&serde_json::to_vec_pretty(&report)?)?;
    f.write_all(b"\n")?;
    f.sync_all()?;
    println!("{}",serde_json::to_string(&json!({
        "source_sha256":expected_sha,
        "result":report["result"],
        "story_count":report["eligible_story_count"]
    }))?);
    Ok(())
}
