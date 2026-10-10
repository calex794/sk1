//! SK1-QUILL-EXP-PUB-T-960: separate-Story two-deletion ordering using ONLY pinned rar2 Writer.
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



struct StoryControl {
    ordinal: usize,
    syid: u32,
    before: String,
    after: String,
    offset_utf16: usize,
    single: Step,
}

/// Verify BOTH distinct Story edits survived the second Writer step using
/// source and final parsed SYID identities. This is not an atomic edit API.
fn final_stories_match(
    source_catalog:&pub_quill::QuillStoryCatalog,
    final_pub:&[u8],
    controls:&[StoryControl],
    ai:usize,bi:usize,
)->bool {
    let check=(||->Result<bool> {
        let hash=sha256(final_pub);
        let editor=open_mature_0x2c_editor(final_pub,hash)?;
        let final_quill=pub_cfb::read_stream_reader(
            Cursor::new(final_pub),pub_reader::QUILL_STREAM_PATH)?;
        let cat=pub_quill::parse_confirmed_story_catalog(
            pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&final_quill)?;
        if source_catalog.stories.len()!=cat.stories.len(){return Ok(false);}
        for (before,after) in source_catalog.stories.iter().zip(&cat.stories) {
            if before.syid!=after.syid{return Ok(false);}
            let control=controls.iter().find(|c|c.syid==before.syid.0);
            let expected=match control {
                Some(c) if c.syid==controls[ai].syid || c.syid==controls[bi].syid =>
                    c.after.encode_utf16().flat_map(|unit|unit.to_le_bytes()).collect::<Vec<u8>>(),
                _=>before.utf16le.clone()
            };
            if after.utf16le!=expected {return Ok(false);}
        }
        for i in [ai,bi] {
            let c=&controls[i];
            let id=pub_reader::derive_pub_story_id(&hash,c.syid)?;
            if !editor.graph().stories.get(&id).is_some_and(|s|s.text==c.after){
                return Ok(false);
            }
        }
        Ok(true)
    })();
    matches!(check,Ok(true))
}

fn inspect_source(source:&[u8], expected_sha:&str)->Result<Value> {
    ensure!(sha256(source).to_string()==expected_sha,"source SHA drift");
    let source_hash=sha256(source);
    let mut receipt=json!({
        "schema":"sk1.quill-exp-pub-t-960.inter-story.v1",
        "source_sha256":expected_sha,
        "source_bytes":source.len(),
        "result":"NOT_EVALUATED",
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":false,
        "eligible_story_count":0,
        "single_controls":[],
        "pairs":[]
    });
    let editor=match open_mature_0x2c_editor(source,source_hash){
        Ok(v)=>v,
        Err(_)=>{
            receipt["result"]=json!("SOURCE_EDITOR_OPEN_BLOCKED");
            return Ok(receipt)
        }
    };
    let eligible=editor.graph().stories.iter()
        .filter(|(id,s)|editor.can_replace_story_text(**id).is_ok()
            && s.text.chars().any(|c|c.is_ascii_alphanumeric()))
        .take(3)
        .map(|(id,s)|(*id,s.text.clone())).collect::<Vec<_>>();
    receipt["eligible_story_count"]=json!(eligible.len());
    if eligible.len()<2{
        receipt["result"]=json!("INSUFFICIENT_ELIGIBLE_STORIES");
        return Ok(receipt);
    }
    let quill=pub_cfb::read_stream_reader(Cursor::new(source),pub_reader::QUILL_STREAM_PATH)?;
    let catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&quill)?;
    let mut controls=Vec::new();
    for (ordinal,(id,before)) in eligible.into_iter().enumerate(){
        let mut matched=catalog.stories.iter().filter(|story|
            pub_reader::derive_pub_story_id(&source_hash,story.syid.0)
                .is_ok_and(|lookup|lookup==id));
        let syid=matched.next().context("missing eligible Story SYID")?.syid.0;
        ensure!(matched.next().is_none(),"duplicate target SYID");
        let n=before.chars().filter(|ch|ch.is_ascii_alphanumeric()).count();
        ensure!(n>0,"missing selectable ASCII character");
        let offset=rank_offset(&before,1_usize.min(n-1))?;
        let after=delete_at_utf16(&before,offset)?;
        let one=step(source,syid,&before,&after);
        controls.push(StoryControl{
            ordinal,syid,before,after,offset_utf16:offset,single:one
        });
    }
    receipt["single_controls"]=json!(controls.iter().map(|c|json!({
        "story_ordinal":c.ordinal,
        "syid":c.syid,
        "offset_utf16":c.offset_utf16,
        "single_delete":c.single.receipt.clone()
    })).collect::<Vec<_>>());
    // The predeclared 11th PUB has a TOKN-protected third Story.
    // It is a legitimate negative single control, NOT a third candidate for
    // a pair whose both independent single deletes succeeded in PUB-T-956.
    let permitted=controls.iter().enumerate()
        .filter(|(_,c)|c.single.receipt["status"]=="HOSTED_PASS")
        .map(|(i,_)|i).collect::<Vec<_>>();
    if permitted.len()<2{
        receipt["result"]=json!("INSUFFICIENT_ACCEPTED_SINGLE_CONTROLS");
        return Ok(receipt);
    }
    let mut rows=Vec::new();
    for ia in 0..permitted.len(){
        for ib in ia+1..permitted.len(){
            let ai=permitted[ia];
            let bi=permitted[ib];
            let a=&controls[ai];
            let b=&controls[bi];
            let ab=step(a.single.bytes.as_deref().context("missing A single")?,
                        b.syid,&b.before,&b.after);
            let ba=step(b.single.bytes.as_deref().context("missing B single")?,
                        a.syid,&a.before,&a.after);
            let ab_pass=ab.receipt["status"]=="HOSTED_PASS";
            let ba_pass=ba.receipt["status"]=="HOSTED_PASS";
            let ab_final=if ab_pass{Some(final_stories_match(
                &catalog,ab.bytes.as_deref().context("missing AB")?,&controls,ai,bi))}
                else{None};
            let ba_final=if ba_pass{Some(final_stories_match(
                &catalog,ba.bytes.as_deref().context("missing BA")?,&controls,ai,bi))}
                else{None};
            let same=if ab_pass&&ba_pass{
                Some(ab.bytes==ba.bytes)
            }else{None};
            rows.push(json!({
                "a_story_ordinal":a.ordinal,
                "b_story_ordinal":b.ordinal,
                "a_syid":a.syid,
                "b_syid":b.syid,
                "a_offset_utf16":a.offset_utf16,
                "b_offset_utf16":b.offset_utf16,
                "a_then_b_second":ab.receipt,
                "b_then_a_second":ba.receipt,
                "a_then_b_final_stories_match":ab_final,
                "b_then_a_final_stories_match":ba_final,
                "both_final_byte_equal":same
            }));
        }
    }
    receipt["pairs"]=json!(rows);
    receipt["result"]=json!("EVALUATED");
    ensure!(sha256(source).to_string()==expected_sha,"original input changed");
    Ok(receipt)
}

fn main()->Result<()> {
    let mut args=env::args().skip(1);
    let input=args.next().context("input source PUB")?;
    let expected_sha=args.next().context("expected source SHA")?;
    let output=args.next().context("source-safe receipt output")?;
    ensure!(args.next().is_none(),"unexpected args");
    ensure!(expected_sha.len()==64 && expected_sha.bytes().all(|b|b.is_ascii_hexdigit()),
            "invalid source SHA");
    let raw=fs::read(input)?;
    ensure!(raw.len()<=12*1024*1024,"source bytes exceed limit");
    let report=inspect_source(&raw,&expected_sha)?;
    let mut file=fs::OpenOptions::new().create_new(true).write(true).open(output)?;
    file.write_all(&serde_json::to_vec_pretty(&report)?)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    println!("{}",serde_json::to_string(&json!({
        "source_sha256":expected_sha,
        "result":report["result"],
        "pairs":report["pairs"].as_array().map_or(0,|a|a.len())
    }))?);
    Ok(())
}
