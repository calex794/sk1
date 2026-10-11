// PUB-T-982 — only task-specific matrix and outcome logic.
// All Reader/Writer/CFB comparison routines above this point are identical to
// the immutable PUB-T-963 scientific experiment, verified by Git blob SHA.
const PINNED_SOURCES:[(&str,u32);3]=[
 ("155f8fd8c191851e4380ab1557638aeabb34b2257fa12a7748ab00b09edb74ba",22),
 ("1e7f38b3ce1d0d956815992b15d361c405fc4bbdced5cdabb3c4581327cc183e",12),
 ("712e1db9cefd0af613b12fb776720ac5d67ebe772468f2e47cb26a1f2e6ce28a",2)
];
const REPL_NAMES:[&str;8]=[
 "ASCII_UPPER","CYRILLIC_ZHE","CJK_IDEOGRAPH",
 "NUL","TAB","LF","LINE_SEPARATOR","CR"
];

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
fn inspect_source(source:&[u8],expected_sha:&str)->Result<Value>{
    ensure!(sha256(source).to_string()==expected_sha,"source SHA changed");
    let target_header=PINNED_SOURCES.iter().find(|(s,_)|*s==expected_sha)
        .map(|(_,n)|*n).context("SHA not predeclared")?;
    let source_hash=sha256(source);
    let quill=pub_cfb::read_stream_reader(Cursor::new(source),pub_reader::QUILL_STREAM_PATH)?;
    let catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&quill)?;
    ensure!(catalog.syid.header.value==target_header,"source header drift");
    let editor=open_mature_0x2c_editor(source,source_hash)?;
    let eligible=editor.graph().stories.iter()
        .filter(|(id,s)|editor.can_replace_story_text(**id).is_ok()
             && s.text.chars().any(|c|c.is_ascii_alphanumeric()))
        .take(3).map(|(id,s)|(*id,s.text.clone())).collect::<Vec<_>>();
    let (id,before)=eligible.first().context("first eligible Story missing")?;
    let syids=catalog.stories.iter().filter(|s|pub_reader::derive_pub_story_id(
        &source_hash,s.syid.0).is_ok_and(|sid|sid==*id)).collect::<Vec<_>>();
    ensure!(syids.len()==1,"target SYID missing or duplicate");
    let syid=syids[0].syid.0;
    let letters=before.char_indices().filter(|(_,c)|c.is_ascii_alphanumeric()).collect::<Vec<_>>();
    ensure!(letters.len()>1,"second ASCII letter not present");
    let (byte_pos,old)=letters[1];
    ensure!(before[..byte_pos].encode_utf16().count()==1,"pinned UTF16 offset changed");
    let previous=before[..byte_pos].chars().last();
    let ascii=['X','Q','Z'].into_iter().find(|c|*c!=old && Some(*c)!=previous)
        .context("no distinct ASCII marker")?;
    let mut insert_text=before.clone();
    insert_text.insert(byte_pos,ascii);
    let mut delete_text=before.clone();
    delete_text.remove(byte_pos);
    let first_insert=step(source,syid,before,&insert_text);
    let first_delete=step(source,syid,before,&delete_text);
    let mut report=json!({
      "schema":"sk1.quill-val-pub-t-982.source.v1",
      "source_sha256":expected_sha,"source_bytes":source.len(),
      "source_syid_header":target_header,"story_ordinal":0,
      "slot":"second","utf16_offset":1,"original_codepoint":old as u32,
      "baseline_insert":first_insert.receipt,
      "baseline_delete":first_delete.receipt,
      "baseline_inverse_insert":{"status":"NOT_ATTEMPTED"},
      "baseline_inverse_delete":{"status":"NOT_ATTEMPTED"},
      "result":"BASELINE_NOT_EVALUATED",
      "variants":[],"native_publisher_acceptance":"NOT_EVALUATED"
    });
    let reverse_insert=if let Some(ref b)=first_insert.bytes {
        step(b,syid,&insert_text,before)
    } else { failed("FIRST_INSERT_FAILED") };
    let reverse_delete=if let Some(ref b)=first_delete.bytes {
        step(b,syid,&delete_text,before)
    } else { failed("FIRST_DELETE_FAILED") };
    report["baseline_inverse_insert"]=reverse_insert.receipt;
    report["baseline_inverse_delete"]=reverse_delete.receipt;
    if first_insert.receipt["status"]!="HOSTED_PASS" ||
       first_delete.receipt["status"]!="HOSTED_PASS" ||
       report["baseline_inverse_insert"]["status"]!="HOSTED_PASS" ||
       report["baseline_inverse_delete"]["status"]!="HOSTED_PASS" {
        report["result"]=json!("BASELINE_DRIFT");
        return Ok(report);
    }
    report["result"]=json!("EVALUATED");
    let changes=[
      ascii,'Ж','界','\0','\t','\n','\u{2028}','\r'
    ];
    let mut variants=Vec::new();
    for (&name,&glyph) in REPL_NAMES.iter().zip(changes.iter()) {
        ensure!(glyph!=old && glyph.len_utf16()==1,"invalid predeclared glyph");
        let after=mark_replace(before,byte_pos,old,glyph)?;
        let first=step(source,syid,before,&after);
        let mut item=json!({"name":name,"codepoint":glyph as u32,
           "original_utf16_units":before.encode_utf16().count(),
           "replacement_utf16_units":after.encode_utf16().count(),
           "first":first.receipt,"first_diff":Value::Null,
           "first_hypothesis":Value::Null,
           "inverse":{"status":"NOT_ATTEMPTED"},
           "final_diff":Value::Null,
           "final_hypothesis":Value::Null});
        if let Some(mutated)=first.bytes {
            let diff=raw_and_quill(source,&mutated)?;
            item["first_hypothesis"]=json!(hypothesis_first(&diff,target_header,old,glyph));
            item["first_diff"]=diff;
            let inverse=step(&mutated,syid,&after,before);
            item["inverse"]=inverse.receipt;
            if let Some(final_bytes)=inverse.bytes {
                let diff=raw_and_quill(source,&final_bytes)?;
                item["final_hypothesis"]=json!(hypothesis_final(&diff,target_header));
                item["final_diff"]=diff;
            }
        }
        variants.push(item);
    }
    report["variants"]=json!(variants);
    ensure!(sha256(source).to_string()==expected_sha,"source mutated");
    Ok(report)
}
fn main()->Result<()>{
    let mut args=env::args().skip(1);
    let input=args.next().context("input source path")?;
    let expected=args.next().context("source sha")?;
    let output=args.next().context("output JSON")?;
    ensure!(args.next().is_none(),"unexpected argument");
    ensure!(expected.len()==64 && expected.bytes().all(|b|b.is_ascii_hexdigit()),"invalid SHA");
    let raw=fs::read(input)?;
    ensure!(raw.len()<=12*1024*1024,"source too large");
    let report=inspect_source(&raw,&expected)?;
    let mut f=fs::OpenOptions::new().create_new(true).write(true).open(output)?;
    f.write_all(&serde_json::to_vec_pretty(&report)?)?;
    f.write_all(b"\n")?;
    f.sync_all()?;
    println!("{}",serde_json::to_string(&json!({
      "source_sha256":expected,"result":report["result"],
      "replacement_variants":report["variants"].as_array().map(|x|x.len()).unwrap_or(0)
    }))?);
    Ok(())
}
