//! SK1-CFB-DIAG-PUB-T-957: inverse +/-1 Story compositions using ONLY pinned rar2 Writer.
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



// NEW FOR PUB-T-957: inspect source vs fully reverted in memory, no serialization.
// Only fixed classifier labels and counts are emitted; never raw CFB/Quill data.
fn inspect_reverted_cfb(source: &[u8], final_pub: &[u8]) -> Result<Value> {
    use std::collections::BTreeMap;
    let mut original=BTreeMap::new();
    let mut candidate=BTreeMap::new();
    for e in pub_cfb::inspect_reader(Cursor::new(source))?.entries {
        ensure!(original.insert(e.path.clone(),e).is_none(),"duplicate source CFB path");
    }
    for e in pub_cfb::inspect_reader(Cursor::new(final_pub))?.entries {
        ensure!(candidate.insert(e.path.clone(),e).is_none(),"duplicate final CFB path");
    }
    let mut missing_paths=0usize;
    let mut new_paths=0usize;
    let mut type_changes=0usize;
    let mut non_quill_streams_checked=0usize;
    let mut non_quill_streams_changed=0usize;
    let mut quill_streams_found=0usize;
    let mut quill_bytes_equal=false;
    for (path, original_entry) in &original {
        let Some(new_entry)=candidate.get(path) else {
            missing_paths+=1;
            continue;
        };
        if original_entry.kind!=new_entry.kind {
            type_changes+=1;
            continue;
        }
        if original_entry.kind==pub_cfb::EntryKind::Stream {
            let before=pub_cfb::read_stream_reader(Cursor::new(source),path)?;
            let after=pub_cfb::read_stream_reader(Cursor::new(final_pub),path)?;
            if path==pub_reader::QUILL_STREAM_PATH {
                quill_streams_found+=1;
                quill_bytes_equal=before==after;
            } else {
                non_quill_streams_checked+=1;
                if before!=after {non_quill_streams_changed+=1;}
            }
        }
    }
    for path in candidate.keys() {
        if !original.contains_key(path){new_paths+=1;}
    }
    ensure!(quill_streams_found==1,"missing unique source/final Quill");
    let old_quill=pub_cfb::read_stream_reader(
        Cursor::new(source),pub_reader::QUILL_STREAM_PATH)?;
    let new_quill=pub_cfb::read_stream_reader(
        Cursor::new(final_pub),pub_reader::QUILL_STREAM_PATH)?;
    let old_catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&old_quill)?;
    let new_catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&new_quill)?;
    let source_story_ids=old_catalog.stories.iter()
        .map(|s|s.syid.0).collect::<Vec<_>>();
    let final_story_ids=new_catalog.stories.iter()
        .map(|s|s.syid.0).collect::<Vec<_>>();
    let same_strs_lengths=old_catalog.strs.lengths.iter().map(|s|s.value)
        .eq(new_catalog.strs.lengths.iter().map(|s|s.value));
    let same_text_payload=old_catalog.text.bytes==new_catalog.text.bytes;
    let left=old_catalog.descriptor_nodes.iter()
        .flat_map(|n|n.descriptors.iter()).collect::<Vec<_>>();
    let right=new_catalog.descriptor_nodes.iter()
        .flat_map(|n|n.descriptors.iter()).collect::<Vec<_>>();
    let matched_descriptor_sequence=left.len()==right.len() &&
        left.iter().zip(&right).all(|(a,b)|
            a.name.value==b.name.value && a.option_a.value==b.option_a.value);
    let mut altered_chunks=0usize;
    let mut altered_chunk_by_kind=BTreeMap::<String,usize>::new();
    let mut altered_descriptor_offset_count=0usize;
    let mut altered_descriptor_length_count=0usize;
    let mut altered_descriptor_options_count=0usize;
    let mut equal_descriptor_payloads=0usize;
    if matched_descriptor_sequence {
        for (a,b) in left.iter().zip(&right) {
            let ast:usize=usize::try_from(a.data_offset.value)?;
            let bst:usize=usize::try_from(b.data_offset.value)?;
            let alen:usize=usize::try_from(a.data_length.value)?;
            let blen:usize=usize::try_from(b.data_length.value)?;
            let ax=ast.checked_add(alen).context("original chunk overflow")?;
            let bx=bst.checked_add(blen).context("final chunk overflow")?;
            let ap=old_quill.get(ast..ax).context("original chunk outside Quill")?;
            let bp=new_quill.get(bst..bx).context("final chunk outside Quill")?;
            if a.data_offset.value!=b.data_offset.value {
                altered_descriptor_offset_count+=1;
            }
            if a.data_length.value!=b.data_length.value {
                altered_descriptor_length_count+=1;
            }
            if a.option_b.value!=b.option_b.value || a.option_c.value!=b.option_c.value
                || a.bit_type.value!=b.bit_type.value {
                altered_descriptor_options_count+=1;
            }
            if ap!=bp {
                altered_chunks+=1;
                // Whitelist the only kinds allowed into public JSON.
                let name=a.name.value;
                let cat=if name==*b"TEXT"{"TEXT"}
                else if name==*b"SYID"{"SYID"}
                else if name==*b"STRS"{"STRS"}
                else if name==*b"FDPP"{"FDPP"}
                else if name==*b"FDPC"{"FDPC"}
                else if name==*b"BTEP"{"BTEP"}
                else if name==*b"BTEC"{"BTEC"}
                else if name==*b"TOKN"{"TOKN"}
                else if name==*b"TCD "{"TCD"}
                else {"OTHER"};
                *altered_chunk_by_kind.entry(cat.to_owned()).or_default()+=1;
            } else {
                equal_descriptor_payloads+=1;
            }
        }
    }
    let all_logical_streams_equal=missing_paths==0 && new_paths==0
        && type_changes==0 && non_quill_streams_changed==0 && quill_bytes_equal;
    let whole_file_equal=source==final_pub;
    ensure!(!whole_file_equal || all_logical_streams_equal,
        "whole-file equal but logical CFB differs");
    Ok(json!({
        "schema":"sk1.cfb-diag-pub-t-957.diff.v1",
        "source_file_bytes":source.len(),
        "final_file_bytes":final_pub.len(),
        "source_directory_entries":original.len(),
        "final_directory_entries":candidate.len(),
        "missing_cfb_paths":missing_paths,
        "added_cfb_paths":new_paths,
        "cfb_entry_type_changes":type_changes,
        "non_quill_streams_checked":non_quill_streams_checked,
        "non_quill_streams_changed":non_quill_streams_changed,
        "quill_streams_found":quill_streams_found,
        "quill_bytes_equal":quill_bytes_equal,
        "all_logical_streams_equal":all_logical_streams_equal,
        "physical_only_container_difference":!whole_file_equal && all_logical_streams_equal,
        "whole_file_equal":whole_file_equal,
        "source_quill_bytes":old_quill.len(),
        "final_quill_bytes":new_quill.len(),
        "source_quill_sha256":sha256(&old_quill).to_string(),
        "final_quill_sha256":sha256(&new_quill).to_string(),
        "quill_differing_byte_positions_equal_len":if old_quill.len()==new_quill.len(){
            json!(old_quill.iter().zip(&new_quill).filter(|(a,b)|a!=b).count())
        }else{Value::Null},
        "same_quill_story_syid_sequence":source_story_ids==final_story_ids,
        "same_quill_story_utf16_lengths":same_strs_lengths,
        "same_quill_TEXT_payload_bytes":same_text_payload,
        "source_quill_descriptor_count":left.len(),
        "final_quill_descriptor_count":right.len(),
        "matched_descriptor_sequence":matched_descriptor_sequence,
        "altered_chunk_payload_count":if matched_descriptor_sequence{json!(altered_chunks)}
            else{Value::Null},
        "equal_chunk_payload_count":if matched_descriptor_sequence{json!(equal_descriptor_payloads)}
            else{Value::Null},
        "altered_chunks_by_kind":altered_chunk_by_kind,
        "altered_descriptor_offsets":if matched_descriptor_sequence{
            json!(altered_descriptor_offset_count)}else{Value::Null},
        "altered_descriptor_lengths":if matched_descriptor_sequence{
            json!(altered_descriptor_length_count)}else{Value::Null},
        "altered_descriptor_options":if matched_descriptor_sequence{
            json!(altered_descriptor_options_count)}else{Value::Null},
        "publisher_native_acceptance":"NOT_EVALUATED",
        "source_pub_output_authorized":false
    }))
}

fn inspect_source(source: &[u8], expected_sha: &str) -> Result<Value> {
    ensure!(sha256(source).to_string()==expected_sha, "source SHA drift");
    let source_hash=sha256(source);
    let mut report=json!({
        "schema":"sk1.cfb-diag-pub-t-957.inverse.v1",
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
                "both_final_byte_equal":Value::Null,
                "insert_delete_cfb":Value::Null,
                "delete_insert_cfb":Value::Null
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
                    pair["insert_delete_cfb"]=inspect_reverted_cfb(source,
                        reverse_insert.bytes.as_ref().context("missing inverse inserted bytes")?)?;
                    pair["insert_delete_returns_original_bytes"]=json!(
                        reverse_insert.bytes.as_ref().is_some_and(|bytes|bytes==source));
                }
                if delete_insert_pass{
                    pair["delete_insert_cfb"]=inspect_reverted_cfb(source,
                        reverse_delete.bytes.as_ref().context("missing inverse deleted bytes")?)?;
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
