//! SK1-EXP-004: read-only census of Quill TEXT -> aligned FD service anchor.
//! No edit, no writer implementation, and no source/candidate PUB in artifacts.
//! The byte interval examined is the EXACT +1 BMP growth discard interval:
//!   [first_aligned_fd_anchor - 2, first_aligned_fd_anchor)
//! Matcher/authority only for pinned rar2 7038084, per pub-quill/src/writer.rs.
use anyhow::{ensure, Context, Result};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{env, fs, io::Write, io::Cursor};

const MAX_INPUT: usize = 12 * 1024 * 1024;
const FD_ALIGNMENT: usize = 0x200;

fn digest(data: &[u8]) -> String {
    format!("{:x}", Sha256::digest(data))
}

fn tag(name: [u8;4]) -> &'static str {
    match &name {
        b"STSH" => "STSH",
        b"SYID" => "SYID",
        b"STRS" => "STRS",
        b"FDPP" => "FDPP",
        b"FDPC" => "FDPC",
        b"BTEP" => "BTEP",
        b"BTEC" => "BTEC",
        b"MCLD" => "MCLD",
        b"TOKN" => "TOKN",
        b"TEXT" => "TEXT",
        _ => "OTHER_KNOWN_DESCRIPTOR",
    }
}

fn inspect(source: &[u8], source_sha: &str) -> Value {
    let mut result = json!({
        "schema":"sk1.exp004.quill-anchor-envelope.v1",
        "source_sha256":source_sha,
        "source_bytes":source.len(),
        "outcome":"NOT_EVALUATED",
        "scope":"read_only_structural_inspection",
        "native_publisher_acceptance":"NOT_EVALUATED",
        "publisher_save_authorized":false
    });
    let quill = match pub_cfb::read_stream_reader(
        Cursor::new(source), pub_reader::QUILL_STREAM_PATH)
    {
        Ok(data) => data,
        Err(_) => {
            result["outcome"] = json!("QUILL_STREAM_MISSING_OR_BROKEN");
            return result;
        }
    };
    let catalog = match pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &quill)
    {
        Ok(catalog) => catalog,
        Err(_) => {
            result["outcome"] = json!("QUILL_STORY_CATALOG_UNPARSEABLE");
            return result;
        }
    };
    let desc = catalog.descriptor_nodes.iter()
        .flat_map(|node| node.descriptors.iter()).collect::<Vec<_>>();
    let text_desc = desc.iter().filter(|d| d.name.value == *b"TEXT")
        .copied().collect::<Vec<_>>();
    if text_desc.len() != 1 {
        result["outcome"] = json!("TEXT_DESCRIPTOR_NON_UNIQUE");
        return result;
    }
    let text_start = text_desc[0].data_offset.value as usize;
    let Some(text_end) = text_start.checked_add(text_desc[0].data_length.value as usize) else {
        result["outcome"] = json!("STRUCTURAL_RANGE_INVALID");
        return result;
    };
    if text_end > quill.len() {
        result["outcome"] = json!("STRUCTURAL_RANGE_INVALID");
        return result;
    }
    let anchors = desc.iter()
        .copied()
        .filter(|d| d.name.value == *b"FDPP" || d.name.value == *b"FDPC")
        .map(|d|d.data_offset.value as usize)
        .filter(|&o|o >= text_end && o % FD_ALIGNMENT == 0)
        .collect::<Vec<_>>();
    let Some(&anchor) = anchors.iter().min() else {
        result["outcome"] = json!("ALIGNED_SERVICE_ANCHOR_MISSING");
        return result;
    };
    if anchor > quill.len() || anchor < 2 || anchor < text_end {
        result["outcome"] = json!("STRUCTURAL_RANGE_INVALID");
        return result;
    }
    let gap = anchor - text_end;
    // Exactly the same TWO trailing bytes that an ordinary +1 BMP growth
    // would need to discard. Preserve byte values privately, publish flags only.
    let tail = &quill[anchor - 2..anchor];
    let nonzero_count = tail.iter().filter(|&&b|b != 0).count();
    let mut payload_tags = Vec::new();
    let mut descriptor_payload_overlaps = 0;
    for d in &desc {
        let off = d.data_offset.value as usize;
        let Some(end) = off.checked_add(d.data_length.value as usize) else {
            result["outcome"] = json!("STRUCTURAL_RANGE_INVALID");
            return result;
        };
        if off < anchor && end > anchor-2 && d.name.value != *b"TEXT" {
            descriptor_payload_overlaps += 1;
            let label = tag(d.name.value);
            if !payload_tags.contains(&label) {
                payload_tags.push(label);
            }
        }
    }
    payload_tags.sort_unstable();
    let metadata_relies_on_movement = catalog.descriptor_nodes.iter().any(|node| {
        let Some(end) = node.source.end() else { return true; };
        (node.source.offset as usize) < anchor && (end as usize) > text_end
    });
    let trailing_zero_bytes = quill[text_end..anchor].iter().rev()
        .take_while(|&&byte|byte==0).count();
    // This is not permission to write. Named payload or other writer guards
    // can still forbid relocation even when the final bytes happen to be zero.
    let predicted_guard = if gap < 2 {
        "INSUFFICIENT_PRE_ANCHOR_SPACE"
    } else if nonzero_count != 0 {
        "NONZERO_UNKNOWN_ANCHOR_TAIL"
    } else if descriptor_payload_overlaps != 0 {
        "NAMED_DESCRIPTOR_PAYLOAD_OVERLAP"
    } else {
        "TAIL_TWO_BYTES_CLEAR_ONLY"
    };
    result["outcome"] = json!("INSPECTED");
    result["quill_length"] = json!(quill.len());
    result["descriptor_count"] = json!(desc.len());
    result["story_count"] = json!(catalog.stories.len());
    result["text_start"] = json!(text_start);
    result["text_end"] = json!(text_end);
    result["first_fd_anchor"] = json!(anchor);
    result["gap_before_anchor_bytes"] = json!(gap);
    result["tail2_nonzero_count"] = json!(nonzero_count);
    result["trailing_zero_bytes"] = json!(trailing_zero_bytes);
    result["descriptor_payload_overlaps_tail2"] = json!(descriptor_payload_overlaps);
    result["tail2_descriptor_tags"] = json!(payload_tags);
    result["descriptor_metadata_inside_move_window"] = json!(metadata_relies_on_movement);
    result["predicted_plus_one_gate"] = json!(predicted_guard);
    result
}

fn main() -> Result<()> {
    let mut args = env::args().skip(1);
    let file_path = args.next().context("source path")?;
    let expected_sha = args.next().context("expected SHA256")?;
    let output_path = args.next().context("receipt path")?;
    ensure!(args.next().is_none(), "unexpected arguments");
    ensure!(expected_sha.len() == 64 && expected_sha.bytes().all(|b| b.is_ascii_hexdigit()),
        "bad expected SHA");
    let data = fs::read(file_path)?;
    ensure!(data.len() > 8 && data.len() <= MAX_INPUT, "unexpected input length");
    ensure!(digest(&data)==expected_sha,"source SHA drift");
    ensure!(data.starts_with(&[0xd0,0xcf,0x11,0xe0,0xa1,0xb1,0x1a,0xe1]),
        "not CFB");
    let report = inspect(&data,&expected_sha);
    ensure!(digest(&data)==expected_sha,"source unexpectedly mutated");
    let mut file = fs::OpenOptions::new().create_new(true).write(true)
        .open(output_path)?;
    file.write_all(&serde_json::to_vec_pretty(&report)?)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    println!("{}", serde_json::to_string(&json!({
        "source_sha256":expected_sha, "outcome": report["outcome"]
    }))?);
    Ok(())
}
