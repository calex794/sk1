//! SK1-QUILL-VAL-PUB-T-961: inverse +/-1 Story compositions using ONLY pinned rar2 Writer.
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




fn output_byte_compare(ascii: &[u8], glyph: &[u8], target_syid: u32,
                       utf16_offset: usize, ascii_marker: char, glyph_char: char)
    -> Result<Value>
{
    use std::collections::BTreeMap;
    let mut a_entries=BTreeMap::new();
    let mut b_entries=BTreeMap::new();
    for e in pub_cfb::inspect_reader(Cursor::new(ascii))?.entries {
        ensure!(a_entries.insert(e.path.clone(),e).is_none(),"duplicate ASCII CFB path");
    }
    for e in pub_cfb::inspect_reader(Cursor::new(glyph))?.entries {
        ensure!(b_entries.insert(e.path.clone(),e).is_none(),"duplicate glyph CFB path");
    }
    let mut missing=0usize; let mut added=0usize;
    let mut changed_kinds=0usize;
    let mut other_stream_checked=0usize; let mut other_stream_changed=0usize;
    let mut quill_count=0usize;
    for (path,a) in &a_entries {
        let Some(b)=b_entries.get(path) else {missing+=1;continue;};
        if a.kind!=b.kind {changed_kinds+=1;continue;}
        if a.kind==pub_cfb::EntryKind::Stream {
            if path==pub_reader::QUILL_STREAM_PATH {quill_count+=1;}
            else {
                other_stream_checked+=1;
                let x=pub_cfb::read_stream_reader(Cursor::new(ascii),path)?;
                let y=pub_cfb::read_stream_reader(Cursor::new(glyph),path)?;
                if x!=y {other_stream_changed+=1;}
            }
        }
    }
    for key in b_entries.keys() {if !a_entries.contains_key(key){added+=1;}}
    ensure!(quill_count==1,"exact Quill stream unavailable");
    let aq=pub_cfb::read_stream_reader(Cursor::new(ascii),pub_reader::QUILL_STREAM_PATH)?;
    let bq=pub_cfb::read_stream_reader(Cursor::new(glyph),pub_reader::QUILL_STREAM_PATH)?;
    let ac=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&aq)?;
    let bc=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&bq)?;
    let at=ac.descriptor_nodes.iter().flat_map(|n|n.descriptors.iter())
        .filter(|d|d.name.value==*b"TEXT").collect::<Vec<_>>();
    let bt=bc.descriptor_nodes.iter().flat_map(|n|n.descriptors.iter())
        .filter(|d|d.name.value==*b"TEXT").collect::<Vec<_>>();
    ensure!(at.len()==1&&bt.len()==1,"TEXT descriptor not unique");
    let desc_match=at[0].data_offset.value==bt[0].data_offset.value
        && at[0].data_length.value==bt[0].data_length.value;
    let tx=usize::try_from(at[0].data_offset.value)?;
    let txlen=usize::try_from(at[0].data_length.value)?;
    let mut apos=ac.stories.iter().filter(|s|s.syid.0==target_syid);
    let target=apos.next().context("missing target SYID")?;
    ensure!(apos.next().is_none(),"duplicate target SYID");
    let prefix=ac.stories.iter().filter(|s|s.index<target.index)
        .try_fold(0usize,|acc,s|acc.checked_add(s.utf16le.len())
            .context("TEXT prefix overflow"))?;
    let expected=tx.checked_add(prefix)
        .and_then(|o|o.checked_add(utf16_offset.checked_mul(2)?))
        .context("expected UTF16 offset overflow")?;
    let within_text=expected>=tx&&expected+2<=tx+txlen;
    let bytes_same_size=aq.len()==bq.len();
    let mut quill_diff_count=0usize;
    let mut quill_diff_outside_expected=0usize;
    let mut quill_diff_outside_text=0usize;
    if bytes_same_size {
        for (i,(a,b)) in aq.iter().zip(&bq).enumerate() {
            if a!=b {
                quill_diff_count+=1;
                if i<expected||i>=expected+2 {quill_diff_outside_expected+=1;}
                if i<tx||i>=tx+txlen {quill_diff_outside_text+=1;}
            }
        }
    }
    let au=ascii_marker as u32;let gu=glyph_char as u32;
    ensure!(au<=u16::MAX as u32&&gu<=u16::MAX as u32,"not BMP");
    let unit_pair_expected=within_text&&bytes_same_size
        &&aq.get(expected..expected+2)==Some(&(au as u16).to_le_bytes()[..])
        &&bq.get(expected..expected+2)==Some(&(gu as u16).to_le_bytes()[..]);
    let mut descriptors_a=ac.descriptor_nodes.iter()
        .flat_map(|n|n.descriptors.iter());
    let mut descriptors_b=bc.descriptor_nodes.iter()
        .flat_map(|n|n.descriptors.iter());
    let mut desc_count=0usize;
    let descriptor_sequence_equal=loop{
        match(descriptors_a.next(),descriptors_b.next()){
            (None,None)=>break true,
            (Some(a),Some(b))=>{
                desc_count+=1;
                if a.name.value!=b.name.value||a.option_a.value!=b.option_a.value
                    ||a.option_b.value!=b.option_b.value||a.option_c.value!=b.option_c.value
                    ||a.bit_type.value!=b.bit_type.value
                    ||a.data_offset.value!=b.data_offset.value
                    ||a.data_length.value!=b.data_length.value {break false;}
            }
            _=>break false
        }
    };
    let same_story_id_order=ac.stories.iter().map(|s|s.syid.0)
        .eq(bc.stories.iter().map(|s|s.syid.0));
    let quill_only_utf16_unit_delta=bytes_same_size
        &&unit_pair_expected&&quill_diff_count>=1&&quill_diff_count<=2
        &&quill_diff_outside_expected==0;
    let all_non_quill_streams_equal=missing==0&&added==0
        &&changed_kinds==0&&other_stream_changed==0;
    let raw_output_diff_positions=if ascii.len()==glyph.len() {
        json!(ascii.iter().zip(glyph.iter()).filter(|(a,b)|a!=b).count())
    } else {Value::Null};
    Ok(json!({
        "schema":"sk1.quill-val-pub-t-961.glyph-diff.v1",
        "ascii_output_len":ascii.len(),"glyph_output_len":glyph.len(),
        "ascii_quill_len":aq.len(),"glyph_quill_len":bq.len(),
        "raw_output_diff_positions_equal_len":raw_output_diff_positions,
        "quill_diff_byte_count_equal_len":if bytes_same_size{
            json!(quill_diff_count)}else{Value::Null},
        "quill_diff_outside_expected_utf16_unit_equal_len":if bytes_same_size{
            json!(quill_diff_outside_expected)}else{Value::Null},
        "quill_diff_outside_TEXT_equal_len":if bytes_same_size{
            json!(quill_diff_outside_text)}else{Value::Null},
        "TEXT_descriptor_same_offset_length":desc_match,
        "TEXT_expected_UTF16_unit_present":unit_pair_expected,
        "quill_diff_confined_to_one_UTF16_unit":quill_only_utf16_unit_delta,
        "same_quill_descriptor_sequence":descriptor_sequence_equal,
        "same_SYID_header":ac.syid.header.value==bc.syid.header.value,
        "same_story_SYID_sequence":same_story_id_order,
        "same_story_UTF16_lengths":ac.strs.lengths.iter().map(|s|s.value)
            .eq(bc.strs.lengths.iter().map(|s|s.value)),
        "source_quill_descriptor_count":desc_count,
        "missing_CFB_paths":missing,"added_CFB_paths":added,
        "changed_CFB_entry_kinds":changed_kinds,
        "non_Quill_streams_checked":other_stream_checked,
        "non_Quill_streams_changed":other_stream_changed,
        "all_non_Quill_streams_equal":all_non_quill_streams_equal,
        "publisher_native_acceptance":"NOT_EVALUATED",
        "product_PUB_download_authorized":false
    }))
}

fn inspect_source(source:&[u8],expected_sha:&str,cases:&[Value])->Result<Value>{
    ensure!(sha256(source).to_string()==expected_sha,"original source hash drift");
    let original_sha=sha256(source);
    let editor=open_mature_0x2c_editor(source,original_sha)?;
    let eligible=editor.graph().stories.iter()
        .filter(|(id,s)|editor.can_replace_story_text(**id).is_ok()
            &&s.text.chars().any(|c|c.is_ascii_alphanumeric()))
        .take(3).map(|(id,s)|(*id,s.text.clone())).collect::<Vec<_>>();
    let source_quill=pub_cfb::read_stream_reader(
        Cursor::new(source),pub_reader::QUILL_STREAM_PATH)?;
    let catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&source_quill)?;
    let mut out=Vec::<Value>::new();
    for p in cases{
        let w=p.as_array().context("witness must be array")?;
        ensure!(w.len()==5,"witness field count");
        let story_ordinal=usize::try_from(w[0].as_u64().context("story ordinal")?)?;
        let slot=w[1].as_str().context("slot")?;
        let offset=usize::try_from(w[2].as_u64().context("utf16 offset")?)?;
        let expected_len=usize::try_from(w[3].as_u64().context("story utf16 len")?)?;
        let expected_ascii=usize::try_from(w[4].as_u64().context("ascii total")?)?;
        let (id,before)=eligible.get(story_ordinal).context("witness Story unavailable")?;
        ensure!(before.encode_utf16().count()==expected_len,"Story length drift");
        let letters=before.char_indices().filter(|(_,c)|c.is_ascii_alphanumeric())
            .collect::<Vec<_>>();
        ensure!(letters.len()==expected_ascii&&expected_ascii>0,"ASCII count drift");
        let rank=match slot{
            "F"=>0usize,"S"=>1usize.min(expected_ascii-1),
            "M"=>(expected_ascii-1)/2,
            _=>anyhow::bail!("invalid witness slot")
        };
        let (byte_index,old_char)=letters[rank];
        let true_offset=before[..byte_index].encode_utf16().count();
        ensure!(offset==true_offset,"pre-registered source offset drift");
        let mut syids=catalog.stories.iter()
            .filter(|s|pub_reader::derive_pub_story_id(&original_sha,s.syid.0)
                .is_ok_and(|derived|derived==*id));
        let syid=syids.next().context("missing target Quill SYID")?.syid.0;
        ensure!(syids.next().is_none(),"duplicate target Quill SYID");
        let prev=before[..byte_index].chars().last();
        let marker=['X','Q','Z'].into_iter()
            .find(|&c|Some(c)!=prev&&c!=old_char)
            .context("ASCII reference marker unavailable")?;
        let mut control_text=before.clone();
        control_text.insert(byte_index,marker);
        let control=step(source,syid,before,&control_text);
        ensure!(control.receipt["status"]=="HOSTED_PASS","baseline ASCII changed");
        let control_bytes=control.bytes.as_ref().context("missing ASCII output")?;
        let mut unicode_receipts=serde_json::Map::new();
        for (tag,ch) in [
            ("LATIN1_E_ACUTE",'\u{00e9}'),
            ("CYRILLIC_ZHE",'\u{0416}'),
            ("CJK_ZHONG",'\u{4e2d}'),
            ("COMBINING_ACUTE",'\u{0301}'),
            ("ASTRAL_GRIN",'\u{1f600}')
        ] {
            let mut after=before.clone();
            after.insert(byte_index,ch);
            let actual=step(source,syid,before,&after);
            let compared=if actual.receipt["status"]=="HOSTED_PASS"&&ch.len_utf16()==1{
                output_byte_compare(control_bytes,
                    actual.bytes.as_ref().context("missing glyph output")?,
                    syid,offset,marker,ch)?
            }else{
                Value::Null
            };
            unicode_receipts.insert(tag.to_owned(),
                json!({"step":actual.receipt,"vs_ascii_reference":compared}));
        }
        out.push(json!({
            "story_ordinal":story_ordinal,
            "slot":slot,
            "offset_utf16":offset,
            "story_utf16_len":expected_len,
            "story_ascii_count":expected_ascii,
            "baseline_ASCII":control.receipt,
            "unicode":unicode_receipts
        }));
    }
    ensure!(sha256(source).to_string()==expected_sha,"immutable input source drift");
    Ok(json!({
        "schema":"sk1.quill-val-pub-t-961.source.v1",
        "source_sha256":expected_sha,
        "source_bytes":source.len(),
        "eligible_story_count":eligible.len(),
        "witness_count":out.len(),
        "records":out,
        "publisher_native_acceptance":"NOT_EVALUATED",
        "product_PUB_download_authorized":false
    }))
}

fn main()->Result<()>{
    let mut args=env::args().skip(1);
    let input=args.next().context("source input")?;
    let expected_sha=args.next().context("expected SHA")?;
    let witness_file=args.next().context("witnesses.json")?;
    let output=args.next().context("output receipt")?;
    ensure!(args.next().is_none(),"unexpected args");
    ensure!(expected_sha.len()==64&&expected_sha.bytes().all(|b|b.is_ascii_hexdigit()),
        "invalid source SHA");
    let witness_map:Value=serde_json::from_slice(&fs::read(witness_file)?)?;
    let witness=witness_map[&expected_sha].as_array().context("source witness missing")?;
    ensure!(!witness.is_empty(),"empty source witness group");
    let bytes=fs::read(input)?;
    ensure!(bytes.len()<=12*1024*1024,"source byte cap");
    let result=inspect_source(&bytes,&expected_sha,witness)?;
    let mut f=fs::OpenOptions::new().create_new(true).write(true).open(output)?;
    f.write_all(&serde_json::to_vec_pretty(&result)?)?;
    f.write_all(b"\n")?;
    f.sync_all()?;
    println!("{}",serde_json::to_string(&json!({
        "source_sha256":expected_sha,
        "witnesses":result["witness_count"],
        "source_status":"EVALUATED"
    }))?);
    Ok(())
}
