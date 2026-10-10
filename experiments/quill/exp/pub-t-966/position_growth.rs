//! PUB-T-966: bounded independent ASCII-growth arms on immutable PUB sources.
//! Uses ONLY the pinned upstream rar2 Editor, Writer, Reader and Quill parser.
//! No raw PUB, Story text or unknown Quill payload enters receipts.
use anyhow::{ensure, Context, Result};
use pub_editor::{open_mature_0x2c_editor, Sha256Digest};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{env, fs, io::{Cursor, Write}};

fn hash(bytes: &[u8]) -> Sha256Digest {
    let mut digest = [0u8;32];
    digest.copy_from_slice(&Sha256::digest(bytes));
    Sha256Digest::from_bytes(digest)
}
fn blocked(code: &str) -> Value {
    let safe = if !code.is_empty() && code.len() <= 64 &&
        code.bytes().all(|c| c.is_ascii_lowercase() || c==b'_') {
        code
    } else { "unclassified_writer_guard" };
    json!({"status":"WRITER_BLOCKED","writer_code":safe})
}
fn probe(input: &[u8], expected: &str, growth: usize, slot: &str) -> Result<(Value,Option<Vec<u8>>)> {
    ensure!((1..=8192).contains(&growth), "growth outside pre-registered bounds");
    ensure!(matches!(slot, "first" | "middle" | "last"), "slot not registered");
    let source_hash=hash(input);
    ensure!(source_hash.to_string()==expected,"SHA drift");
    let editor=match open_mature_0x2c_editor(input,source_hash) {
        Ok(x)=>x,Err(_)=>return Ok((json!({"status":"SOURCE_OPEN_BLOCKED","growth_utf16":growth}),None))
    };
    let initial=editor.graph().stories.clone();
    let selected=initial.iter().enumerate().find_map(|(ordinal,(id,s))| {
        if editor.can_replace_story_text(*id).is_err(){return None}
        let letters=s.text.char_indices().filter(|(_,c)|c.is_ascii_alphanumeric()).collect::<Vec<_>>();
        if letters.is_empty(){return None}
        let second_rank=1.min(letters.len()-1);
        let rank=match slot {"first"=>0,"middle"=>(letters.len()-1)/2,"last"=>letters.len()-1,_=>return None};
        let (pos,ch)=letters[rank];
        let second_pos=letters[second_rank].0;
        let first_pos=letters[0].0;
        let mid_pos=letters[(letters.len()-1)/2].0;
        let prev=s.text[..pos].chars().last();
        let marker=['X','Q','Z'].into_iter().find(|m|Some(*m)!=prev && *m!=ch)?;
        let second_offset=s.text[..second_pos].encode_utf16().count();
        let duplicate_second=pos==second_pos;
        let duplicate_other=(slot=="middle" && pos==first_pos)
            || (slot=="last" && (pos==first_pos || pos==mid_pos));
        Some((ordinal,*id,s.text.clone(),pos,marker,second_offset,letters.len(),
              duplicate_second,duplicate_other))
    });
    let Some((ordinal,id,before,pos,marker,second_offset,ascii_count,duplicate_second,duplicate_other))=selected else {
        return Ok((json!({"status":"NO_ELIGIBLE_STORY","growth_utf16":growth,"slot":slot}),None))
    };
    let offset_utf16=before[..pos].encode_utf16().count();
    let before_len=before.encode_utf16().count();
    let mut after=before.clone();after.insert_str(pos,&marker.to_string().repeat(growth));
    let common=json!({"growth_utf16":growth,"story_ordinal":ordinal,"slot":slot,
        "offset_utf16":offset_utf16,"before_utf16":before_len,
        "after_utf16":before_len+growth,
        "baseline_second_offset_utf16":second_offset,
        "ascii_count":ascii_count});
    if duplicate_second || duplicate_other {
        let mut x=common;
        x["status"]=json!(if duplicate_second {
            "DUPLICATE_SECOND_POSITION"
        } else {
            "DUPLICATE_OTHER_POSITION"
        });
        return Ok((x,None));
    }
    let mut edited=match open_mature_0x2c_editor(input,source_hash) {
        Ok(x)=>x,Err(_)=>return Ok((json!({"status":"SOURCE_OPEN_BLOCKED","growth_utf16":growth}),None))
    };
    if edited.replace_story_text(id,after.clone()).is_err(){
        let mut x=common;x["status"]=json!("CANONICAL_EDIT_REJECTED");
        return Ok((x,None))
    }
    let project=edited.project();
    let cand=match edited.materialize_mature_0x2c_native_pub_candidate(input) {
        Ok(x)=>x, Err(e)=>{
            let mut x=common;let b=blocked(e.code());
            x["status"]=b["status"].clone();x["writer_code"]=b["writer_code"].clone();
            return Ok((x,None))
        }
    };
    if cand.source_hash!=source_hash || cand.output_hash!=hash(&cand.bytes) || cand.bytes==input {
        let mut x=common;x["status"]=json!("INVALID_CANDIDATE_HASH");
        return Ok((x,None))
    }
    let reopened=match open_mature_0x2c_editor(&cand.bytes,cand.output_hash) {
        Ok(x)=>x,Err(_)=>{
            let mut x=common;x["status"]=json!("REOPEN_FAILED");return Ok((x,None))
        }
    };
    if !reopened.graph().stories.get(&cand.output_story_id).is_some_and(|s|s.text==after){
        let mut x=common;x["status"]=json!("TARGET_SEMANTIC_MISMATCH");return Ok((x,None))
    }
    let siblings=(||->Result<bool>{
        let oldbytes=pub_cfb::read_stream_reader(Cursor::new(input),pub_reader::QUILL_STREAM_PATH)?;
        let newbytes=pub_cfb::read_stream_reader(Cursor::new(&cand.bytes),pub_reader::QUILL_STREAM_PATH)?;
        let old=pub_quill::parse_confirmed_story_catalog(pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&oldbytes)?;
        let new=pub_quill::parse_confirmed_story_catalog(pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&newbytes)?;
        let mut old_ids=old.stories.iter().map(|s|s.syid.0).collect::<Vec<_>>();
        let mut new_ids=new.stories.iter().map(|s|s.syid.0).collect::<Vec<_>>();
        old_ids.sort_unstable();new_ids.sort_unstable();
        if old_ids!=new_ids || old_ids.windows(2).any(|p|p[0]==p[1]) ||
            initial.len()!=reopened.graph().stories.len(){return Ok(false)}
        let mut found=false;let mut matched=0usize;
        for s in &old.stories {
            let old_id=pub_reader::derive_pub_story_id(&source_hash,s.syid.0)?;
            let new_id=pub_reader::derive_pub_story_id(&cand.output_hash,s.syid.0)?;
            let Some(before_story)=initial.get(&old_id) else {continue};
            matched+=1;
            if old_id==id {found=new_id==cand.output_story_id;}
            else if !reopened.graph().stories.get(&new_id).is_some_and(|x|x.text==before_story.text) {
                return Ok(false)
            }
        }
        Ok(found && matched==initial.len())
    })();
    if !matches!(siblings,Ok(true)){
        let mut x=common;x["status"]=json!("SYID_OR_SIBLING_MISMATCH");return Ok((x,None))
    }
    let mut replay=match open_mature_0x2c_editor(input,source_hash) {
        Ok(x)=>x,Err(_)=>{
            let mut x=common;x["status"]=json!("REPLAY_OPEN_FAILED");return Ok((x,None))
        }
    };
    if replay.apply_project(&project).is_err(){
        let mut x=common;x["status"]=json!("REPLAY_APPLY_FAILED");return Ok((x,None))
    }
    let repeated=match replay.materialize_mature_0x2c_native_pub_candidate(input){
        Ok(x)=>x,Err(_)=>{
            let mut x=common;x["status"]=json!("REPLAY_WRITE_FAILED");return Ok((x,None))
        }
    };
    if repeated.bytes!=cand.bytes || hash(input)!=source_hash {
        let mut x=common;x["status"]=json!("REPLAY_BYTES_MISMATCH");return Ok((x,None))
    }
    let mut x=common;
    x["status"]=json!("HOSTED_PASS");
    x["source_sha256"]=json!(expected);
    x["candidate_sha256"]=json!(cand.output_hash.to_string());
    x["candidate_bytes"]=json!(cand.bytes.len());
    x["reader_reopened"]=json!(true);
    x["syid_siblings_preserved"]=json!(true);
    x["project_replay_byte_equal"]=json!(true);
    x["source_immutable"]=json!(true);
    x["native_publisher_acceptance"]=json!("NOT_EVALUATED");
    Ok((x,Some(cand.bytes)))
}
fn main()->Result<()> {
    let mut it=env::args().skip(1);
    let src=it.next().context("source argument")?;
    let expected=it.next().context("expected source SHA")?;
    let out=it.next().context("temporary candidate destination")?;
    let receipt=it.next().context("receipt destination")?;
    let size:usize=it.next().context("growth length")?.parse()?;
    let slot=it.next().context("insertion slot")?;
    ensure!(it.next().is_none(),"extra CLI arguments");
    ensure!(expected.len()==64 && expected.bytes().all(|c|c.is_ascii_hexdigit()),"bad SHA input");
    let source=fs::read(&src)?;
    ensure!(source.len()<=12*1024*1024,"source size limit");
    let (result,candidate)=probe(&source,&expected,size,&slot)?;
    if let Some(bytes)=candidate{fs::write(&out,bytes)?}
    let mut file=fs::OpenOptions::new().create_new(true).write(true).open(&receipt)?;
    file.write_all(&serde_json::to_vec_pretty(&result)?)?;
    file.write_all(b"\n")?;file.sync_all()?;
    println!("{}",serde_json::to_string(&json!({"status":result["status"]}))?);
    Ok(())
}
