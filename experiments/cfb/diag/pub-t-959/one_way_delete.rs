//! PUB-T-959: one-way deletion through the original pinned rar2 Writer.
//! PUB bytes and Story contents remain in a temporary worker directory.
//! Never print raw errors or text, or write them to public receipts.
use anyhow::{ensure, Context, Result};
use pub_editor::{open_mature_0x2c_editor, Sha256Digest};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{env, fs, io::{Cursor, Write}};

fn hash(input: &[u8]) -> Sha256Digest {
    let mut bytes = [0u8;32];
    bytes.copy_from_slice(&Sha256::digest(input));
    Sha256Digest::from_bytes(bytes)
}
fn blocked(code: &str) -> Value {
    let safe = if !code.is_empty() && code.len()<=64 &&
        code.bytes().all(|c| c.is_ascii_lowercase() || c == b'_')
        { code } else { "unclassified_writer_guard" };
    json!({"status":"WRITER_BLOCKED","writer_code":safe})
}
fn probe(input: &[u8], expected: &str) -> Result<(Value,Option<Vec<u8>>)> {
    let source_hash=hash(input);
    ensure!(source_hash.to_string()==expected,"source identity changed");
    let mut editor=match open_mature_0x2c_editor(input,source_hash) {
        Ok(x)=>x, Err(_)=>return Ok((json!({"status":"SOURCE_OPEN_BLOCKED"}),None))
    };
    let initial=editor.graph().stories.clone();
    let selected=initial.iter().find_map(|(id,s)| {
        let letters=s.text.char_indices().filter(|(_,c)|c.is_ascii_alphanumeric()).collect::<Vec<_>>();
        if letters.is_empty() || editor.can_replace_story_text(*id).is_err(){return None}
        let (byte_pos,ch)=letters[1.min(letters.len()-1)];
        Some((*id,s.text.clone(),byte_pos,ch))
    });
    let Some((id,before,pos,ch))=selected else {
        return Ok((json!({"status":"NO_ELIGIBLE_STORY"}),None))
    };
    let offset_utf16=before[..pos].encode_utf16().count();
    let mut after=before.clone();after.remove(pos);
    ensure!(ch.is_ascii_alphanumeric(),"unstable ASCII offset");
    if editor.replace_story_text(id,after.clone()).is_err(){
        return Ok((json!({"status":"CANONICAL_EDIT_REJECTED"}),None))
    }
    let project=editor.project();
    let candidate=match editor.materialize_mature_0x2c_native_pub_candidate(input){
        Ok(x)=>x,
        Err(e)=>return Ok((blocked(e.code()),None))
    };
    if candidate.source_hash!=source_hash || candidate.output_hash!=hash(&candidate.bytes) || candidate.bytes==input {
        return Ok((json!({"status":"HASH_OR_NO_CHANGE"}),None))
    }
    let reopened=match open_mature_0x2c_editor(&candidate.bytes,candidate.output_hash){
        Ok(x)=>x,Err(_)=>return Ok((json!({"status":"REOPEN_FAILED"}),None))
    };
    if !reopened.graph().stories.get(&candidate.output_story_id)
        .is_some_and(|s|s.text==after) {
        return Ok((json!({"status":"TARGET_SEMANTIC_MISMATCH"}),None))
    }
    // Check that all source Story SYIDs and siblings retain their semantic text.
    let correct_siblings=(|| -> Result<bool> {
        let old_bytes=pub_cfb::read_stream_reader(Cursor::new(input),pub_reader::QUILL_STREAM_PATH)?;
        let new_bytes=pub_cfb::read_stream_reader(Cursor::new(&candidate.bytes),pub_reader::QUILL_STREAM_PATH)?;
        let old=pub_quill::parse_confirmed_story_catalog(pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&old_bytes)?;
        let new=pub_quill::parse_confirmed_story_catalog(pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&new_bytes)?;
        let mut old_ids=old.stories.iter().map(|s|s.syid.0).collect::<Vec<_>>();
        let mut new_ids=new.stories.iter().map(|s|s.syid.0).collect::<Vec<_>>();
        old_ids.sort_unstable();new_ids.sort_unstable();
        if old_ids!=new_ids || old_ids.windows(2).any(|p|p[0]==p[1]) ||
            initial.len()!=reopened.graph().stories.len(){return Ok(false)}
        let mut matched=0usize;
        let mut found=false;
        for story in &old.stories {
            let old_id=pub_reader::derive_pub_story_id(&source_hash,story.syid.0)?;
            let new_id=pub_reader::derive_pub_story_id(&candidate.output_hash,story.syid.0)?;
            let Some(old_story)=initial.get(&old_id) else { continue };
            matched+=1;
            if old_id==id {
                found=new_id==candidate.output_story_id;
            }else if !reopened.graph().stories.get(&new_id)
                .is_some_and(|s|s.text==old_story.text) {return Ok(false)}
        }
        Ok(found && matched==initial.len())
    })();
    if !matches!(correct_siblings,Ok(true)){
        return Ok((json!({"status":"SYID_OR_SIBLING_MISMATCH"}),None))
    }
    let mut replay=match open_mature_0x2c_editor(input,source_hash){
        Ok(x)=>x,Err(_)=>return Ok((json!({"status":"REPLAY_OPEN_FAILED"}),None))
    };
    if replay.apply_project(&project).is_err(){
        return Ok((json!({"status":"REPLAY_APPLY_FAILED"}),None))
    }
    let again=match replay.materialize_mature_0x2c_native_pub_candidate(input){
        Ok(x)=>x,Err(_)=>return Ok((json!({"status":"REPLAY_WRITE_FAILED"}),None))
    };
    if again.bytes!=candidate.bytes || hash(input)!=source_hash {
        return Ok((json!({"status":"REPLAY_BYTES_MISMATCH"}),None))
    }
    Ok((json!({
        "status":"HOSTED_PASS","source_sha256":expected,
        "candidate_sha256":candidate.output_hash.to_string(),
        "source_bytes":input.len(),"candidate_bytes":candidate.bytes.len(),
        "edit":"delete_one_ascii","offset_utf16":offset_utf16,
        "reader_reopened":true,"syid_siblings_preserved":true,
        "project_replay_byte_equal":true,"source_immutable":true,
        "native_publisher_acceptance":"NOT_EVALUATED"
    }),Some(candidate.bytes)))
}
fn main()->Result<()> {
    let mut it=env::args().skip(1);
    let src=it.next().context("source path argument")?;
    let expected=it.next().context("source sha argument")?;
    let out=it.next().context("candidate temporary path argument")?;
    let receipt=it.next().context("receipt temporary path argument")?;
    ensure!(it.next().is_none(),"wrong number of arguments");
    ensure!(expected.len()==64 && expected.bytes().all(|x|x.is_ascii_hexdigit()),"bad digest format");
    let bytes=fs::read(src)?;
    ensure!(bytes.len()<=12*1024*1024,"source size limit");
    let (status,candidate)=probe(&bytes,&expected)?;
    if let Some(candidate)=candidate {fs::write(out,candidate)?}
    let mut f=fs::OpenOptions::new().create_new(true).write(true).open(receipt)?;
    f.write_all(&serde_json::to_vec_pretty(&status)?)?; f.write_all(b"\n")?;
    f.sync_all()?;
    println!("{}",serde_json::to_string(&json!({"status":status["status"]}))?);
    Ok(())
}
