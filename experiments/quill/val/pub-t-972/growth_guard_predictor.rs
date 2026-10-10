//! PUB-T-972: source-only FD insertion-boundary predicate on never-before-scored public PUB.
//! Static predictions are fully collected before any Writer invocation.
//! No raw PUB, Quill bytes, URL, story text or unsafe error reaches a public receipt.
use anyhow::{Context, Result, ensure};
use pub_editor::{Sha256Digest, open_mature_0x2c_editor};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::HashSet, env, fs, io::{Cursor, Write}};

fn hash(input: &[u8]) -> Sha256Digest {
    let mut h = [0u8; 32];
    h.copy_from_slice(&Sha256::digest(input));
    Sha256Digest::from_bytes(h)
}
fn safe_code(code: &str) -> &str {
    if !code.is_empty() && code.len() <= 64
        && code.bytes().all(|x| x.is_ascii_lowercase() || x == b'_') {
        code
    } else { "unclassified_writer_guard" }
}
fn blocked(code: &str) -> Value {
    json!({"status":"WRITER_BLOCKED","code":safe_code(code)})
}
fn failed(status: &str) -> Value {
    json!({"status":status})
}
#[derive(Clone)]
struct FdBoundary {
    position: u32,
    is_pp: bool,
}
struct ArmPlan {
    story_ordinal: usize,
    syid: u32,
    slot: &'static str,
    ascii_rank: usize,
    at_utf16: usize,
    len_utf16: usize,
    pp_hit: bool,
    pc_hit: bool,
    tokn_hit: bool,
    dose:usize,
    growth_class:&'static str,
    nearest_bytes: Option<u32>,
    before: String,
    after: String,
}

fn read_fd_bounds(
    quill: &[u8], catalog: &pub_quill::QuillStoryCatalog
) -> Result<Vec<FdBoundary>> {
    let descs=catalog.descriptor_nodes.iter()
        .flat_map(|node| node.descriptors.iter()).collect::<Vec<_>>();
    let text=descs.iter().copied()
        .filter(|d|d.name.value==*b"TEXT").collect::<Vec<_>>();
    ensure!(text.len()==1,"unique TEXT required");
    let start=text[0].data_offset.value;
    let end=start.checked_add(text[0].data_length.value).context("TEXT end")?;
    ensure!(usize::try_from(end)?<=quill.len(),"TEXT outside Quill");
    let mut out=Vec::new();
    let (mut has_pp,mut has_pc)=(false,false);
    for d in descs {
        let name=d.name.value;
        if name!=*b"FDPP" && name!=*b"FDPC" {continue}
        let is_pp=name==*b"FDPP";
        if is_pp {has_pp=true} else {has_pc=true}
        let first=usize::try_from(d.data_offset.value)?;
        let length=usize::try_from(d.data_length.value)?;
        let final_end=first.checked_add(length).context("FD descriptor size")?;
        let chunk=quill.get(first..final_end).context("FD outside Quill")?;
        ensure!(chunk.len()>=8,"FD header");
        let count=usize::from(u16::from_le_bytes([chunk[0],chunk[1]]));
        let min_len=8usize.checked_add(count.checked_mul(6).context("FD count")?)
            .context("FD frame")?;
        ensure!(chunk.len()>=min_len,"short FD frame");
        for i in 0..count {
            let at=8+i*4;
            let v=u32::from_le_bytes(chunk[at..at+4].try_into()?);
            ensure!(v>=start && v<=end,"FD boundary outside TEXT");
            out.push(FdBoundary{position:v,is_pp});
        }
    }
    ensure!(has_pp && has_pc,"missing FDPP/FDPC");
    Ok(out)
}


fn classify_growth(quill:&[u8],catalog:&pub_quill::QuillStoryCatalog,dose:usize)->Result<&'static str>{
    let descs=catalog.descriptor_nodes.iter().flat_map(|n|n.descriptors.iter()).collect::<Vec<_>>();
    let texts=descs.iter().filter(|d|d.name.value==*b"TEXT").collect::<Vec<_>>();
    ensure!(texts.len()==1,"unique TEXT");
    let text_end=usize::try_from(texts[0].data_offset.value)?
        .checked_add(usize::try_from(texts[0].data_length.value)?).context("text end")?;
    let anchor=descs.iter().filter(|d|d.name.value==*b"FDPP" || d.name.value==*b"FDPC")
        .filter_map(|d|usize::try_from(d.data_offset.value).ok())
        .filter(|&n|n>=text_end && n%512==0).min().context("no anchor")?;
    ensure!(text_end<=anchor && anchor<=quill.len(),"invalid anchor");
    for node in &catalog.descriptor_nodes {
        let lo=usize::try_from(node.source.offset)?;
        let hi=usize::try_from(node.source.end().context("source end")?)?;
        ensure!(!(lo<anchor && hi>text_end),"descriptor metadata intersects growth");
    }
    let growth=dose.checked_mul(2).context("growth overflow")?;
    if text_end.checked_add(growth).context("new text end")?>anchor{return Ok("CAPACITY")}
    let discard=anchor.checked_sub(growth).context("discard underflow")?;
    if discard<text_end{return Ok("CAPACITY")}
    for d in &descs{
        if d.name.value==*b"TEXT"{continue}
        let start=usize::try_from(d.data_offset.value)?;
        let end=start.checked_add(usize::try_from(d.data_length.value)?).context("descriptor end")?;
        if start<anchor && end>discard{
            let a=start.max(discard);let b=end.min(anchor);
            ensure!(a<b && b<=quill.len(),"bad descriptor intersection");
            return Ok(if quill[a..b].iter().any(|&v|v!=0){"GROWTH_UNKNOWN"}else{"GROWTH_DESCRIPTOR"})
        }
    }
    Ok(if quill[discard..anchor].iter().any(|&v|v!=0){"GROWTH_UNKNOWN"}else{"PASS"})
}

fn write_one(original: &[u8], source_sha: Sha256Digest, plan: &ArmPlan) -> Value {
    let mut editor=match open_mature_0x2c_editor(original,source_sha) {
        Ok(x)=>x,Err(_)=>return failed("SOURCE_REOPEN_FAILED")
    };
    let target_id=match pub_reader::derive_pub_story_id(&source_sha,plan.syid) {
        Ok(x)=>x,Err(_)=>return failed("TARGET_ID_UNAVAILABLE")
    };
    let original_graph=editor.graph().stories.clone();
    if !original_graph.get(&target_id).is_some_and(|x|x.text==plan.before) {
        return failed("STORY_ID_MISMATCH")
    }
    if editor.replace_story_text(target_id,plan.after.clone()).is_err() {
        return failed("CANONICAL_EDIT_REJECTED")
    }
    let project=editor.project();
    let candidate=match editor.materialize_mature_0x2c_native_pub_candidate(original) {
        Ok(x)=>x,Err(e)=>return blocked(e.code())
    };
    if candidate.source_hash!=source_sha || candidate.output_hash!=hash(&candidate.bytes)
        || candidate.bytes==original {return failed("INVALID_CANDIDATE")}
    let reopened=match open_mature_0x2c_editor(&candidate.bytes,candidate.output_hash) {
        Ok(x)=>x,Err(_)=>return failed("READER_REOPEN_FAILED")
    };
    let new_id=match pub_reader::derive_pub_story_id(&candidate.output_hash,plan.syid) {
        Ok(x)=>x,Err(_)=>return failed("OUTPUT_ID_UNAVAILABLE")
    };
    if candidate.output_story_id!=new_id ||
        !reopened.graph().stories.get(&new_id).is_some_and(|s|s.text==plan.after) {
        return failed("TARGET_SEMANTIC_MISMATCH")
    }
    let siblings=(|| -> Result<bool>{
        let source_q=pub_cfb::read_stream_reader(
            Cursor::new(original),pub_reader::QUILL_STREAM_PATH)?;
        let out_q=pub_cfb::read_stream_reader(
            Cursor::new(&candidate.bytes),pub_reader::QUILL_STREAM_PATH)?;
        let old=pub_quill::parse_confirmed_story_catalog(
            pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &source_q)?;
        let new=pub_quill::parse_confirmed_story_catalog(
            pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &out_q)?;
        let mut old_ids=old.stories.iter().map(|s|s.syid.0).collect::<Vec<_>>();
        let mut new_ids=new.stories.iter().map(|s|s.syid.0).collect::<Vec<_>>();
        old_ids.sort_unstable();new_ids.sort_unstable();
        if old_ids!=new_ids || old_ids.windows(2).any(|w|w[0]==w[1])
            || original_graph.len()!=reopened.graph().stories.len() {
            return Ok(false)
        }
        let mut matched=0usize;let mut found=false;
        for s in &old.stories {
            let oi=pub_reader::derive_pub_story_id(&source_sha,s.syid.0)?;
            let ni=pub_reader::derive_pub_story_id(&candidate.output_hash,s.syid.0)?;
            let Some(before)=original_graph.get(&oi) else {continue};
            matched+=1;
            if s.syid.0==plan.syid {found=oi==target_id && ni==new_id}
            else if !reopened.graph().stories.get(&ni)
                .is_some_and(|now|now.text==before.text){return Ok(false)}
        }
        Ok(found && matched==original_graph.len())
    })();
    if !matches!(siblings,Ok(true)){return failed("SYID_OR_SIBLING_MISMATCH")}
    let mut replay=match open_mature_0x2c_editor(original,source_sha) {
        Ok(x)=>x,Err(_)=>return failed("PROJECT_SOURCE_OPEN_FAILED")
    };
    if replay.apply_project(&project).is_err(){return failed("PROJECT_APPLY_FAILED")}
    let identical=match replay.materialize_mature_0x2c_native_pub_candidate(original) {
        Ok(x)=>x,Err(_)=>return failed("PROJECT_WRITER_FAILED")
    };
    if identical.bytes!=candidate.bytes || hash(original)!=source_sha {
        return failed("PROJECT_BYTE_MISMATCH")
    }
    json!({"status":"HOSTED_PASS","candidate_sha256":candidate.output_hash.to_string(),
        "reader_reopened":true,"syid_siblings_preserved":true,
        "project_replay_byte_equal":true,"source_immutable":true,
        "native_publisher_acceptance":"NOT_EVALUATED"})
}

fn probe(source: &[u8], expected_sha:&str) -> Result<Value> {
    let digest=hash(source);
    ensure!(digest.to_string()==expected_sha,"source SHA drift");
    ensure!(source.starts_with(&[0xd0,0xcf,0x11,0xe0,0xa1,0xb1,0x1a,0xe1]),"CFB signature");
    let mut out=json!({"schema":"sk1.pub-t-972.source.v1",
        "source_sha256":expected_sha,"source_bytes":source.len(),
        "status":"NOT_EVALUATED","static_predictions_built_before_writer":false,
        "publisher_native_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":false,
        "stories":[],"writer_arm_count":0,"source_immutable":false});
    let editor=match open_mature_0x2c_editor(source,digest) {
        Ok(x)=>x,Err(_)=>{out["status"]=json!("SOURCE_OPEN_BLOCKED");return Ok(out)}
    };
    let chosen=editor.graph().stories.iter()
        .filter(|(id,story)|editor.can_replace_story_text(**id).is_ok()
           &&story.text.chars().any(|c|c.is_ascii_alphanumeric()))
        .take(3).map(|(id,s)|(*id,s.text.clone())).collect::<Vec<_>>();
    if chosen.is_empty(){
        out["status"]=json!("NO_ELIGIBLE_STORY");return Ok(out)
    }
    let quill=match pub_cfb::read_stream_reader(
        Cursor::new(source),pub_reader::QUILL_STREAM_PATH) {
        Ok(x)=>x,Err(_)=>{out["status"]=json!("QUILL_READ_BLOCKED");return Ok(out)}
    };
    let catalog=match pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &quill) {
        Ok(x)=>x,Err(_)=>{out["status"]=json!("QUILL_PARSE_BLOCKED");return Ok(out)}
    };
    let boundaries=match read_fd_bounds(&quill,&catalog){
        Ok(x)=>x,Err(_)=>{out["status"]=json!("FD_STRUCTURE_BLOCKED");return Ok(out)}
    };
    // Mandatory: collect ALL deterministic source-only predictions here BEFORE
    // the first original Writer invocation; outcome labels cannot influence them.
    let mut plans=Vec::new();
    for (story_ordinal,(id,before)) in chosen.into_iter().enumerate(){
        let matches=catalog.stories.iter().filter(|s|
            pub_reader::derive_pub_story_id(&digest,s.syid.0)
                .is_ok_and(|candidate_id|candidate_id==id)).collect::<Vec<_>>();
        if matches.len()!=1 {
            out["status"]=json!("STORY_ID_AMBIGUOUS");return Ok(out)
        }
        let story=matches[0];
        let tokn_hit=catalog.descriptor_nodes.iter()
            .flat_map(|node|node.descriptors.iter()).any(|d|
              d.name.value==*b"TOKN" && u16::try_from(story.index).ok()
                .is_some_and(|idx|d.option_a.value==idx));
        let letters=before.char_indices()
            .filter(|(_,c)|c.is_ascii_alphanumeric()).collect::<Vec<_>>();
        let total=letters.len();
        let choices=[("first",0usize),("second",1usize.min(total-1)),
           ("middle",(total-1)/2),("last",total-1)];
        let growths=[(32usize,classify_growth(&quill,&catalog,32)?),
                     (128usize,classify_growth(&quill,&catalog,128)?),
                     (256usize,classify_growth(&quill,&catalog,256)?)];
        let mut used=HashSet::new();
        for (slot,rank) in choices {
            let (byte_offset,ch)=letters[rank];
            if !used.insert(byte_offset){continue}
            let at_utf16=before[..byte_offset].encode_utf16().count();
            let abs=usize::try_from(story.text_source.offset)?
                .checked_add(at_utf16.checked_mul(2).context("utf16 position")?)
                .context("story absolute position")?;
            let abs=u32::try_from(abs)?;
            let pp_hit=boundaries.iter().any(|b|b.is_pp && b.position==abs);
            let pc_hit=boundaries.iter().any(|b|!b.is_pp && b.position==abs);
            let nearest_bytes=boundaries.iter().map(|b|b.position.abs_diff(abs)).min();
            let previous=before[..byte_offset].chars().last();
            let marker=['X','Q','Z'].into_iter()
                .find(|c|Some(*c)!=previous && *c!=ch).context("marker unavailable")?;
            for &(dose,growth_class) in &growths{
                let mut after=before.clone();
                after.insert_str(byte_offset,&marker.to_string().repeat(dose));
                plans.push(ArmPlan{story_ordinal,syid:story.syid.0,slot,ascii_rank:rank,
                    at_utf16,len_utf16:before.encode_utf16().count(),
                    pp_hit,pc_hit,tokn_hit,dose,growth_class,nearest_bytes,
                    before:before.clone(),after});
            }
        }
    }
    out["static_predictions_built_before_writer"]=json!(true);
    let mut stories=Vec::new();
    let mut total_arms=0usize;
    for ordinal in 0..3usize {
        let selected=plans.iter().filter(|x|x.story_ordinal==ordinal).collect::<Vec<_>>();
        if selected.is_empty(){continue}
        let first=selected[0];
        let mut arms=Vec::new();
        for arm in selected {
            let result=write_one(source,digest,arm);
            total_arms+=1;
            arms.push(json!({"slot":arm.slot,"ascii_rank":arm.ascii_rank,
                "at_utf16":arm.at_utf16,"story_utf16_length":arm.len_utf16,
                "predicted_fd_hit":arm.pp_hit||arm.pc_hit,
                "source_tokn_hit":arm.tokn_hit,
                "dose_utf16":arm.dose,
                "source_growth_class":arm.growth_class,
                "predicted_first_class":if arm.tokn_hit {"TOKN"} else if arm.pp_hit||arm.pc_hit {"FD"} else {arm.growth_class},
                "fdpp_hit":arm.pp_hit,"fdpc_hit":arm.pc_hit,
                "nearest_fd_boundary_distance_bytes":arm.nearest_bytes,
                "writer":result}))
        }
        stories.push(json!({"story_ordinal":ordinal,"syid":first.syid,
          "story_utf16_length":first.len_utf16,"arms":arms}));
    }
    out["status"]=json!("EVALUATED");
    out["stories"]=json!(stories);
    out["writer_arm_count"]=json!(total_arms);
    out["source_immutable"]=json!(hash(source)==digest);
    Ok(out)
}
fn main()->Result<()>{
    let mut it=env::args().skip(1);
    let src=it.next().context("source path")?;
    let expected=it.next().context("SHA input")?;
    let receipt=it.next().context("receipt path")?;
    ensure!(it.next().is_none(),"unregistered argument");
    ensure!(expected.len()==64 && expected.bytes().all(|x|x.is_ascii_hexdigit()),"bad digest");
    let raw=fs::read(src)?;
    ensure!(raw.len()<=12*1024*1024,"file limit");
    let proof=match probe(&raw,&expected){
        Ok(x)=>x,Err(_)=>json!({"schema":"sk1.pub-t-972.source.v1",
           "source_sha256":expected,"source_bytes":raw.len(),
           "status":"STATIC_PROBE_BLOCKED",
           "static_predictions_built_before_writer":false,
           "publisher_native_acceptance":"NOT_EVALUATED",
           "product_pub_download_authorized":false,
           "stories":[],"writer_arm_count":0,"source_immutable":hash(&raw).to_string()==expected})
    };
    let mut f=fs::OpenOptions::new().create_new(true).write(true).open(receipt)?;
    f.write_all(&serde_json::to_vec_pretty(&proof)?)?;f.write_all(b"\n")?;
    f.sync_all()?;
    println!("{}",serde_json::to_string(&json!({"status":proof["status"]}))?);
    Ok(())
}
