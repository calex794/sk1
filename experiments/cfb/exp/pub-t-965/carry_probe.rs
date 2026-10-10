//! SK1-CFB-DIAG-PUB-T-965: inverse +/-1 Story compositions using ONLY pinned rar2 Writer.
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



// NEW FOR PUB-T-965: inspect source vs fully reverted in memory, no serialization.
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

    // SYID +0 has a long-standing *allocator-high-water candidate* model,
    // NOT a known Microsoft name or a universal per-edit counter. Localize
    // every Quill byte delta to the exact persisted SYID first DWORD if true.
    let source_syid_first_dword=old_catalog.syid.header.value;
    let final_syid_first_dword=new_catalog.syid.header.value;
    let source_syid_count=old_catalog.syid.count.value;
    let final_syid_count=new_catalog.syid.count.value;
    let syid_live_ids_equal=old_catalog.syid.ids.iter().map(|s|s.value.0)
        .eq(new_catalog.syid.ids.iter().map(|s|s.value.0));
    let mut syid_header_offset=None;
    if matched_descriptor_sequence {
        let old_syid=left.iter().filter(|d|d.name.value==*b"SYID")
            .collect::<Vec<_>>();
        let new_syid=right.iter().filter(|d|d.name.value==*b"SYID")
            .collect::<Vec<_>>();
        if old_syid.len()==1 && new_syid.len()==1 &&
           old_syid[0].data_offset.value==new_syid[0].data_offset.value &&
           old_syid[0].data_length.value==new_syid[0].data_length.value &&
           old_syid[0].data_length.value>=8 {
            syid_header_offset=Some(usize::try_from(old_syid[0].data_offset.value)?);
        }
    }
    let mut syid_header_changed_bytes=Value::Null;
    let mut quill_differing_bytes_outside_syid_header=Value::Null;
    if let Some(offset)=syid_header_offset {
        if old_quill.len()==new_quill.len() {
            let mut in_header=0usize;
            let mut outside_header=0usize;
            for (i,(a,b)) in old_quill.iter().zip(&new_quill).enumerate() {
                if a!=b {
                    if i>=offset && i<offset+4 {in_header+=1;}
                    else {outside_header+=1;}
                }
            }
            syid_header_changed_bytes=json!(in_header);
            quill_differing_bytes_outside_syid_header=json!(outside_header);
        }
    }
    let all_logical_streams_equal=missing_paths==0 && new_paths==0
        && type_changes==0 && non_quill_streams_changed==0 && quill_bytes_equal;
    let whole_file_equal=source==final_pub;
    ensure!(!whole_file_equal || all_logical_streams_equal,
        "whole-file equal but logical CFB differs");
    Ok(json!({
        "schema":"sk1.cfb-diag-pub-t-965.diff.v1",
        "source_syid_first_dword":source_syid_first_dword,
        "final_syid_first_dword":final_syid_first_dword,
        "syid_first_dword_delta":i64::from(final_syid_first_dword)-i64::from(source_syid_first_dword),
        "same_syid_live_ids":syid_live_ids_equal,
        "same_syid_count":source_syid_count==final_syid_count,
        "syid_first_dword_changed_bytes":syid_header_changed_bytes,
        "quill_changed_bytes_outside_syid_first_dword":quill_differing_bytes_outside_syid_header,

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

fn physical_residue(source: &[u8], final_pub: &[u8]) -> Value {
    let overlap=source.len().min(final_pub.len());
    let changed=source[..overlap].iter().zip(&final_pub[..overlap])
        .filter(|(a,b)|a!=b).count();
    json!({
        "source_file_length":source.len(),
        "final_file_length":final_pub.len(),
        "equal_length":source.len()==final_pub.len(),
        "changed_same_offset_bytes":changed,
        "extra_bytes":source.len().max(final_pub.len())-overlap,
        "whole_file_equal":source==final_pub
    })
}
const SYNTHETIC_HEADERS:[u32;9]=[
    0x0000_00fd, 0x0000_00fe, 0x0000_00ff,
    0x0000_fffd, 0x0000_fffe, 0x0000_ffff,
    0xffff_fffd, 0xffff_fffe, 0xffff_ffff
];

fn expected_source_header(sha: &str) -> Result<u32> {
    match sha {
        "155f8fd8c191851e4380ab1557638aeabb34b2257fa12a7748ab00b09edb74ba" => Ok(22),
        "1e7f38b3ce1d0d956815992b15d361c405fc4bbdced5cdabb3c4581327cc183e" => Ok(12),
        "712e1db9cefd0af613b12fb776720ac5d67ebe772468f2e47cb26a1f2e6ce28a" => Ok(2),
        _ => anyhow::bail!("source not preregistered"),
    }
}

fn syid_header(pub_bytes: &[u8]) -> Result<u32> {
    let stream=pub_cfb::read_stream_reader(Cursor::new(pub_bytes),pub_reader::QUILL_STREAM_PATH)?;
    let catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &stream)?;
    Ok(catalog.syid.header.value)
}

fn expected_header_diff(a:u32,b:u32) -> usize {
    a.to_le_bytes().iter().zip(b.to_le_bytes().iter()).filter(|(x,y)|x!=y).count()
}

fn summarize_final(synthetic:&[u8], initial:u32, final_pub:&[u8]) -> Result<Value> {
    let raw=physical_residue(synthetic,final_pub);
    let diff=inspect_reverted_cfb(synthetic,final_pub)?;
    let expected=initial.checked_add(2);
    let expected_bytes=expected.map(|end|expected_header_diff(initial,end));
    let counted=raw["changed_same_offset_bytes"].as_u64().context("raw changed count")?;
    let extra=raw["extra_bytes"].as_u64().context("extra")?;
    let correct=expected.is_some_and(|v|diff["final_syid_first_dword"]==json!(v)) &&
        expected_bytes.is_some_and(|n|counted==n as u64) &&
        raw["equal_length"]==true && extra==0 &&
        diff["syid_first_dword_delta"]==2 &&
        diff["syid_first_dword_changed_bytes"]==json!(counted) &&
        diff["quill_changed_bytes_outside_syid_first_dword"]==0 &&
        diff["non_quill_streams_changed"]==0 &&
        diff["same_quill_TEXT_payload_bytes"]==true &&
        diff["same_quill_story_syid_sequence"]==true &&
        diff["matched_descriptor_sequence"]==true;
    Ok(json!({
        "initial_header":initial,
        "final_header":diff["final_syid_first_dword"],
        "delta":diff["syid_first_dword_delta"],
        "predicted_final_header":expected,
        "predicted_changed_header_bytes":expected_bytes,
        "whole_pub_equal_length":raw["equal_length"],
        "whole_pub_raw_changed_bytes":counted,
        "whole_pub_extra_bytes":extra,
        "quill_changed_bytes":diff["quill_differing_byte_positions_equal_len"],
        "syid_first_dword_changed_bytes":diff["syid_first_dword_changed_bytes"],
        "quill_changed_bytes_outside_syid_first_dword":diff["quill_changed_bytes_outside_syid_first_dword"],
        "non_quill_streams_changed":diff["non_quill_streams_changed"],
        "same_quill_TEXT_payload_bytes":diff["same_quill_TEXT_payload_bytes"],
        "same_quill_story_syid_sequence":diff["same_quill_story_syid_sequence"],
        "matched_descriptor_sequence":diff["matched_descriptor_sequence"],
        "predicted_raw_exact_match":correct,
        "publisher_native_acceptance":"NOT_EVALUATED"
    }))
}

fn run_arm(synthetic:&[u8], syid:u32, initial:u32,
           first:Step, intermediate_text:&str, original_text:&str) -> Result<Value> {
    let mut result=json!({
        "first":first.receipt,
        "first_header":Value::Null,
        "second": {"status":"NOT_ATTEMPTED"},
        "final":Value::Null
    });
    let Some(mid)=first.bytes else {return Ok(result)};
    result["first_header"]=json!(syid_header(&mid)?);
    let second=step(&mid,syid,intermediate_text,original_text);
    result["second"]=second.receipt;
    if let Some(fin)=second.bytes {
        result["final"]=summarize_final(synthetic,initial,&fin)?;
    }
    Ok(result)
}

fn mutate_header_only(original:&[u8],source_counter:u32,new_counter:u32) -> Result<(Vec<u8>,Value)> {
    let quill=pub_cfb::read_stream_reader(Cursor::new(original),pub_reader::QUILL_STREAM_PATH)?;
    let catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&quill)?;
    ensure!(catalog.syid.header.value==source_counter,"source header drift");
    let offset=usize::try_from(catalog.syid.header.source.offset)?;
    ensure!(offset.checked_add(4).is_some_and(|end|end<=quill.len()),"header offset invalid");
    let mut modified=quill.clone();
    modified[offset..offset+4].copy_from_slice(&new_counter.to_le_bytes());
    let synthetic=pub_cfb::replace_stream_reader(
        Cursor::new(original),pub_reader::QUILL_STREAM_PATH,&modified)?;
    let raw=physical_residue(original,&synthetic);
    let predicted=expected_header_diff(source_counter,new_counter);
    let exact=raw["equal_length"]==true &&
        raw["extra_bytes"]==0 &&
        raw["changed_same_offset_bytes"]==json!(predicted) &&
        syid_header(&synthetic)?==new_counter &&
        pub_cfb::read_stream_reader(Cursor::new(&synthetic),pub_reader::QUILL_STREAM_PATH)?==modified;
    Ok((synthetic,json!({
        "source_header":source_counter,"patched_header":new_counter,
        "changed_raw_bytes":raw["changed_same_offset_bytes"],
        "expected_changed_header_bytes":predicted,
        "equal_length":raw["equal_length"],
        "extra_bytes":raw["extra_bytes"],
        "exact_header_only":exact
    })))
}

fn measure_variant(original:&[u8],source_counter:u32,syid:u32,before:&str,
                   insert_text:&str,delete_text:&str,value:u32) -> Result<Value> {
    let (synthetic,patch)=mutate_header_only(original,source_counter,value)?;
    let mut record=json!({
        "variant_header":value, "patch":patch,
        "status":"NOT_EVALUATED",
        "synthetic_sha256":sha256(&synthetic).to_string(),
        "semantic_source_reopen":false,
        "insert_delete":Value::Null,
        "delete_insert":Value::Null
    });
    if record["patch"]["exact_header_only"]!=true {
        record["status"]=json!("SYNTHETIC_PATCH_NOT_EXACT");
        return Ok(record);
    }
    let old_hash=sha256(original);
    let synthetic_hash=sha256(&synthetic);
    let old_editor=match open_mature_0x2c_editor(original,old_hash) {
        Ok(x)=>x, Err(_)=>{
            record["status"]=json!("ORIGINAL_EDITOR_OPEN_BLOCKED");return Ok(record);
        }
    };
    let synthetic_editor=match open_mature_0x2c_editor(&synthetic,synthetic_hash) {
        Ok(x)=>x, Err(_)=>{
            record["status"]=json!("SYNTHETIC_EDITOR_OPEN_BLOCKED");return Ok(record);
        }
    };
    let old_quill=pub_cfb::read_stream_reader(Cursor::new(original),pub_reader::QUILL_STREAM_PATH)?;
    let new_quill=pub_cfb::read_stream_reader(Cursor::new(&synthetic),pub_reader::QUILL_STREAM_PATH)?;
    let old_cat=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&old_quill)?;
    let new_cat=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&new_quill)?;
    let original_ids:Vec<_>=old_cat.stories.iter().map(|s|s.syid.0).collect();
    let synthetic_ids:Vec<_>=new_cat.stories.iter().map(|s|s.syid.0).collect();
    let mut all_agree=original_ids==synthetic_ids &&
        old_editor.graph().stories.len()==synthetic_editor.graph().stories.len();
    if all_agree {
        for s in &old_cat.stories {
            let original_id=pub_reader::derive_pub_story_id(&old_hash,s.syid.0)?;
            let candidate_id=pub_reader::derive_pub_story_id(&synthetic_hash,s.syid.0)?;
            if let Some(orig)=old_editor.graph().stories.get(&original_id) {
                if !synthetic_editor.graph().stories.get(&candidate_id)
                    .is_some_and(|after|after.text==orig.text) {
                    all_agree=false;break;
                }
            }
        }
    }
    if !all_agree {
        record["status"]=json!("SYNTHETIC_STORY_OR_SYID_MISMATCH");
        return Ok(record);
    }
    record["semantic_source_reopen"]=json!(true);
    let first_insert=step(&synthetic,syid,before,insert_text);
    let first_delete=step(&synthetic,syid,before,delete_text);
    record["insert_delete"]=run_arm(&synthetic,syid,value,
        first_insert,insert_text,before)?;
    record["delete_insert"]=run_arm(&synthetic,syid,value,
        first_delete,delete_text,before)?;
    record["status"]=json!("MEASURED");
    Ok(record)
}

fn inspect_source(source: &[u8], expected_sha: &str) -> Result<Value> {
    ensure!(sha256(source).to_string()==expected_sha,"source SHA mismatch");
    let source_counter=expected_source_header(expected_sha)?;
    let original_hash=sha256(source);
    let quill=pub_cfb::read_stream_reader(Cursor::new(source),pub_reader::QUILL_STREAM_PATH)?;
    let catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&quill)?;
    ensure!(catalog.syid.header.value==source_counter,"source header control changed");
    let editor=open_mature_0x2c_editor(source,original_hash)?;
    let eligible=editor.graph().stories.iter()
        .filter(|(id,s)|editor.can_replace_story_text(**id).is_ok()
             && s.text.chars().any(|c|c.is_ascii_alphanumeric()))
        .take(3).map(|(id,s)|(*id,s.text.clone())).collect::<Vec<_>>();
    let (id,before)=eligible.first().context("no eligible Story")?;
    let mut matches=catalog.stories.iter()
       .filter(|s|pub_reader::derive_pub_story_id(&original_hash,s.syid.0)
           .is_ok_and(|story_id|story_id==*id));
    let syid=matches.next().context("first eligible Story missing SYID")?.syid.0;
    ensure!(matches.next().is_none(),"ambiguous Story");
    let letters=before.char_indices().filter(|(_,c)|c.is_ascii_alphanumeric()).collect::<Vec<_>>();
    ensure!(letters.len()>1,"no second ASCII char");
    let (offset,ch)=letters[1];
    ensure!(before[..offset].encode_utf16().count()==1,"predeclared UTF16 offset changed");
    let prev=before[..offset].chars().last();
    let marker=['X','Q','Z'].into_iter().find(|c|Some(*c)!=prev && *c!=ch)
        .context("no safe marker")?;
    let mut insert_text=before.clone();insert_text.insert(offset,marker);
    let mut delete_text=before.clone();delete_text.remove(offset);
    let mut report=json!({
        "schema":"sk1.cfb-exp-pub-t-965.source.v1",
        "source_sha256":expected_sha,"original_syid_first_dword":source_counter,
        "story_ordinal":0,"slot":"second","offset_utf16":1,
        "source_bytes":source.len(),
        "status":"BASELINE_NOT_EVALUATED",
        "baseline":Value::Null,
        "variants":[],
        "native_publisher_acceptance":"NOT_EVALUATED"
    });
    let base_insert=step(source,syid,before,&insert_text);
    let base_delete=step(source,syid,before,&delete_text);
    let baseline_insert=run_arm(source,syid,source_counter,base_insert,&insert_text,before)?;
    let baseline_delete=run_arm(source,syid,source_counter,base_delete,&delete_text,before)?;
    let baseline_pass=baseline_insert["second"]["status"]=="HOSTED_PASS" &&
        baseline_delete["second"]["status"]=="HOSTED_PASS";
    report["baseline"]=json!({
        "insert_delete":baseline_insert,
        "delete_insert":baseline_delete,"both_pass":baseline_pass
    });
    if !baseline_pass {
        report["status"]=json!("BASELINE_DRIFT");
        return Ok(report);
    }
    report["status"]=json!("EVALUATED");
    let mut variants=Vec::new();
    for value in SYNTHETIC_HEADERS {
        let item=match measure_variant(source,source_counter,syid,before,&insert_text,&delete_text,value) {
            Ok(x)=>x,
            Err(_)=>json!({"variant_header":value,"status":"VARIANT_PROBE_ERROR"})
        };
        variants.push(item);
    }
    report["variants"]=json!(variants);
    ensure!(sha256(source).to_string()==expected_sha,"source bytes mutated");
    Ok(report)
}
fn main()->Result<()> {
    let mut it=env::args().skip(1);
    let input=it.next().context("source input")?;
    let expected=it.next().context("expected sha")?;
    let output=it.next().context("receipt path")?;
    ensure!(it.next().is_none(),"unexpected extra args");
    ensure!(expected.len()==64 && expected.bytes().all(|x|x.is_ascii_hexdigit()),"invalid expected SHA");
    let raw=fs::read(input)?;
    ensure!(raw.len()<=12*1024*1024,"source limit");
    let receipt=inspect_source(&raw,&expected)?;
    let mut f=fs::OpenOptions::new().create_new(true).write(true).open(output)?;
    f.write_all(&serde_json::to_vec_pretty(&receipt)?)?;
    f.write_all(b"\n")?;
    f.sync_all()?;
    println!("{}",serde_json::to_string(&json!({
        "source_sha256":expected,"status":receipt["status"],
        "variant_count":receipt["variants"].as_array().map(|x|x.len()).unwrap_or(0)
    }))?);
    Ok(())
}
