//! PUB-T-986: read-only forensic test of Quill paragraph/character boundary grammar.
//! Never invokes the Writer or publishes original Quill bytes or Story text.
use anyhow::{anyhow, Context, Result, ensure};
use pub_core::StreamPath;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{collections::{BTreeMap, BTreeSet}, env, fs, io::{Cursor, Write}};

const MAX_SOURCE: usize = 12*1024*1024;
const SAMPLE_LIMIT: usize = 30;

fn sha256_hex(input:&[u8])->String {
    let digest=Sha256::digest(input);
    digest.iter().map(|b|format!("{b:02x}")).collect()
}
fn stat_frame(input:&[u8], sha:&str, status:&str)->Value{
    json!({"schema":"sk1.pub-t-986.source.v1",
        "source_sha256":sha,"source_bytes":input.len(),
        "status":status,"stats":null,
        "quill_writer_invocations":0,
        "native_publisher_acceptance":"NOT_EVALUATED",
        "product_pub_download_authorized":false,
        "source_immutable":true})
}
fn cr_at(bytes:&[u8], i:usize)->bool{
    bytes.get(i..i+2)==Some(&[0x0d,0x00][..])
}
fn decode_fd(
    bytes:&[u8],
    catalog:&pub_quill::QuillStoryCatalog,
    name:[u8;4], text_start:u32, text_end:u32
)->Result<(Vec<u32>,usize)>{
    let descriptors=catalog.descriptor_nodes.iter()
        .flat_map(|node|node.descriptors.iter())
        .filter(|d|d.name.value==name).collect::<Vec<_>>();
    ensure!(!descriptors.is_empty(),"missing FD descriptor");
    let mut positions=Vec::new();
    for desc in &descriptors{
        let base=usize::try_from(desc.data_offset.value)?;
        let len=usize::try_from(desc.data_length.value)?;
        let end=base.checked_add(len).context("FD size overflow")?;
        let payload=bytes.get(base..end).context("FD span outside Quill")?;
        ensure!(payload.len()>=8,"short FD header");
        let count=usize::from(u16::from_le_bytes([payload[0],payload[1]]));
        ensure!(count<=16384,"unreasonable FD count");
        let min=8usize.checked_add(count.checked_mul(6).context("FD count overflow")?)
            .context("FD minimum bytes overflow")?;
        ensure!(min<=payload.len(),"FD payload too small");
        for k in 0..count{
            let pos=8usize.checked_add(k.checked_mul(4).context("FD position overflow")?)
                .context("FD offset overflow")?;
            let val=u32::from_le_bytes(payload[pos..pos+4].try_into()?);
            ensure!(val>=text_start && val<=text_end,"FD position outside TEXT");
            ensure!((val-text_start)%2==0,"FD unaligned UTF16 position");
            positions.push(val);
        }
    }
    Ok((positions,descriptors.len()))
}
fn diff_multiset(expected:&[u32],actual:&[u32])->(usize,usize,Vec<u32>,Vec<u32>){
    let mut delta=BTreeMap::<u32,i64>::new();
    for &v in expected {*delta.entry(v).or_default()+=1}
    for &v in actual {*delta.entry(v).or_default()-=1}
    let mut missing=0usize;let mut unexpected=0usize;
    let mut missed=Vec::new();let mut extra=Vec::new();
    for (offset,count) in delta {
        if count>0 {
            missing+=count as usize;
            if missed.len()<SAMPLE_LIMIT {missed.push(offset)}
        } else if count<0 {
            unexpected+=(-count) as usize;
            if extra.len()<SAMPLE_LIMIT {extra.push(offset)}
        }
    }
    (missing,unexpected,missed,extra)
}


const RAW_METRIC_NAMES:[&str;25]=[
"records","unique_bodies","comparable_pairs","duplicate_end_pairs",
"adjacent_alias","adjacent_equal_distinct","adjacent_different",
"within_page","cross_page","equal_within_page","equal_cross_page",
"at_cr_any","equal_at_cr_any","outside_cr","equal_outside_cr",
"terminal_cr_start","equal_terminal_cr_start",
"terminal_cr_end","equal_terminal_cr_end",
"internal_cr_start","equal_internal_cr_start",
"internal_cr_end","equal_internal_cr_end",
"same_story_end","equal_same_story_end"
];
fn raw_bump(x:&mut BTreeMap<String,usize>,name:&str){
    *x.get_mut(name).expect("unregistered FDPC metric")+=1;
}
fn raw_fdpc_styles(
  bytes:&[u8],
  catalog:&pub_quill::QuillStoryCatalog,
  text_start:u32, text_end:u32,
  terminal_start:&BTreeSet<u32>,terminal_end:&BTreeSet<u32>,
  internal_start:&BTreeSet<u32>,internal_end:&BTreeSet<u32>,
  story_end:&BTreeSet<u32>,
  old_fdpc_count:usize
)->Result<BTreeMap<String,usize>>{
    let mut metrics=RAW_METRIC_NAMES.iter()
        .map(|k|(k.to_string(),0usize)).collect::<BTreeMap<_,_>>();
    // Exactly the framing used in the pinned Quill typography Reader,
    // but compare the complete raw per-record style bodies without decoding
    // or mutating their semantics.
    let descriptors=catalog.descriptor_nodes.iter()
        .flat_map(|node|node.descriptors.iter())
        .filter(|d|d.name.value==*b"FDPC").collect::<Vec<_>>();
    let mut records=Vec::<(u32,usize,usize,usize)>::new();
    let mut unique=BTreeSet::<Vec<u8>>::new();
    for (page_idx,desc) in descriptors.iter().enumerate(){
        let base=usize::try_from(desc.data_offset.value)?;
        let length=usize::try_from(desc.data_length.value)?;
        let end=base.checked_add(length).context("FDPC raw page overflow")?;
        let page=bytes.get(base..end).context("FDPC raw page outside Quill")?;
        ensure!(page.len()>=8,"FDPC raw page short");
        let count=usize::from(u16::from_le_bytes(page[0..2].try_into()?));
        ensure!(count<=16384,"FDPC record count too large");
        let table_end=8usize.checked_add(count.checked_mul(6).context("FDPC table count overflow")?)
            .context("FDPC table position overflow")?;
        ensure!(table_end<=page.len(),"FDPC tables exceed page");
        for k in 0..count {
            let text_pos=8usize+k*4;
            let stop=u32::from_le_bytes(page[text_pos..text_pos+4].try_into()?);
            ensure!(stop>=text_start&&stop<=text_end&&(stop-text_start)%2==0,
                "FDPC end outside UTF16 TEXT");
            let ofs_pos=8usize+count*4+k*2;
            let relative=usize::from(u16::from_le_bytes(page[ofs_pos..ofs_pos+2].try_into()?));
            ensure!(relative>=table_end&&relative+4<=page.len(),
                "FDPC style offset outside body");
            let style_len=usize::try_from(u32::from_le_bytes(
                page[relative..relative+4].try_into()?))?;
            ensure!(style_len>=4,"FDPC style shorter than u32 prefix");
            let style_end=relative.checked_add(style_len).context("FDPC raw style size overflow")?;
            ensure!(style_end<=page.len(),"FDPC raw style outside page");
            let absolute_style_start=base.checked_add(relative).context("FDPC raw absolute offset overflow")?;
            unique.insert(page[relative..style_end].to_vec());
            records.push((stop,absolute_style_start,style_len,page_idx));
        }
    }
    ensure!(records.len()==old_fdpc_count,
        "raw FDPC record count disagrees with independent boundary decoder");
    metrics.insert("records".into(),records.len());
    metrics.insert("unique_bodies".into(),unique.len());
    records.sort_by_key(|x|(x.0,x.3));
    for w in records.windows(2){
        let (boundary,a_start,a_len,a_page)=w[0];
        let (_,b_start,b_len,b_page)=w[1];
        if boundary==w[1].0 {raw_bump(&mut metrics,"duplicate_end_pairs");continue}
        raw_bump(&mut metrics,"comparable_pairs");
        let a=bytes.get(a_start..a_start+a_len).context("raw style A outside stream")?;
        let b=bytes.get(b_start..b_start+b_len).context("raw style B outside stream")?;
        let equal=a==b;
        if a_start==b_start {
            ensure!(equal,"alias offset had unequal content");
            raw_bump(&mut metrics,"adjacent_alias");
        } else if equal {
            raw_bump(&mut metrics,"adjacent_equal_distinct");
        } else {raw_bump(&mut metrics,"adjacent_different");}
        if a_page==b_page {
            raw_bump(&mut metrics,"within_page");
            if equal {raw_bump(&mut metrics,"equal_within_page");}
        }else{
            raw_bump(&mut metrics,"cross_page");
            if equal {raw_bump(&mut metrics,"equal_cross_page");}
        }
        let ts=terminal_start.contains(&boundary);
        let te=terminal_end.contains(&boundary);
        let is=internal_start.contains(&boundary);
        let ie=internal_end.contains(&boundary);
        if ts||te||is||ie {
            raw_bump(&mut metrics,"at_cr_any");
            if equal {raw_bump(&mut metrics,"equal_at_cr_any");}
        }else {
            raw_bump(&mut metrics,"outside_cr");
            if equal {raw_bump(&mut metrics,"equal_outside_cr");}
        }
        for (flag,name,equal_name) in [
            (ts,"terminal_cr_start","equal_terminal_cr_start"),
            (te,"terminal_cr_end","equal_terminal_cr_end"),
            (is,"internal_cr_start","equal_internal_cr_start"),
            (ie,"internal_cr_end","equal_internal_cr_end"),
            (story_end.contains(&boundary),"same_story_end","equal_same_story_end")
        ]{
            if flag {
                raw_bump(&mut metrics,name);
                if equal {raw_bump(&mut metrics,equal_name);}
            }
        }
    }
    ensure!(metrics["comparable_pairs"]+metrics["duplicate_end_pairs"]==
        records.len().saturating_sub(1),"FDPC partition count inconsistent");
    ensure!(metrics["adjacent_alias"]+metrics["adjacent_equal_distinct"]
        +metrics["adjacent_different"]==metrics["comparable_pairs"],
        "FDPC style type partition inconsistent");
    ensure!(metrics["at_cr_any"]+metrics["outside_cr"]==metrics["comparable_pairs"],
        "FDPC CR position partition inconsistent");
    ensure!(metrics["within_page"]+metrics["cross_page"]==metrics["comparable_pairs"],
        "FDPC page partition inconsistent");
    Ok(metrics)
}


// NEW question: for every raw-equal FDPC page seam, do the physical
// page addresses have distinct BTEC entries and a matching PLC boundary?
// This does not infer any native Publisher reallocation/write policy.
const BTEC_METRICS:[&str;23]=[
"fdpc_pages","fdpc_records","btec_descriptors","btec_rows",
"nonzero_flags_descriptors","zero_sentinel_rows",
"targets_found","targets_missing","pages_one_target",
"pages_zero_targets","pages_multiple_targets",
"row_end_matches_page","row_end_mismatches_page",
"cross_page_seams","cross_page_linked","cross_page_distinct_rows",
"cross_page_boundary_join",
"raw_equal_seams","equal_linked","equal_distinct_rows",
"equal_boundary_join","equal_same_btec_descriptor",
"equal_different_btec_descriptor"
];
fn inc(m:&mut BTreeMap<String,usize>,k:&str) {
    *m.get_mut(k).expect("metric must have been declared")+=1;
}
fn btec_fdpc_links(
  quill:&[u8],catalog:&pub_quill::QuillStoryCatalog,
  text_start:u32,text_end:u32
)->Result<Value> {
    let mut m=BTEC_METRICS.iter()
        .map(|&k|(k.to_string(),0usize)).collect::<BTreeMap<_,_>>();
    let descriptors=catalog.descriptor_nodes.iter()
        .flat_map(|n|n.descriptors.iter()).collect::<Vec<_>>();
    // (physical FDPC payload start, final text boundary)
    let mut pages=Vec::<(u32,u32)>::new();
    // (text-end boundary, physical raw-style body start, raw length, page index)
    let mut entries=Vec::<(u32,usize,usize,usize)>::new();
    let mut address_to_page=BTreeMap::<u32,usize>::new();
    for d in descriptors.iter().copied().filter(|d|d.name.value==*b"FDPC") {
        let begin=usize::try_from(d.data_offset.value)?;
        let len=usize::try_from(d.data_length.value)?;
        let end=begin.checked_add(len).context("FDPC arithmetic overflow")?;
        let chunk=quill.get(begin..end).context("FDPC out of range")?;
        ensure!(chunk.len()>=8,"FDPC short header");
        let n=usize::from(u16::from_le_bytes(chunk[0..2].try_into()?));
        ensure!(n>0&&n<=16384,"FDPC invalid count");
        let tables=8usize.checked_add(n.checked_mul(6).context("FDPC count overflow")?)
            .context("FDPC table overflow")?;
        ensure!(tables<=chunk.len(),"FDPC table extends past descriptor");
        let page_index=pages.len();
        ensure!(address_to_page.insert(d.data_offset.value,page_index).is_none(),
            "FDPC descriptor physical offset repeated");
        let mut previous=0u32;
        for k in 0..n {
            let p=8+k*4;
            let stop=u32::from_le_bytes(chunk[p..p+4].try_into()?);
            ensure!(stop>=text_start&&stop<=text_end&&(stop-text_start)%2==0,
                "FDPC text offset outside TEXT");
            if k>0 {ensure!(stop>previous,"FDPC page ends do not advance");}
            previous=stop;
            let q=8+n*4+k*2;
            let style_rel=usize::from(u16::from_le_bytes(chunk[q..q+2].try_into()?));
            ensure!(style_rel>=tables && style_rel+4<=chunk.len(),"FDPC raw style address");
            let length=usize::try_from(u32::from_le_bytes(
                chunk[style_rel..style_rel+4].try_into()?))?;
            let style_end=style_rel.checked_add(length).context("FDPC style length overflow")?;
            ensure!(length>=4&&style_end<=chunk.len(),"FDPC raw style span");
            entries.push((stop,begin+style_rel,length,page_index));
        }
        pages.push((d.data_offset.value,previous));
    }
    m.insert("fdpc_pages".into(),pages.len());
    m.insert("fdpc_records".into(),entries.len());
    let btec=descriptors.iter().copied().filter(|d|d.name.value==*b"BTEC").collect::<Vec<_>>();
    m.insert("btec_descriptors".into(),btec.len());
    if btec.is_empty() {
        return Ok(json!({"status":"ABSENT","metrics":null,"equal_witnesses":[]}));
    }
    // Generic libwps P_ABS / T_CST type-4 PLC framing; all values stay raw
    // except first stored zero, which is evaluated *separately* as TEXT.begin.
    // (physical target, logical_start, logical_end, BTEC descriptor ordinal)
    let mut rows=Vec::<(u32,u32,u32,usize)>::new();
    for (didx,d) in btec.iter().enumerate(){
        let begin=usize::try_from(d.data_offset.value)?;
        let len=usize::try_from(d.data_length.value)?;
        let end=begin.checked_add(len).context("BTEC end overflow")?;
        let chunk=quill.get(begin..end).context("BTEC out of Quill")?;
        ensure!(chunk.len()>=16,"BTEC header too short");
        let n=usize::try_from(u32::from_le_bytes(chunk[0..4].try_into()?))?;
        let width=u32::from_le_bytes(chunk[4..8].try_into()?);
        ensure!(n>0&&n<=65535&&width==4,"BTEC not a supported type-4 PLC");
        let length=16usize.checked_add(n.checked_mul(8).context("BTEC count overflow")?)
            .context("BTEC PLC overflow")?;
        ensure!(length==chunk.len(),"BTEC PLC length not exact");
        if chunk[8..12].iter().any(|&x|x!=0){ inc(&mut m,"nonzero_flags_descriptors");}
        let mut pos=Vec::<u32>::with_capacity(n+1);
        for k in 0..=n {
            let at=12+k*4;
            let raw=u32::from_le_bytes(chunk[at..at+4].try_into()?);
            let resolved=if raw==0 {text_start} else {raw};
            ensure!(resolved>=text_start&&resolved<=text_end
                &&(resolved-text_start)%2==0,"BTEC logical position out of TEXT");
            if raw==0 { inc(&mut m,"zero_sentinel_rows");}
            pos.push(resolved);
        }
        for k in 0..n {
            ensure!(pos[k+1]>=pos[k],"BTEC logical positions decrease");
            let at=12+(n+1)*4+k*4;
            let target=u32::from_le_bytes(chunk[at..at+4].try_into()?);
            rows.push((target,pos[k],pos[k+1],didx));
        }
    }
    m.insert("btec_rows".into(),rows.len());
    let mut refs=vec![Vec::<usize>::new();pages.len()];
    for (i,r) in rows.iter().enumerate(){
        if let Some(&page)=address_to_page.get(&r.0) {
            inc(&mut m,"targets_found");
            refs[page].push(i);
            if r.2==pages[page].1 {inc(&mut m,"row_end_matches_page");}
            else {inc(&mut m,"row_end_mismatches_page");}
        } else {inc(&mut m,"targets_missing");}
    }
    for v in &refs {
        if v.is_empty(){inc(&mut m,"pages_zero_targets");}
        else if v.len()==1{inc(&mut m,"pages_one_target");}
        else {inc(&mut m,"pages_multiple_targets");}
    }
    entries.sort_by_key(|x|(x.0,x.3));
    let mut witnesses=Vec::<Value>::new();
    for w in entries.windows(2) {
        let before=w[0];let after=w[1];
        if before.0==after.0||before.3==after.3 {continue;}
        inc(&mut m,"cross_page_seams");
        let a=quill.get(before.1..before.1+before.2).context("raw style A out of Quill")?;
        let b=quill.get(after.1..after.1+after.2).context("raw style B out of Quill")?;
        let equal=a==b;
        if equal{inc(&mut m,"raw_equal_seams");}
        let a_ref=&refs[before.3]; let b_ref=&refs[after.3];
        let joined=a_ref.len()==1 && b_ref.len()==1;
        if joined {
            inc(&mut m,"cross_page_linked");
            let arow=a_ref[0];let brow=b_ref[0];
            let distinct=arow!=brow && rows[arow].0!=rows[brow].0;
            let logical_join=rows[arow].2==before.0
                && rows[brow].1==before.0;
            if distinct {inc(&mut m,"cross_page_distinct_rows");}
            if logical_join {inc(&mut m,"cross_page_boundary_join");}
            if equal {
                inc(&mut m,"equal_linked");
                if distinct {inc(&mut m,"equal_distinct_rows");}
                if logical_join {inc(&mut m,"equal_boundary_join");}
                if rows[arow].3==rows[brow].3 {
                    inc(&mut m,"equal_same_btec_descriptor");
                } else { inc(&mut m,"equal_different_btec_descriptor"); }
            }
        }
        if equal {
            // Numeric witness only: never persist style bytes, hash, text or PUB.
            let a_ref_index=if a_ref.len()==1{Some(a_ref[0])}else{None};
            let b_ref_index=if b_ref.len()==1{Some(b_ref[0])}else{None};
            let logical_match=match (a_ref_index,b_ref_index){
                (Some(ai),Some(bi))=>rows[ai].2==before.0&&rows[bi].1==before.0,
                _=>false,
            };
            witnesses.push(json!({
                "boundary_absolute":before.0,
                "before_fdpc_page":before.3,
                "after_fdpc_page":after.3,
                "before_fdpc_target":pages[before.3].0,
                "after_fdpc_target":pages[after.3].0,
                "before_btec_row":a_ref_index,
                "after_btec_row":b_ref_index,
                "fully_linked":joined,
                "distinct_target_rows":joined && a_ref_index!=b_ref_index
                    && pages[before.3].0!=pages[after.3].0,
                "logical_boundary_join":logical_match
            }));
        }
    }
    ensure!(m["cross_page_seams"]<=entries.len().saturating_sub(1),
        "cross-page count exceeds records");
    ensure!(m["raw_equal_seams"]==witnesses.len(),
        "equal seam witness count inconsistent");
    ensure!(m["targets_found"]+m["targets_missing"]==m["btec_rows"],
        "BTEC target count mismatch");
    ensure!(m["pages_one_target"]+m["pages_zero_targets"]
        +m["pages_multiple_targets"]==m["fdpc_pages"],"FDPC page ownership mismatch");
    let complete=m["targets_missing"]==0
        &&m["pages_zero_targets"]==0
        &&m["pages_multiple_targets"]==0
        &&m["row_end_mismatches_page"]==0;
    Ok(json!({
        "status":if complete{"COMPLETE"}else{"PARTIAL"},
        "metrics":m,
        "equal_witnesses":witnesses
    }))
}

fn inspect(source:&[u8], expected:&str)->Result<Value>{
    ensure!(sha256_hex(source)==expected,"SHA mismatch");
    ensure!(source.starts_with(&[0xd0,0xcf,0x11,0xe0,0xa1,0xb1,0x1a,0xe1]),"not CFB");
    let mut out=stat_frame(source,expected,"ANALYSIS_BLOCKED");
    let quill=match pub_cfb::read_stream_reader(Cursor::new(source),pub_reader::QUILL_STREAM_PATH){
        Ok(x)=>x,Err(_)=>{
            out["status"]=json!("NO_QUILL_STREAM_OR_CFB_ERROR");return Ok(out)
        }
    };
    let catalog=match pub_quill::parse_confirmed_story_catalog(
       StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&quill){
        Ok(x)=>x,Err(_)=>{
            out["status"]=json!("QUILL_CATALOG_BLOCKED");return Ok(out)
        }
    };
    let all=catalog.descriptor_nodes.iter()
        .flat_map(|node|node.descriptors.iter()).collect::<Vec<_>>();
    let texts=all.iter().filter(|d|d.name.value==*b"TEXT").collect::<Vec<_>>();
    if texts.len()!=1 {
        out["status"]=json!("TEXT_DESCRIPTOR_NOT_UNIQUE");return Ok(out)
    }
    let text_start=usize::try_from(texts[0].data_offset.value)?;
    let text_size=usize::try_from(texts[0].data_length.value)?;
    let text_end=text_start.checked_add(text_size).context("TEXT end overflow")?;
    if text_size%2!=0||text_end>quill.len(){
        out["status"]=json!("TEXT_SPAN_INVALID");return Ok(out)
    }
    let text=&quill[text_start..text_end];
    let text_start_u32=u32::try_from(text_start)?;
    let text_end_u32=u32::try_from(text_end)?;
    let (fdpp,pp_pages)=match decode_fd(&quill,&catalog,*b"FDPP",text_start_u32,text_end_u32){
        Ok(v)=>v,Err(_)=>{
            out["status"]=json!("FDPP_STRUCTURE_BLOCKED");return Ok(out)
        }
    };
    let (fdpc,pc_pages)=match decode_fd(&quill,&catalog,*b"FDPC",text_start_u32,text_end_u32){
        Ok(v)=>v,Err(_)=>{
            out["status"]=json!("FDPC_STRUCTURE_BLOCKED");return Ok(out)
        }
    };
    let raw_cr_ends=(0..text.len()).step_by(2).filter(|&i|cr_at(text,i))
        .map(|i|u32::try_from(text_start+i+2)).collect::<Result<Vec<_>,_>>()?;
    let fdpc_set=fdpc.iter().copied().collect::<BTreeSet<_>>();
    let mut story_spans=Vec::<(usize,usize)>::new();
    let mut terminals=0usize;let mut nonterminals=0usize;let mut empties=0usize;
    let mut internal_cr=0usize;let mut terminal_cr=0usize;
    let mut terminal_isolations=[0usize;4];
    let mut internal_isolations=[0usize;4];
    let mut seen_cr_positions=BTreeSet::new();
    let mut terminal_cr_starts=BTreeSet::new();
    let mut terminal_cr_ends=BTreeSet::new();
    let mut internal_cr_starts=BTreeSet::new();
    let mut internal_cr_ends=BTreeSet::new();
    let mut story_ends=BTreeSet::new();
    let mut story_mismatch=0usize;
    let mut last_cr_missing=Vec::new();
    for (index,story) in catalog.stories.iter().enumerate(){
        let start=usize::try_from(story.text_source.offset)?;
        let end=usize::try_from(story.text_source.end().context("story end overflow")?)?;
        if start<text_start || end>text_end||end<start||
           (start-text_start)%2!=0||(end-start)%2!=0{
            out["status"]=json!("STORY_SPAN_INVALID");return Ok(out)
        }
        story_spans.push((start,end));
        if quill.get(start..end)!=Some(story.utf16le.as_slice()){
            story_mismatch+=1
        }
        if start==end {
            empties+=1;continue;
        }
        let is_terminal=cr_at(&quill,end-2);
        if is_terminal {terminals+=1} else {
            nonterminals+=1;
            if last_cr_missing.len()<SAMPLE_LIMIT {last_cr_missing.push(index)}
        }
        for j in (start..end).step_by(2){
            if !cr_at(&quill,j){continue}
            let at_start=u32::try_from(j)?;
            let at_end=u32::try_from(j+2)?;
            seen_cr_positions.insert(at_end);
            let before=fdpc_set.contains(&at_start);
            let after=fdpc_set.contains(&at_end);
            let cat=match (before,after){
                (true,true)=>0,
                (true,false)=>1,
                (false,true)=>2,
                (false,false)=>3,
            };
            if j+2==end{
                terminal_cr+=1;terminal_isolations[cat]+=1;
                terminal_cr_starts.insert(at_start);
                terminal_cr_ends.insert(at_end);
                story_ends.insert(at_end);
            }else{
                internal_cr+=1;internal_isolations[cat]+=1;
                internal_cr_starts.insert(at_start);
                internal_cr_ends.insert(at_end);
            }
        }
    }
    story_spans.sort_unstable();
    let mut previous=text_start;let mut gap_bytes=0usize;let mut overlap_bytes=0usize;
    for &(s,e) in &story_spans {
        if s>previous {gap_bytes+=s-previous}
        if s<previous {overlap_bytes+=previous-s.min(e)}
        previous=previous.max(e);
    }
    if previous<text_end {gap_bytes+=text_end-previous}
    let partition_exact=gap_bytes==0 && overlap_bytes==0;
    let uncatalogued_cr=raw_cr_ends.iter()
        .filter(|v|!seen_cr_positions.contains(v)).count();
    let (missing,extra,missing_sample,extra_sample)=diff_multiset(&raw_cr_ends,&fdpp);
    let pp_unique=fdpp.iter().copied().collect::<BTreeSet<_>>().len();
    let pc_unique=fdpc_set.len();
    let raw_style=match raw_fdpc_styles(
        &quill,&catalog,text_start_u32,text_end_u32,
        &terminal_cr_starts,&terminal_cr_ends,
        &internal_cr_starts,&internal_cr_ends,
        &story_ends,fdpc.len()
    ) {
        Ok(v)=>v,
        Err(_)=>{
            out["status"]=json!("FDPC_RAW_STYLE_BLOCKED");return Ok(out)
        }
    };
    let btec_link=match btec_fdpc_links(
        &quill,&catalog,text_start_u32,text_end_u32
    ){
        Ok(v)=>v,
        Err(_)=>json!({"status":"STRUCTURE_BLOCKED",
            "metrics":null,"equal_witnesses":[]})
    };
    out["status"]=json!("ANALYZED");
    out["stats"]=json!({
        "quill_bytes":quill.len(),"text_offset":text_start,"text_bytes":text.len(),
        "story_count":catalog.stories.len(),
        "nonempty_stories":terminals+nonterminals,"zero_length_stories":empties,
        "story_terminal_cr":terminals,"story_missing_terminal_cr":nonterminals,
        "story_terminal_missing_ordinal_sample":last_cr_missing,
        "story_catalog_byte_mismatches":story_mismatch,
        "story_partition_exact":partition_exact,
        "story_gap_bytes":gap_bytes,"story_overlap_bytes":overlap_bytes,
        "raw_cr_count":raw_cr_ends.len(),
        "story_terminal_cr_count":terminal_cr,"story_internal_cr_count":internal_cr,
        "raw_cr_not_owned_by_stories":uncatalogued_cr,
        "fdpp_page_count":pp_pages,"fdpp_entry_count":fdpp.len(),"fdpp_unique":pp_unique,
        "fdpp_duplicate_entries":fdpp.len()-pp_unique,
        "fdpc_page_count":pc_pages,"fdpc_entry_count":fdpc.len(),"fdpc_unique":pc_unique,
        "fdpc_duplicate_entries":fdpc.len()-pc_unique,
        "fdpp_equal_raw_cr_multiset":missing==0&&extra==0,
        "fdpp_missing_cr_ends":missing,"fdpp_extraneous_entries":extra,
        "fdpp_missing_offset_sample":missing_sample,"fdpp_extraneous_offset_sample":extra_sample,
        "fdpc_terminal_both":terminal_isolations[0],
        "fdpc_terminal_start_only":terminal_isolations[1],
        "fdpc_terminal_end_only":terminal_isolations[2],
        "fdpc_terminal_neither":terminal_isolations[3],
        "fdpc_internal_both":internal_isolations[0],
        "fdpc_internal_start_only":internal_isolations[1],
        "fdpc_internal_end_only":internal_isolations[2],
        "fdpc_internal_neither":internal_isolations[3],
        "fdpc_raw_style":raw_style,
        "btec_link":btec_link
    });
    ensure!(sha256_hex(source)==expected,"original mutated");
    Ok(out)
}
fn main()->Result<()>{
    let mut it=env::args().skip(1);
    let src=it.next().context("source file")?;
    let sha=it.next().context("expected sha")?;
    let receipt=it.next().context("receipt file")?;
    ensure!(it.next().is_none(),"extra argument");
    ensure!(sha.len()==64&&sha.bytes().all(|x|x.is_ascii_hexdigit()),"invalid SHA");
    let bytes=fs::read(src)?;
    ensure!(bytes.len()<=MAX_SOURCE,"source size limit");
    let out=match inspect(&bytes,&sha){
        Ok(v)=>v,Err(_)=>stat_frame(&bytes,&sha,"ANALYSIS_BLOCKED")
    };
    let mut w=fs::OpenOptions::new().create_new(true).write(true).open(receipt)?;
    w.write_all(&serde_json::to_vec_pretty(&out)?)?;
    w.write_all(b"\n")?;
    w.sync_all()?;
    println!("{}",serde_json::to_string(&json!({"status":out["status"]}))?);
    Ok(())
}
