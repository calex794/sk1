//! SK1-QUILL-DIAG-PUB-T-967: blind read-only source→growth-envelope census.
//! Writer is never invoked. Source contents/candidate PUB stay private.
//! Validity is limited to the immutable upstream hosted Writer guard geometry.
use anyhow::{Context, Result, ensure};
use pub_editor::{open_mature_0x2c_editor, Sha256Digest};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{env, fs, io::{Cursor, Write}};

const MAX_SOURCE_BYTES: usize = 12 * 1024 * 1024;
const SERVICE_ALIGNMENT: usize = 0x200;
fn sha256(data: &[u8])->Sha256Digest {
    let mut out=[0u8;32];
    out.copy_from_slice(&Sha256::digest(data));
    Sha256Digest::from_bytes(out)
}

fn predict(data: &[u8], sha: &str) -> Result<Value> {
    let hash=sha256(data);
    ensure!(hash.to_string()==sha,"source digest mismatch");
    ensure!(data.starts_with(&[0xd0,0xcf,0x11,0xe0,0xa1,0xb1,0x1a,0xe1]),"not CFB");
    let editor=open_mature_0x2c_editor(data,hash).context("source Editor unavailable")?;
    // Exactly the original PUB-T-962 selection: first Editor Story with
    // a replaceable text and at least one ASCII alphanumeric character.
    // The ordinal is the index in the original graph, NOT its Quill SYID.
    let selected=editor.graph().stories.iter().enumerate().find_map(|(ordinal,(id,story))|{
        if editor.can_replace_story_text(*id).is_err(){return None;}
        let letters=story.text.char_indices()
            .filter(|(_,ch)|ch.is_ascii_alphanumeric()).collect::<Vec<_>>();
        if letters.is_empty(){return None;}
        let (offset,_)=letters[1usize.min(letters.len()-1)];
        Some((ordinal,story.text[..offset].encode_utf16().count(),
              story.text.encode_utf16().count()))
    }).context("no original eligible Story")?;

    let stream=pub_cfb::read_stream_reader(
        Cursor::new(data),pub_reader::QUILL_STREAM_PATH)?;
    let catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.to_owned()),&stream)?;
    let descriptors=catalog.descriptor_nodes.iter()
        .flat_map(|node|node.descriptors.iter()).collect::<Vec<_>>();
    let text=descriptors.iter().filter(|desc|desc.name.value==*b"TEXT")
        .copied().collect::<Vec<_>>();
    ensure!(text.len()==1,"TEXT descriptor must be unique");
    let text_start=usize::try_from(text[0].data_offset.value)?;
    let text_len=usize::try_from(text[0].data_length.value)?;
    let text_end=text_start.checked_add(text_len).context("TEXT end overflow")?;
    ensure!(text_end<=stream.len(),"TEXT out of source Quill");

    let anchor=descriptors.iter()
        .filter(|desc|desc.name.value==*b"FDPP" || desc.name.value==*b"FDPC")
        .filter_map(|desc|usize::try_from(desc.data_offset.value).ok())
        .filter(|&offset|offset>=text_end && offset%SERVICE_ALIGNMENT==0)
        .min().context("aligned FDPP/FDPC anchor unavailable")?;
    ensure!(anchor<=stream.len() && text_end<=anchor,"service anchor out of Quill");

    let metadata_intersects=catalog.descriptor_nodes.iter().any(|node|{
        node.source.end().is_none_or(|end|
            (node.source.offset as usize)<anchor && (end as usize)>text_end)
    });
    ensure!(!metadata_intersects,"descriptor metadata in move window");
    let gap=anchor-text_end;
    let trailing_zero=stream[text_end..anchor].iter().rev()
        .take_while(|&&byte|byte==0).count();

    let mut furthest_non_text_end=text_end;
    let mut candidate_desc_count=0usize;
    for d in &descriptors {
        if d.name.value==*b"TEXT"{continue;}
        let start=usize::try_from(d.data_offset.value)?;
        let length=usize::try_from(d.data_length.value)?;
        let end=start.checked_add(length).context("descriptor extent overflow")?;
        if start<anchor && end>text_end {
            candidate_desc_count+=1;
            furthest_non_text_end=furthest_non_text_end.max(end);
        }
    }
    let descriptor_clearance=anchor.saturating_sub(furthest_non_text_end);
    let raw_limit=gap.min(trailing_zero).min(descriptor_clearance);
    let max_n=raw_limit/2;
    let first_fail=max_n.checked_add(1).context("overflow in first fail")?;

    // Independent exact-address read-only check of the *first* growth > bound:
    // same observed predicates in upstream guard, no writer call/materialize.
    let first_fail_bytes=first_fail.checked_mul(2).context("growth overflow")?;
    let fail_class=if first_fail_bytes>gap {
        "quill_insufficient_capacity"
    } else {
        let discard=anchor.checked_sub(first_fail_bytes).context("discard underflow")?;
        let mut kind=None;
        for d in &descriptors {
            if d.name.value==*b"TEXT"{continue;}
            let start=usize::try_from(d.data_offset.value)?;
            let size=usize::try_from(d.data_length.value)?;
            let end=start.checked_add(size).context("descriptor end overflow")?;
            if start<anchor && end>discard {
                let ostart=start.max(discard);
                let oend=end.min(anchor);
                ensure!(ostart<oend && oend<=stream.len(),"invalid descriptor overlap");
                kind=Some(if stream[ostart..oend].iter().any(|&v|v!=0){
                    "quill_growth_would_discard_unknown"
                } else {
                    "quill_growth_would_discard_descriptor"
                });
                break;
            }
        }
        kind.unwrap_or_else(||{
            if stream[discard..anchor].iter().any(|&v|v!=0){
                "quill_growth_would_discard_unknown"
            } else {"PREDICTED_PASS_UNEXPECTED"}
        })
    };
    let bound_by={
        let mut why=Vec::new();
        if gap/2==max_n{why.push("GEOMETRY");}
        if trailing_zero/2==max_n{why.push("NONZERO_SUFFIX");}
        if descriptor_clearance/2==max_n{why.push("DESCRIPTOR_CLEARANCE");}
        why.join("+")
    };
    // Do not export source/candidate PUB, unknown chunk names, raw bytes, text.
    ensure!(sha256(data)==hash,"source immutable SHA mismatch");
    Ok(json!({
        "schema":"sk1.quill-diag-pub-t-967.source-envelope.v1",
        "source_sha256":sha,
        "source_bytes":data.len(),
        "selected_story_ordinal":selected.0,
        "selected_offset_utf16":selected.1,
        "selected_story_utf16_len":selected.2,
        "quill_stream_length":stream.len(),
        "quill_descriptor_count":descriptors.len(),
        "source_story_count":catalog.stories.len(),
        "text_start":text_start,"text_end":text_end,
        "first_aligned_fd_anchor":anchor,
        "pre_anchor_gap_bytes":gap,
        "trailing_zero_bytes":trailing_zero,
        "overlapping_nontarget_descriptor_count":candidate_desc_count,
        "furthest_nontext_descriptor_end":furthest_non_text_end,
        "nontext_descriptor_clearance_bytes":descriptor_clearance,
        "source_only_predicted_max_growth_utf16":max_n,
        "source_only_predicted_first_failure_utf16":first_fail,
        "source_only_predicted_first_failure_guard":fail_class,
        "limiting_factors":bound_by,
        "source_immutable":true,
        "writer_invoked":false,
        "candidate_generated":false,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":false
    }))
}
fn main()->Result<()>{
    let mut args=env::args().skip(1);
    let path=args.next().context("input PUB path missing")?;
    let sha=args.next().context("SHA missing")?;
    let out=args.next().context("output receipt path missing")?;
    ensure!(args.next().is_none(),"too many args");
    ensure!(sha.len()==64 && sha.bytes().all(|b|b.is_ascii_hexdigit()),
        "invalid source SHA");
    let bytes=fs::read(path)?;
    ensure!(bytes.len()>=512 && bytes.len()<=MAX_SOURCE_BYTES,"source size cap");
    let record=predict(&bytes,&sha)?;
    let mut file=fs::OpenOptions::new().create_new(true).write(true).open(out)?;
    file.write_all(&serde_json::to_vec_pretty(&record)?)?;
    file.write_all(b"\n")?;
    file.sync_all()?;
    println!("{}",json!({
        "source_sha256":sha,
        "read_only":true,
        "predicted_max":record["source_only_predicted_max_growth_utf16"],
        "first_guard":record["source_only_predicted_first_failure_guard"]
    }));
    Ok(())
}
