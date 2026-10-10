//! SK1-QUILL-EXP-PUB-T-964: mixed-sign cross-Story +1/-1 ordering using ONLY pinned rar2 Writer.
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



/// Insert one original +1 ASCII marker from EXP-956 at the exact
/// pre-registered UTF-16 boundary; no CR or Unicode surrogate touched.
fn insert_at_utf16(text:&str, offset:usize)->Result<String>{
    let mut units=0usize;
    for (idx,ch) in text.char_indices(){
        if units==offset {
            ensure!(ch.is_ascii_alphanumeric(),"not a suitable insertion rank");
            let previous=text[..idx].chars().last();
            let marker=['X','Q','Z'].into_iter()
                .find(|&c|Some(c)!=previous&&c!=ch)
                .context("no ASCII insert marker")?;
            let mut after=text.to_owned();
            after.insert(idx,marker);
            return Ok(after);
        }
        units+=ch.len_utf16();
    }
    anyhow::bail!("insertion offset not found")
}
struct StoryControl {
    ordinal:usize,
    syid:u32,
    before:String,
    after_insert:String,
    after_delete:String,
    offset_utf16:usize,
    single_insert:Step,
    single_delete:Step,
}
fn final_stories_match(source_catalog:&pub_quill::QuillStoryCatalog,
                       final_pub:&[u8],controls:&[StoryControl],
                       insert_i:usize,delete_i:usize)->bool{
    let outcome=(||->Result<bool>{
        ensure!(insert_i!=delete_i,"same Story not permitted");
        let hash=sha256(final_pub);
        let editor=open_mature_0x2c_editor(final_pub,hash)?;
        let fq=pub_cfb::read_stream_reader(
            Cursor::new(final_pub),pub_reader::QUILL_STREAM_PATH)?;
        let cat=pub_quill::parse_confirmed_story_catalog(
            pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&fq)?;
        if cat.stories.len()!=source_catalog.stories.len(){return Ok(false);}
        for (a,b)in source_catalog.stories.iter().zip(&cat.stories){
            if a.syid!=b.syid{return Ok(false);}
            let match_control=controls.iter().find(|c|c.syid==a.syid.0);
            let expected=match match_control{
                Some(c)if c.syid==controls[insert_i].syid=>
                    c.after_insert.encode_utf16()
                        .flat_map(|x|x.to_le_bytes()).collect::<Vec<u8>>(),
                Some(c)if c.syid==controls[delete_i].syid=>
                    c.after_delete.encode_utf16()
                        .flat_map(|x|x.to_le_bytes()).collect::<Vec<u8>>(),
                _=>a.utf16le.clone()
            };
            if b.utf16le!=expected {return Ok(false);}
        }
        for (i,inserted) in [(insert_i,true),(delete_i,false)] {
            let c=&controls[i];
            let id=pub_reader::derive_pub_story_id(&hash,c.syid)?;
            let expected=if inserted{&c.after_insert}else{&c.after_delete};
            if !editor.graph().stories.get(&id).is_some_and(|s|s.text==*expected){
                return Ok(false);
            }
        }
        Ok(true)
    })();
    matches!(outcome,Ok(true))
}

fn inspect_source(source:&[u8],expected_sha:&str)->Result<Value>{
    ensure!(sha256(source).to_string()==expected_sha,"source SHA mismatch");
    let original_hash=sha256(source);
    let mut receipt=json!({
        "schema":"sk1.quill-exp-pub-t-964.cross-story-mixed.v1",
        "source_sha256":expected_sha,
        "source_bytes":source.len(),
        "result":"NOT_EVALUATED",
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":false,
        "eligible_story_count":0,
        "single_controls":[],
        "pairs":[]
    });
    let editor=match open_mature_0x2c_editor(source,original_hash) {
        Ok(v)=>v,Err(_)=>{receipt["result"]=json!("SOURCE_EDITOR_OPEN_BLOCKED");return Ok(receipt)}
    };
    let eligible=editor.graph().stories.iter()
        .filter(|(id,s)|editor.can_replace_story_text(**id).is_ok()
            &&s.text.chars().any(|c|c.is_ascii_alphanumeric()))
        .take(3)
        .map(|(id,s)|(*id,s.text.clone())).collect::<Vec<_>>();
    receipt["eligible_story_count"]=json!(eligible.len());
    if eligible.len()<2 {
        receipt["result"]=json!("INSUFFICIENT_ELIGIBLE_STORIES");
        return Ok(receipt);
    }
    let quill=pub_cfb::read_stream_reader(Cursor::new(source),pub_reader::QUILL_STREAM_PATH)?;
    let catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&quill)?;
    let mut controls=Vec::new();
    for (ordinal,(id,before)) in eligible.into_iter().enumerate() {
        let mut source_story=catalog.stories.iter()
            .filter(|s|pub_reader::derive_pub_story_id(&original_hash,s.syid.0)
                .is_ok_and(|derived|derived==id));
        let syid=source_story.next().context("no original SYID identity")?.syid.0;
        ensure!(source_story.next().is_none(),"ambiguous original SYID");
        let ascii_n=before.chars().filter(|c|c.is_ascii_alphanumeric()).count();
        ensure!(ascii_n>0,"no rankable ASCII");
        let offset=rank_offset(&before,1usize.min(ascii_n-1))?;
        let after_insert=insert_at_utf16(&before,offset)?;
        let after_delete=delete_at_utf16(&before,offset)?;
        let inc=step(source,syid,&before,&after_insert);
        let dec=step(source,syid,&before,&after_delete);
        controls.push(StoryControl{
            ordinal,syid,before,after_insert,after_delete,
            offset_utf16:offset,single_insert:inc,single_delete:dec
        });
    }
    receipt["single_controls"]=json!(controls.iter().map(|c|json!({
        "story_ordinal":c.ordinal,"syid":c.syid,"offset_utf16":c.offset_utf16,
        "single_insert":c.single_insert.receipt.clone(),
        "single_delete":c.single_delete.receipt.clone()
    })).collect::<Vec<_>>());
    let permitted=controls.iter().enumerate()
        .filter(|(_,c)|c.single_insert.receipt["status"]=="HOSTED_PASS" &&
            c.single_delete.receipt["status"]=="HOSTED_PASS")
        .map(|(i,_)|i).collect::<Vec<_>>();
    if permitted.len()<2{
        receipt["result"]=json!("INSUFFICIENT_BOTH_SINGLE_PASS_CONTROLS");
        return Ok(receipt)
    }
    let mut pair_rows=Vec::<Value>::new();
    for ia in 0..permitted.len() {
        for ib in ia+1..permitted.len() {
            for (insert_i,delete_i) in [(permitted[ia],permitted[ib]),
                                        (permitted[ib],permitted[ia])] {
                let ins=&controls[insert_i];
                let del=&controls[delete_i];
                let insert_then_delete=step(
                    ins.single_insert.bytes.as_deref().context("missing insert output")?,
                    del.syid,&del.before,&del.after_delete);
                let delete_then_insert=step(
                    del.single_delete.bytes.as_deref().context("missing delete output")?,
                    ins.syid,&ins.before,&ins.after_insert);
                let id_ok=insert_then_delete.receipt["status"]=="HOSTED_PASS";
                let di_ok=delete_then_insert.receipt["status"]=="HOSTED_PASS";
                let id_final=if id_ok{Some(final_stories_match(
                    &catalog,insert_then_delete.bytes.as_deref().context("missing ID bytes")?,
                    &controls,insert_i,delete_i))}else{None};
                let di_final=if di_ok{Some(final_stories_match(
                    &catalog,delete_then_insert.bytes.as_deref().context("missing DI bytes")?,
                    &controls,insert_i,delete_i))}else{None};
                let same=if id_ok&&di_ok {
                    Some(insert_then_delete.bytes==delete_then_insert.bytes)
                }else{None};
                pair_rows.push(json!({
                    "insert_story_ordinal":ins.ordinal,
                    "delete_story_ordinal":del.ordinal,
                    "insert_story_syid":ins.syid,
                    "delete_story_syid":del.syid,
                    "insert_offset_utf16":ins.offset_utf16,
                    "delete_offset_utf16":del.offset_utf16,
                    "insert_then_delete_second":insert_then_delete.receipt,
                    "delete_then_insert_second":delete_then_insert.receipt,
                    "insert_then_delete_final_stories_match":id_final,
                    "delete_then_insert_final_stories_match":di_final,
                    "both_final_byte_equal":same
                }));
            }
        }
    }
    receipt["pairs"]=json!(pair_rows);
    receipt["result"]=json!("EVALUATED");
    ensure!(sha256(source).to_string()==expected_sha,"source mutated");
    Ok(receipt)
}
fn main()->Result<()>{
    let mut args=env::args().skip(1);
    let input=args.next().context("source path")?;
    let expected_sha=args.next().context("source SHA")?;
    let output=args.next().context("receipt path")?;
    ensure!(args.next().is_none(),"unexpected args");
    ensure!(expected_sha.len()==64 &&
        expected_sha.bytes().all(|x|x.is_ascii_hexdigit()),"bad SHA");
    let source=fs::read(input)?;
    ensure!(source.len()<=12*1024*1024,"source file byte cap exceeded");
    let report=inspect_source(&source,&expected_sha)?;
    let mut f=fs::OpenOptions::new().create_new(true).write(true).open(output)?;
    f.write_all(&serde_json::to_vec_pretty(&report)?)?;
    f.write_all(b"\n")?;
    f.sync_all()?;
    println!("{}",serde_json::to_string(&json!({
        "source_sha256":expected_sha,
        "result":report["result"],"eligible_stories":report["eligible_story_count"]
    }))?);
    Ok(())
}
