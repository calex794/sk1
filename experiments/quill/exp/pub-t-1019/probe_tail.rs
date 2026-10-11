// PUB-T-1019 — only task-specific matrix and outcome logic.
// All Reader/Writer/CFB comparison routines above this point are identical to
// the immutable PUB-T-963 scientific experiment, verified by Git blob SHA.
const PINNED_SOURCES:[(&str,u32);3]=[
 ("155f8fd8c191851e4380ab1557638aeabb34b2257fa12a7748ab00b09edb74ba",22),
 ("1e7f38b3ce1d0d956815992b15d361c405fc4bbdced5cdabb3c4581327cc183e",12),
 ("712e1db9cefd0af613b12fb776720ac5d67ebe772468f2e47cb26a1f2e6ce28a",2)
];
const REPL_NAMES:[&str;2]=["ASCII_UPPER","CYRILLIC_ZHE"];

fn mark_replace(before:&str,byte_pos:usize,old:char,new:char)->Result<String> {
    ensure!(old.is_ascii_alphanumeric(),"original ASCII requirement");
    ensure!(old!=new,"replacement must alter text");
    ensure!(new.len_utf16()==1,"must be exactly one UTF-16 code unit");
    let mut after=before.to_owned();
    after.replace_range(byte_pos..byte_pos+old.len_utf8(),&new.to_string());
    ensure!(after.encode_utf16().count()==before.encode_utf16().count(),
        "equal UTF16 length lost");
    Ok(after)
}
fn raw_and_quill(before:&[u8],after:&[u8]) -> Result<Value> {
    let raw=physical_residue(before,after);
    let cfb=inspect_reverted_cfb(before,after)?;
    Ok(json!({
      "same_length":raw["equal_length"],
      "whole_pub_changed_raw_bytes":raw["changed_same_offset_bytes"],
      "whole_pub_extra_bytes":raw["extra_bytes"],
      "source_syid":cfb["source_syid_first_dword"],
      "result_syid":cfb["final_syid_first_dword"],
      "syid_delta":cfb["syid_first_dword_delta"],
      "syid_changed_header_bytes":cfb["syid_first_dword_changed_bytes"],
      "quill_changed_bytes":cfb["quill_differing_byte_positions_equal_len"],
      "outside_header_quill_changed_bytes":cfb["quill_changed_bytes_outside_syid_first_dword"],
      "non_quill_streams_checked":cfb["non_quill_streams_checked"],
      "non_quill_streams_changed":cfb["non_quill_streams_changed"],
      "unchanged_story_syid_sequence":cfb["same_quill_story_syid_sequence"],
      "unchanged_story_lengths":cfb["same_quill_story_utf16_lengths"],
      "unchanged_text_payload":cfb["same_quill_TEXT_payload_bytes"],
      "unchanged_descriptors":cfb["matched_descriptor_sequence"],
      "changed_chunk_types":cfb["altered_chunks_by_kind"],
      "changed_chunk_count":cfb["altered_chunk_payload_count"],
      "publisher_native_acceptance":"NOT_EVALUATED"
    }))
}
fn expected_header_changed(old:u32,delta:u32)->Option<usize>{
    old.checked_add(delta).map(|new|old.to_le_bytes().iter().zip(new.to_le_bytes())
                              .filter(|(a,b)|*a!=b).count())
}
fn hypothesis_first(raw:&Value,old_header:u32,old_char:char,replacement:char)->bool{
    let old_word=old_char as u16;
    let new_word=replacement as u16;
    let text_bytes=old_word.to_le_bytes().iter().zip(new_word.to_le_bytes())
                      .filter(|(a,b)|*a!=b).count();
    let header_bytes=expected_header_changed(old_header,1);
    let expected=header_bytes.map(|n|n+text_bytes);
    expected.is_some_and(|n|raw["whole_pub_changed_raw_bytes"]==json!(n)) &&
        raw["same_length"]==true && raw["whole_pub_extra_bytes"]==0 &&
        raw["syid_delta"]==1 &&
        raw["syid_changed_header_bytes"]==json!(header_bytes.unwrap_or(99)) &&
        raw["outside_header_quill_changed_bytes"]==json!(text_bytes) &&
        raw["non_quill_streams_changed"]==0 &&
        raw["unchanged_story_syid_sequence"]==true &&
        raw["unchanged_story_lengths"]==true &&
        raw["unchanged_descriptors"]==true &&
        raw["unchanged_text_payload"]==false &&
        raw["changed_chunk_types"]["SYID"]==1 &&
        raw["changed_chunk_types"]["TEXT"]==1 &&
        raw["changed_chunk_count"]==2
}
fn hypothesis_final(raw:&Value,old_header:u32)->bool{
    let h=expected_header_changed(old_header,2);
    h.is_some_and(|n|raw["whole_pub_changed_raw_bytes"]==json!(n)) &&
        raw["same_length"]==true && raw["whole_pub_extra_bytes"]==0 &&
        raw["syid_delta"]==2 &&
        raw["syid_changed_header_bytes"]==json!(h.unwrap_or(99)) &&
        raw["outside_header_quill_changed_bytes"]==0 &&
        raw["non_quill_streams_changed"]==0 &&
        raw["unchanged_story_syid_sequence"]==true &&
        raw["unchanged_story_lengths"]==true &&
        raw["unchanged_descriptors"]==true &&
        raw["unchanged_text_payload"]==true &&
        raw["changed_chunk_types"]["SYID"]==1 &&
        raw["changed_chunk_count"]==1
}

fn two_order(source:&[u8],syid:u32,before:&str,intermediate:&str,after:&str,
             old_header:u32,old_char:char,glyph:char)->Result<Value>{
    let first=step(source,syid,before,intermediate);
    let mut out=json!({"first":first.receipt,"second":{"status":"NOT_ATTEMPTED"},
                       "final_sha256":Value::Null,"final_diff":Value::Null,
                       "final_hypothesis":Value::Null});
    if let Some(intermediate_bytes)=first.bytes {
        let second=step(&intermediate_bytes,syid,intermediate,after);
        out["second"]=second.receipt;
        if let Some(final_bytes)=second.bytes {
            let d=raw_and_quill(source,&final_bytes)?;
            let h=expected_header_changed(old_header,2);
            let txt=(old_char as u16).to_le_bytes().iter()
                .zip((glyph as u16).to_le_bytes())
                .filter(|(a,b)|*a!=b).count();
            let locality=h.is_some_and(|n|
                d["same_length"]==true &&
                d["whole_pub_changed_raw_bytes"]==json!(n+txt) &&
                d["whole_pub_extra_bytes"]==0 &&
                d["syid_delta"]==2 &&
                d["syid_changed_header_bytes"]==json!(n) &&
                d["outside_header_quill_changed_bytes"]==json!(txt) &&
                d["non_quill_streams_changed"]==0 &&
                d["unchanged_story_syid_sequence"]==true &&
                d["unchanged_story_lengths"]==true &&
                d["unchanged_descriptors"]==true &&
                d["unchanged_text_payload"]==false &&
                d["changed_chunk_types"]["SYID"]==1 &&
                d["changed_chunk_types"]["TEXT"]==1 &&
                d["changed_chunk_count"]==2);
            out["final_sha256"]=json!(sha256(&final_bytes).to_string());
            out["final_diff"]=d;
            out["final_hypothesis"]=json!(locality);
        }
    }
    Ok(out)
}


fn inspect_source(source:&[u8],expected_sha:&str)->Result<Value>{
    // Original source SHA is verified both by Python manifest intake and here.
    ensure!(sha256(source).to_string()==expected_sha,"source SHA drift");
    let source_hash=sha256(source);
    let source_block=|code:&str| json!({
        "schema":"sk1.quill-exp-pub-t-1019.source.v1",
        "source_sha256":expected_sha,"source_bytes":source.len(),
        "source_syid_header":Value::Null,"eligible_story_count":0,
        "selected_story_count":0,"result":code,"stories":[],
        "native_publisher_acceptance":"NOT_EVALUATED"
    });
    let quill=match pub_cfb::read_stream_reader(Cursor::new(source),pub_reader::QUILL_STREAM_PATH){
        Ok(data)=>data,
        Err(_)=>return Ok(source_block("SOURCE_QUILL_STREAM_BLOCKED"))
    };
    let catalog=match pub_quill::parse_confirmed_story_catalog(
       pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&quill){
        Ok(data)=>data,
        Err(_)=>return Ok(source_block("SOURCE_QUILL_CATALOG_BLOCKED"))
    };
    let header=catalog.syid.header.value;
    if let Some((_,expect))=PINNED_SOURCES.iter().find(|(sha,_)|*sha==expected_sha){
        ensure!(header==*expect,"T1007 header baseline drift");
    }
    let editor=match open_mature_0x2c_editor(source,source_hash){
        Ok(e)=>e,
        Err(_)=>return Ok(json!({
            "schema":"sk1.quill-exp-pub-t-1019.source.v1",
            "source_sha256":expected_sha,"source_bytes":source.len(),
            "source_syid_header":header,"eligible_story_count":0,
            "selected_story_count":0,"result":"SOURCE_EDITOR_OPEN_BLOCKED",
            "stories":[],"native_publisher_acceptance":"NOT_EVALUATED"}))
    };
    // Deterministic original Editor graph order: retain first two ordinary Stories,
    // independent of whether Writer subsequently accepts the selected positions.
    let eligible=editor.graph().stories.iter()
       .filter(|(id,story)|editor.can_replace_story_text(**id).is_ok()
                     && story.text.chars().any(|c|c.is_ascii_alphanumeric()))
       .map(|(id,story)|(*id,story.text.clone())).collect::<Vec<_>>();
    let eligible_count=eligible.len();
    let mut stories=Vec::new();
    for (story_ordinal,(id,before)) in eligible.into_iter().take(2).enumerate(){
        let matched=catalog.stories.iter().filter(|cat|
            pub_reader::derive_pub_story_id(&source_hash,cat.syid.0)
                .is_ok_and(|sid|sid==id)).collect::<Vec<_>>();
        ensure!(matched.len()==1,"ambiguous Story SYID");
        let syid=matched[0].syid.0;
        let letters=before.char_indices().filter(|(_,ch)|ch.is_ascii_alphanumeric())
            .collect::<Vec<_>>();
        ensure!(!letters.is_empty(),"ordinary Story without ASCII slot");
        let ranks=[
          ("first",0_usize),
          ("second",1_usize.min(letters.len()-1)),
          ("middle",(letters.len()-1)/2),
          ("last",letters.len()-1)
        ];
        let mut visited=HashSet::new();
        let mut duplicate_slots=Vec::new();
        let mut slots=Vec::new();
        for &(slot,rank) in &ranks {
            let (byte_pos,old)=letters[rank];
            let offset=before[..byte_pos].encode_utf16().count();
            if !visited.insert(offset){
                duplicate_slots.push(slot);
                continue;
            }
            let prev=before[..byte_pos].chars().last();
            let ascii=['X','Q','Z'].into_iter()
                .find(|c|*c!=old && Some(*c)!=prev)
                .context("ASCII alternate missing")?;
            let glyphs=[ascii,'Ж'];
            let mut variants=Vec::new();
            for (&name,&glyph) in REPL_NAMES.iter().zip(glyphs.iter()){
                let after=mark_replace(&before,byte_pos,old,glyph)?;
                // True direct zero-delta Writer control, not the edit path.
                let direct=step(source,syid,&before,&after);
                let mut deleted=before.clone();
                ensure!(deleted.remove(byte_pos)==old,"delete selected scalar drift");
                let mut inserted=before.clone();
                inserted.insert(byte_pos,glyph);
                ensure!(deleted.encode_utf16().count()+1==before.encode_utf16().count()
                    && inserted.encode_utf16().count()==before.encode_utf16().count()+1,
                    "intermediate UTF16 unit mismatch");
                let delete_first=two_order(source,syid,&before,&deleted,&after,header,old,glyph)?;
                let insert_first=two_order(source,syid,&before,&inserted,&after,header,old,glyph)?;
                let same_sha=match(delete_first["final_sha256"].as_str(),
                                   insert_first["final_sha256"].as_str()){
                    (Some(x),Some(y))=>json!(x==y),_=>Value::Null
                };
                variants.push(json!({
                    "name":name,
                    "codepoint":glyph as u32,
                    "direct_replace":direct.receipt,
                    "delete_then_insert":delete_first,
                    "insert_then_delete":insert_first,
                    "two_stage_sha_equal":same_sha
                }));
            }
            slots.push(json!({
                "slot":slot,"ascii_rank":rank,"utf16_offset":offset,
                "original_codepoint":old as u32,
                "original_story_utf16_units":before.encode_utf16().count(),
                "variants":variants
            }));
        }
        stories.push(json!({
          "story_ordinal":story_ordinal,"syid_id":syid,
          "original_story_utf16_units":before.encode_utf16().count(),
          "ascii_alnum_count":letters.len(),
          "selected_slot_count":slots.len(),"dedup_skipped":duplicate_slots,
          "slots":slots
        }));
    }
    ensure!(sha256(source).to_string()==expected_sha,"source mutated");
    Ok(json!({
      "schema":"sk1.quill-exp-pub-t-1019.source.v1",
      "source_sha256":expected_sha,"source_bytes":source.len(),
      "source_syid_header":header,
      "eligible_story_count":eligible_count,
      "selected_story_count":stories.len(),
      "result":if stories.is_empty(){"NO_ELIGIBLE_STORY"}else{"EVALUATED"},
      "stories":stories,"native_publisher_acceptance":"NOT_EVALUATED"
    }))
}
fn main()->Result<()> {
    let mut args=env::args().skip(1);
    let input=args.next().context("input PUB path")?;
    let expected=args.next().context("expected sha256")?;
    let output=args.next().context("output json path")?;
    ensure!(args.next().is_none(),"extra args");
    ensure!(expected.len()==64 && expected.bytes().all(|b|b.is_ascii_hexdigit()),
        "invalid sha argument");
    let source=fs::read(input)?;
    ensure!(source.len()<=12*1024*1024,"source exceeds source cap");
    let report=inspect_source(&source,&expected)?;
    let mut handle=fs::OpenOptions::new().create_new(true).write(true).open(output)?;
    handle.write_all(&serde_json::to_vec_pretty(&report)?)?;
    handle.write_all(b"\n")?;
    handle.sync_all()?;
    println!("{}",serde_json::to_string(&json!({
        "result":report["result"],
        "selected_story_count":report["selected_story_count"]
    }))?);
    Ok(())
}
