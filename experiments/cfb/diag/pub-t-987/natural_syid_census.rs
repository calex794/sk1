//! PUB-T-987 natural, source-immutable census of all pinned 625 PUB from Lalamu.
//! Only safe SHA + scalar Quill properties leave the isolated GitHub worker.
//! No Writer, mutation, or native Publisher.
use anyhow::{ensure, Context, Result};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{env, fs, io::{Cursor,Write}, path::Path};

fn hex_sha256(bytes:&[u8])->String {
    let digest=Sha256::digest(bytes);
    digest.iter().map(|b|format!("{b:02x}")).collect::<String>()
}
fn scan_one(path:&Path)->Result<Value>{
    let stem=path.file_stem().context("stem")?.to_str().context("utf8 stem")?;
    ensure!(stem.len()==64 && stem.bytes().all(|b|b.is_ascii_hexdigit()&& !b.is_ascii_uppercase()),
        "non hash-named donor object");
    let bytes=fs::read(path)?;
    ensure!(hex_sha256(&bytes)==stem,"donor PUB immutable SHA mismatch");
    let mut row=json!({
        "source_sha256":stem,
        "source_bytes":bytes.len(),
        "status":"NOT_EVALUATED",
        "syid_header":Value::Null,
        "syid_count":Value::Null,
        "syid_max_live":Value::Null,
        "low_byte":Value::Null,
        "is_fe_ff_boundary":false,
        "original_bytes_immutable":true
    });
    if !bytes.starts_with(&[0xd0,0xcf,0x11,0xe0,0xa1,0xb1,0x1a,0xe1]){
        row["status"]=json!("NOT_CFB");
        return Ok(row);
    }
    let stream=match pub_cfb::read_stream_reader(
        Cursor::new(&bytes),pub_reader::QUILL_STREAM_PATH){
        Ok(x)=>x,
        Err(_)=>{
            row["status"]=json!("QUILL_STREAM_UNAVAILABLE");
            return Ok(row);
        }
    };
    let catalog=match pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&stream){
        Ok(x)=>x,
        Err(_)=>{
            row["status"]=json!("QUILL_SYID_PARSE_BLOCKED");
            return Ok(row);
        }
    };
    let header=catalog.syid.header.value;
    let low=header & 0xff;
    row["status"]=json!("NATURAL_SYID_PARSED");
    row["syid_header"]=json!(header);
    row["syid_count"]=json!(catalog.syid.count.value);
    row["syid_max_live"]=json!(catalog.syid.ids.iter().map(|x|x.value.0).max());
    row["low_byte"]=json!(low);
    row["is_fe_ff_boundary"]=json!(low==0xfe || low==0xff);
    Ok(row)
}
fn main()->Result<()>{
    let mut a=env::args().skip(1);
    let directory=a.next().context("donor native PUB directory")?;
    let output=a.next().context("safe receipt output")?;
    ensure!(a.next().is_none(),"unexpected arguments");
    let root=Path::new(&directory);
    let mut files=fs::read_dir(root)?.map(|e|e.map(|v|v.path()))
        .collect::<std::io::Result<Vec<_>>>()?;
    files.sort();
    ensure!(files.len()==625,"donor inventory count not pinned to 625");
    ensure!(files.iter().all(|p|p.is_file() &&
        p.extension().is_some_and(|s|s=="pub")),"unrecognized donor entry");
    let mut records=Vec::<Value>::with_capacity(files.len());
    for file in &files{
        records.push(scan_one(file)?);
    }
    let all=records.len();
    let parsed=records.iter().filter(|r|r["status"]=="NATURAL_SYID_PARSED").count();
    let positives=records.iter().filter(|r|r["is_fe_ff_boundary"]==true).count();
    let receipt=json!({
        "schema":"sk1.cfb-diag-pub-t-987.census.v1",
        "planned_pub":625,
        "source_immutable_sha_verified":all,
        "rows":records
    });
    let mut f=fs::OpenOptions::new().write(true).create_new(true).open(output)?;
    f.write_all(&serde_json::to_vec_pretty(&receipt)?)?;
    f.write_all(b"\n")?;
    f.sync_all()?;
    println!("{}",json!({"source_sha_verified":all,"quill_syid_parsed":parsed,
                          "natural_fe_ff_candidates":positives}));
    Ok(())
}
