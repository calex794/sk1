//! PUB-T-995: public original 29-PUB Quill/SYID live-ID highwater discrimination.
//! Uses the exact pinned production parser; only numerical IDs leave the runner.
//! This is a source-only study: no Writer or changes to any source bytes.
use anyhow::{ensure, Context, Result};
use serde_json::{json,Value};
use sha2::{Digest,Sha256};
use std::{collections::{BTreeSet,BTreeMap},env,fs,io::{Cursor,Write},path::Path};

const A_SHA:&str="b4b005a7e6f662546cf07bdd155a1cf936293e6ceb6ac7f424456fee87051f1b";
const B_SHA:&str="3562f0fe51e5e1dbf42f81f574cea831b0734f6d08a9a1a9cc610c84f44caeff";
const SCHEMA:&str="sk1.quill-diag-pub-t-995.live-ids.v1";

fn hex_sha256(bytes:&[u8])->String{
    Sha256::digest(bytes).iter().map(|b|format!("{b:02x}")).collect()
}
fn scan_one(path:&Path)->Result<Value>{
    let stem=path.file_stem().context("filename stem")?.to_str().context("utf8 stem")?;
    ensure!(stem.len()==64 && stem.bytes().all(|b|b.is_ascii_hexdigit() && !b.is_ascii_uppercase()),
            "not a hash-named source");
    let bytes=fs::read(path)?;
    ensure!(hex_sha256(&bytes)==stem,"original source SHA changed");
    let mut row=json!({
        "source_sha256":stem,"source_bytes":bytes.len(),
        "status":"NOT_EVALUATED","original_immutable":true,
        "header":Value::Null,"count":Value::Null,"max_live":Value::Null,
        "ids":Value::Null,"unique_id_count":Value::Null,"duplicate_id_count":Value::Null,
        "header_minus_max_live":Value::Null,"header_ge_live_max":Value::Null
    });
    if !bytes.starts_with(&[0xd0,0xcf,0x11,0xe0,0xa1,0xb1,0x1a,0xe1]){
        row["status"]=json!("NOT_CFB"); return Ok(row);
    }
    let stream=match pub_cfb::read_stream_reader(
        Cursor::new(&bytes),pub_reader::QUILL_STREAM_PATH){
        Ok(x)=>x,Err(_)=>{row["status"]=json!("QUILL_STREAM_UNAVAILABLE");return Ok(row);}
    };
    let catalog=match pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&stream){
        Ok(x)=>x,Err(_)=>{row["status"]=json!("QUILL_SYID_PARSE_BLOCKED");return Ok(row);}
    };
    let ids=catalog.syid.ids.iter().map(|x|x.value.0).collect::<Vec<u32>>();
    let h=catalog.syid.header.value;
    let count=catalog.syid.count.value;
    let distinct=ids.iter().copied().collect::<BTreeSet<u32>>();
    let max_live=ids.iter().copied().max();
    row["status"]=json!("NATURAL_SYID_PARSED");
    row["header"]=json!(h);
    row["count"]=json!(count);
    row["max_live"]=json!(max_live);
    row["ids"]=json!(ids);
    row["unique_id_count"]=json!(distinct.len());
    row["duplicate_id_count"]=json!(ids.len().saturating_sub(distinct.len()));
    row["header_minus_max_live"]=max_live.map_or(Value::Null,|m|json!(i64::from(h)-i64::from(m)));
    row["header_ge_live_max"]=max_live.map_or(Value::Null,|m|json!(h>=m));
    Ok(row)
}
fn pair_metrics(a:&Value,b:&Value)->Result<Value>{
    if a["status"]!="NATURAL_SYID_PARSED" || b["status"]!="NATURAL_SYID_PARSED"{
        return Ok(json!({"source_a_sha256":A_SHA,"source_b_sha256":B_SHA,
                         "both_parsed":false,"comparison":Value::Null}));
    }
    let a_ids=a["ids"].as_array().context("source A ids")?;
    let b_ids=b["ids"].as_array().context("source B ids")?;
    let av=a_ids.iter().map(|x|x.as_u64().context("bad A ID").and_then(|v|u32::try_from(v).context("A ID overflow"))).collect::<Result<Vec<u32>>>()?;
    let bv=b_ids.iter().map(|x|x.as_u64().context("bad B ID").and_then(|v|u32::try_from(v).context("B ID overflow"))).collect::<Result<Vec<u32>>>()?;
    let ai=av.iter().copied().collect::<BTreeSet<u32>>();
    let bi=bv.iter().copied().collect::<BTreeSet<u32>>();
    let ah=a["header"].as_u64().context("A header")?;
    let bh=b["header"].as_u64().context("B header")?;
    let am=a["max_live"].as_u64().context("A max live")?;
    let bm=b["max_live"].as_u64().context("B max live")?;
    Ok(json!({
        "source_a_sha256":A_SHA,"source_b_sha256":B_SHA,
        "both_parsed":true,
        "comparison":{
          "source_a_header":ah,
          "source_b_header":bh,
          "header_delta_b_minus_a":i64::try_from(bh)?-i64::try_from(ah)?,
          "source_a_max_live":am,
          "source_b_max_live":bm,
          "max_live_delta_b_minus_a":i64::try_from(bm)?-i64::try_from(am)?,
          "source_a_live_count":av.len(),
          "source_b_live_count":bv.len(),
          "source_a_distinct_live_count":ai.len(),
          "source_b_distinct_live_count":bi.len(),
          "shared_distinct_ids":ai.intersection(&bi).count(),
          "a_only_distinct_ids":ai.difference(&bi).count(),
          "b_only_distinct_ids":bi.difference(&ai).count(),
          "same_ordinal_id_count":av.iter().zip(bv.iter()).filter(|(x,y)|x==y).count(),
          "source_a_header_live_gap":i64::try_from(ah)?-i64::try_from(am)?,
          "source_b_header_live_gap":i64::try_from(bh)?-i64::try_from(bm)?
        }
    }))
}
fn main()->Result<()>{
    let mut args=env::args().skip(1);
    let source=args.next().context("immutable originals directory")?;
    let output=args.next().context("source-safe JSON path")?;
    ensure!(args.next().is_none(),"unexpected CLI args");
    let mut paths=fs::read_dir(&source)?.map(|x|x.map(|p|p.path()))
        .collect::<std::io::Result<Vec<_>>>()?;
    paths.sort();
    ensure!(paths.len()==29,"not exactly 29 pre-registered originals");
    ensure!(paths.iter().all(|x|x.is_file() && x.extension().is_some_and(|a|a=="pub")),
            "non-PUB source entry");
    let mut rows=Vec::<Value>::new();
    for path in paths{rows.push(scan_one(&path)?);}
    let originals=rows.iter().filter(|x|x["status"]=="NATURAL_SYID_PARSED").count();
    let a=rows.iter().find(|x|x["source_sha256"]==A_SHA).context("A original absent")?;
    let b=rows.iter().find(|x|x["source_sha256"]==B_SHA).context("B original absent")?;
    let pair=pair_metrics(a,b)?;
    let mut gaps=BTreeMap::<String,usize>::new();
    let mut ge_count=0usize;
    let mut violation_count=0usize;
    let mut duplicate_count=0usize;
    for r in rows.iter().filter(|x|x["status"]=="NATURAL_SYID_PARSED"){
        if let Some(g)=r["header_minus_max_live"].as_i64(){
            *gaps.entry(g.to_string()).or_default()+=1;
            if g>=0{ge_count+=1}else{violation_count+=1;}
        }
        if r["duplicate_id_count"].as_u64().unwrap_or(0)>0 {duplicate_count+=1;}
    }
    let receipt=json!({
        "schema":SCHEMA,
        "registered_original_sources":29,
        "source_sha_verified":rows.len(),
        "original_Quill_parsed":originals,
        "parsed_with_header_ge_max_live":ge_count,
        "parsed_with_header_lt_max_live":violation_count,
        "parsed_with_duplicate_live_ids":duplicate_count,
        "numeric_header_gap_distribution":gaps,
        "pair":pair,
        "rows":rows,
        "source_bytes_artifact_exported":false,
        "writer_run":false,
        "native_microsoft_publisher_saveas":"NOT_EVALUATED"
    });
    let mut f=fs::OpenOptions::new().write(true).create_new(true).open(output)?;
    f.write_all(&serde_json::to_vec_pretty(&receipt)?)?;f.write_all(b"\n")?;f.sync_all()?;
    println!("{}",serde_json::to_string(&json!({
       "source_sha":29,"Quill_parsed":originals,
       "header_ge_max_live":ge_count,"violations":violation_count,
       "pair":receipt["pair"]["comparison"]}))?);
    Ok(())
}
