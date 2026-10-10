//! SK1-QUILL-DIAG-PUB-T-954: read-only TOKN descriptor/Story fingerprint.
//! NO writer invocation, no output PUB creation, no TOKN reconstruction.
use anyhow::{Context, Result, ensure};
use pub_editor::{Sha256Digest, open_mature_0x2c_editor};
use pub_quill::{QuillToknPropertyBlock, parse_confirmed_story_catalog};
use serde_json::json;
use sha2::{Digest, Sha256};
use std::{env, fs, io::{Cursor, Write}};

fn sha256(raw: &[u8]) -> Sha256Digest {
    let raw_hash = Sha256::digest(raw);
    let mut bytes = [0u8; 32];
    bytes.copy_from_slice(&raw_hash);
    Sha256Digest::from_bytes(bytes)
}
fn probe(source: &[u8], sha: &str, ordinal: usize, expected_units: usize,
         expected_ascii: usize) -> Result<serde_json::Value> {
    let source_hash = sha256(source);
    ensure!(source_hash.to_string() == sha, "source SHA mismatch");
    let editor = open_mature_0x2c_editor(source, source_hash)
        .context("original Editor open failed")?;
    // Reproduce EXP-002 eligibility and ordering *without editing anything*.
    let eligible = editor.graph().stories.iter()
        .filter(|(id, story)| editor.can_replace_story_text(**id).is_ok()
            && story.text.chars().any(|c| c.is_ascii_alphanumeric()))
        .take(3)
        .map(|(id, story)| (*id, story.text.encode_utf16().count(),
                          story.text.chars().filter(|c| c.is_ascii_alphanumeric()).count()))
        .collect::<Vec<_>>();
    let (story_id, units, ascii) = eligible.get(ordinal).context("Story ordinal missing")?;
    ensure!(*units == expected_units && *ascii == expected_ascii,
        "pre-registered Story length / ASCII count mismatch");
    let quill = pub_cfb::read_stream_reader(
        Cursor::new(source), pub_reader::QUILL_STREAM_PATH)?;
    let catalog = parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.to_owned()), &quill)?;
    let mut matches = catalog.stories.iter().filter(|slice| {
        pub_reader::derive_pub_story_id(&source_hash, slice.syid)
            .is_ok_and(|id| id == *story_id)
    });
    let target = matches.next().context("Story has no SYID source mapping")?;
    ensure!(matches.next().is_none(), "ambiguous Story SYID mapping");
    ensure!(usize::try_from(target.utf16_code_units)? == *units,
        "Reader and Editor Story length disagree");
    let d = catalog.descriptor_nodes.iter()
        .flat_map(|n| n.descriptors.iter()).collect::<Vec<_>>();
    let tok_descriptors = d.iter().copied()
        .filter(|desc| desc.name.value == *b"TOKN").collect::<Vec<_>>();
    let for_target = tok_descriptors.iter().copied().filter(|desc| {
        u32::from(desc.option_a.value) == target.index
    }).collect::<Vec<_>>();
    let parsed = catalog.tokn.iter().filter(|chunk| {
        u32::from(chunk.story_ordinal.value) == target.index
            && chunk.story_syid.value == target.syid
    }).collect::<Vec<_>>();
    ensure!(parsed.len() == for_target.len(),
        "parsed target TOKN chunks and target descriptors differ");
    let mut parsed_plc_tokens = 0usize;
    let mut parsed_first_phase = 0usize;
    let mut parsed_second_phase = 0usize;
    let mut parsed_opaque_property_blocks = 0usize;
    let mut parsed_target_records = 0usize;
    let mut parsed_has_target_section = false;
    let mut parsed_has_opaque_tail = false;
    let mut parsed_boundary_count = 0usize;
    let mut parsed_opaque_tail_length = 0usize;
    let mut parsed_known_token_kind_count = 0usize;
    let mut parsed_known_token_length_count = 0usize;
    for token in &parsed {
        ensure!(token.plc_type.value == pub_quill::TOKN_PLC_TYPE,
            "unexpected TOKN PLC type");
        ensure!(token.plc_count.value as usize == token.effective_tokens.len(),
            "TOKN reader token count mismatch");
        parsed_plc_tokens += token.effective_tokens.len();
        parsed_first_phase += token.first_phase.len();
        parsed_second_phase += token.second_phase.len();
        parsed_boundary_count += token.boundaries_utf16.len();
        parsed_known_token_kind_count += token.effective_tokens.iter()
            .filter(|t| t.kind_raw.is_some()).count();
        parsed_known_token_length_count += token.effective_tokens.iter()
            .filter(|t| t.text_length_utf16.is_some()).count();
        for block in token.first_phase.iter().chain(token.second_phase.iter()) {
            if matches!(block, QuillToknPropertyBlock::Opaque { .. }) {
                parsed_opaque_property_blocks += 1;
            }
        }
        if let Some(section) = &token.target_section {
            parsed_has_target_section = true;
            parsed_target_records += section.records.len();
        }
        if token.opaque_tail_source.is_some() {
            parsed_has_opaque_tail = true;
            parsed_opaque_tail_length += token.opaque_tail.len();
        }
    }
    let total_tcd_target = catalog.tcd.iter()
        .filter(|chunk| chunk.story_syid.value == target.syid).count();
    let count_named = |name: [u8;4]| d.iter().filter(|desc| desc.name.value == name).count();
    // This is the existing Writer's guard predicate, copied as a read-only
    // count. It is NOT a newly learned TOKN semantics parser/classifier.
    let writer_guard_predicts_tokn = !for_target.is_empty();
    ensure!(sha256(source) == source_hash, "source memory unexpectedly changed");
    Ok(json!({
        "schema":"sk1.quill-diag-pub-t-954.probe.v1",
        "source_sha256":sha,
        "source_bytes":source.len(),
        "story_ordinal":ordinal,
        "story_syid":target.syid.0,
        "story_catalog_index":target.index,
        "story_utf16_len":units,
        "story_ascii_count":ascii,
        "eligible_stories_inspected":eligible.len(),
        "quill_stream_length":quill.len(),
        "quill_descriptor_nodes":catalog.descriptor_nodes.len(),
        "quill_descriptor_count":d.len(),
        "source_tokn_descriptor_count":tok_descriptors.len(),
        "target_tokn_descriptor_count":for_target.len(),
        "target_parsed_tokn_chunk_count":parsed.len(),
        "target_tcd_chunk_count":total_tcd_target,
        "fdpp_descriptor_count":count_named(*b"FDPP"),
        "fdpc_descriptor_count":count_named(*b"FDPC"),
        "btep_descriptor_count":count_named(*b"BTEP"),
        "btec_descriptor_count":count_named(*b"BTEC"),
        "parsed_plc_token_count":parsed_plc_tokens,
        "parsed_first_phase_block_count":parsed_first_phase,
        "parsed_second_phase_block_count":parsed_second_phase,
        "parsed_opaque_property_block_count":parsed_opaque_property_blocks,
        "parsed_target_record_count":parsed_target_records,
        "parsed_known_token_kind_count":parsed_known_token_kind_count,
        "parsed_known_token_length_count":parsed_known_token_length_count,
        "parsed_boundary_count":parsed_boundary_count,
        "parsed_has_target_section":parsed_has_target_section,
        "parsed_has_opaque_tail":parsed_has_opaque_tail,
        "parsed_opaque_tail_length":parsed_opaque_tail_length,
        "writer_guard_predicts_tokn":writer_guard_predicts_tokn,
        "writer_called":false,
        "source_immutable":true,
        "publisher_native_acceptance":"NOT_EVALUATED",
        "product_download_authorized":false
    }))
}
fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let input = args.next().context("source path missing")?;
    let expected_sha = args.next().context("source SHA missing")?;
    let ordinal: usize = args.next().context("story ordinal missing")?.parse()?;
    let expected_units: usize = args.next().context("Story length missing")?.parse()?;
    let expected_ascii: usize = args.next().context("ascii count missing")?.parse()?;
    let receipt = args.next().context("output receipt missing")?;
    ensure!(args.next().is_none(), "unexpected argument");
    ensure!(ordinal < 3 && expected_units <= 5_000_000 && expected_ascii <= expected_units,
        "invalid eligibility limits");
    ensure!(expected_sha.len()==64 && expected_sha.bytes().all(|b| b.is_ascii_hexdigit()),
        "invalid SHA argument");
    let source = fs::read(input)?;
    ensure!(source.len() <= 12*1024*1024, "source PUB oversized");
    let outcome = probe(&source, &expected_sha, ordinal, expected_units, expected_ascii)?;
    let mut f = fs::OpenOptions::new().write(true).create_new(true).open(receipt)?;
    f.write_all(&serde_json::to_vec_pretty(&outcome)?)?;
    f.write_all(b"\n")?;
    f.sync_all()?;
    println!("{}",json!({"source_sha256":expected_sha,"story_ordinal":ordinal,
        "target_tokn_descriptor_count":outcome["target_tokn_descriptor_count"],
        "source_tokn_descriptor_count":outcome["source_tokn_descriptor_count"],
        "writer_guard_predicts_tokn":outcome["writer_guard_predicts_tokn"],
        "writer_called":false}));
    Ok(())
}
