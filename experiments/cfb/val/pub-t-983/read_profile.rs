//! PUB-T-983: bounded public-PUB heap/IO profiles of the *original* pub_cfb API.
//! Data and identity outputs stay within temporary CI workspace; receipt is numeric only.
use anyhow::{Context, Result, ensure};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    alloc::{GlobalAlloc, Layout, System},
    env, fs,
    io::{self, Cursor, Read, Seek, SeekFrom, Write},
    sync::atomic::{AtomicBool, AtomicU64, Ordering},
    time::Instant,
};
const MAX_SOURCE:usize=512*1024;
const QUILL:&str="/Quill/QuillSub/CONTENTS";
static ACTIVE:AtomicBool=AtomicBool::new(false);
static CURRENT:AtomicU64=AtomicU64::new(0);
static PEAK:AtomicU64=AtomicU64::new(0);
static TOTAL:AtomicU64=AtomicU64::new(0);
static ALLOCS:AtomicU64=AtomicU64::new(0);
static IO_BYTES:AtomicU64=AtomicU64::new(0);
static IO_READS:AtomicU64=AtomicU64::new(0);
static IO_SEEKS:AtomicU64=AtomicU64::new(0);
struct TallyAllocator;
#[global_allocator] static ALLOCATOR:TallyAllocator=TallyAllocator;
unsafe impl GlobalAlloc for TallyAllocator {
    unsafe fn alloc(&self,layout:Layout)->*mut u8{
        let out=unsafe{System.alloc(layout)};
        if !out.is_null()&&ACTIVE.load(Ordering::Relaxed){
            let current=CURRENT.fetch_add(layout.size() as u64,Ordering::Relaxed)+layout.size() as u64;
            PEAK.fetch_max(current,Ordering::Relaxed);
            TOTAL.fetch_add(layout.size() as u64,Ordering::Relaxed);
            ALLOCS.fetch_add(1,Ordering::Relaxed);
        }
        out
    }
    unsafe fn dealloc(&self,ptr:*mut u8,layout:Layout){
        if ACTIVE.load(Ordering::Relaxed){
            CURRENT.fetch_sub(layout.size() as u64,Ordering::Relaxed);
        }
        unsafe{System.dealloc(ptr,layout)};
    }
    unsafe fn realloc(&self,ptr:*mut u8,layout:Layout,new_size:usize)->*mut u8{
        let out=unsafe{System.realloc(ptr,layout,new_size)};
        if !out.is_null()&&ACTIVE.load(Ordering::Relaxed){
            let old=layout.size() as u64;
            let new=new_size as u64;
            if new>=old{
                let diff=new-old;
                let current=CURRENT.fetch_add(diff,Ordering::Relaxed)+diff;
                PEAK.fetch_max(current,Ordering::Relaxed);
                TOTAL.fetch_add(diff,Ordering::Relaxed);
            } else {
                CURRENT.fetch_sub(old-new,Ordering::Relaxed);
            }
            ALLOCS.fetch_add(1,Ordering::Relaxed);
        }
        out
    }
}
struct Meter<R>{inner:R}
impl<R:Read> Read for Meter<R>{
    fn read(&mut self, buf:&mut[u8])->io::Result<usize>{
        let size=self.inner.read(buf)?;
        if ACTIVE.load(Ordering::Relaxed){
            IO_READS.fetch_add(1,Ordering::Relaxed);
            IO_BYTES.fetch_add(size as u64,Ordering::Relaxed);
        }
        Ok(size)
    }
}
impl<R:Seek> Seek for Meter<R>{
    fn seek(&mut self,p:SeekFrom)->io::Result<u64>{
        let result=self.inner.seek(p)?;
        if ACTIVE.load(Ordering::Relaxed){IO_SEEKS.fetch_add(1,Ordering::Relaxed);}
        Ok(result)
    }
}
fn reset(){
    assert!(!ACTIVE.load(Ordering::SeqCst));
    CURRENT.store(0,Ordering::SeqCst);PEAK.store(0,Ordering::SeqCst);
    TOTAL.store(0,Ordering::SeqCst);ALLOCS.store(0,Ordering::SeqCst);
    IO_BYTES.store(0,Ordering::SeqCst);IO_READS.store(0,Ordering::SeqCst);
    IO_SEEKS.store(0,Ordering::SeqCst);
    ACTIVE.store(true,Ordering::SeqCst)
}
// NOTE: timed samples run single-threaded. Peak counts bytes allocated *during*
// each measured call, not total process RSS, and exclude pre-loaded input fixture.
fn sample<T,F:FnOnce()->Result<T>>(operation:&str,repeat:usize, f:F)->Result<(T,Value)>{
    reset();let clock=Instant::now();let result=f();
    let micros=clock.elapsed().as_micros() as u64;
    ACTIVE.store(false,Ordering::SeqCst);
    let record=json!({"op":operation,"repeat":repeat,
        "peak_live_new_heap_bytes":PEAK.load(Ordering::SeqCst),
        "allocated_bytes_total":TOTAL.load(Ordering::SeqCst),
        "allocation_calls":ALLOCS.load(Ordering::SeqCst),
        "read_calls":IO_READS.load(Ordering::SeqCst),
        "source_read_bytes":IO_BYTES.load(Ordering::SeqCst),
        "source_seeks":IO_SEEKS.load(Ordering::SeqCst),
        "elapsed_us":micros});
    Ok((result?,record))
}
fn sha_hex(b:&[u8])->String{
    Sha256::digest(b).iter().map(|x|format!("{x:02x}")).collect()
}
fn read_quill(input:&[u8])->Result<Vec<u8>>{
    pub_cfb::read_stream_reader(Meter{inner:Cursor::new(input)},QUILL)
}
fn inspect(input:&[u8])->Result<pub_cfb::CfbInventory>{
    pub_cfb::inspect_reader(Meter{inner:Cursor::new(input)})
}
fn identity_replace(input:&[u8],quill:&[u8])->Result<Vec<u8>>{
    pub_cfb::replace_stream_reader(Meter{inner:Cursor::new(input)},QUILL,quill)
}
fn inspect_case(input:&[u8],expected:&str)->Result<Value>{
    ensure!(input.len()<=MAX_SOURCE,"file exceeds fixed public-input bound");
    ensure!(sha_hex(input)==expected,"source SHA drift");
    let inventory=inspect(input)?;
    let paths=inventory.entries.iter()
        .filter(|x|x.kind==pub_cfb::EntryKind::Stream)
        .map(|x|x.path.to_string()).collect::<Vec<_>>();
    let stream_bytes:u64=inventory.entries.iter()
        .filter(|x|x.kind==pub_cfb::EntryKind::Stream)
        .map(|x|x.len as u64).sum();
    let status=if paths.iter().any(|p|p==QUILL){"EVALUATED"}else{"NO_QUILL"};
    if status!="EVALUATED" {
        return Ok(json!({"schema":"sk1.pub-t-983.file.v1",
            "status":status,"source_sha256":expected,
            "source_bytes":input.len(),"stream_count":paths.len(),
            "stream_bytes":stream_bytes,"quill_bytes":0,
            "measurements":[],"output_bytes":null,
            "logical_streams_equal":null,"native_publisher_acceptance":"NOT_EVALUATED"}))
    }
    let quill=read_quill(input)?;
    let mut measures=Vec::new();
    let mut outputs=Vec::new();
    for operation in ["inspect","read_quill","identity_replace"] {
        for repeat in 0..3usize {
            match operation{
                "inspect"=>{
                    let (_,m)=sample(operation,repeat,||inspect(input))?;
                    measures.push(m)
                }
                "read_quill"=>{
                    let (bytes,m)=sample(operation,repeat,||read_quill(input))?;
                    ensure!(bytes==quill,"read bytes differed");measures.push(m)
                }
                "identity_replace"=>{
                    let (out,m)=sample(operation,repeat,||identity_replace(input,&quill))?;
                    ensure!(out.len()<=2*MAX_SOURCE,"unexpected output size");
                    outputs.push(out);measures.push(m)
                }
                _=>unreachable!()
            }
        }
    }
    ensure!(outputs.len()==3,"missing identity outputs");
    ensure!(outputs.windows(2).all(|w|w[0]==w[1]),"identity replacement nondeterministic");
    let output=&outputs[0];let revised=inspect(output)?;
    let revised_paths=revised.entries.iter()
        .filter(|x|x.kind==pub_cfb::EntryKind::Stream).map(|x|x.path.to_string())
        .collect::<Vec<_>>();
    ensure!(paths==revised_paths,"logical stream path changed");
    let mut all_equal=true;
    for path in &paths {
        let a=pub_cfb::read_stream_reader(Cursor::new(input),path)?;
        let b=pub_cfb::read_stream_reader(Cursor::new(output),path)?;
        if a!=b {all_equal=false}
    }
    ensure!(all_equal,"identity replace lost a logical stream");
    Ok(json!({"schema":"sk1.pub-t-983.file.v1","status":"EVALUATED",
        "source_sha256":expected,"source_bytes":input.len(),
        "stream_count":paths.len(),"stream_bytes":stream_bytes,
        "quill_bytes":quill.len(),"measurements":measures,
        "output_bytes":output.len(),"logical_streams_equal":all_equal,
        "native_publisher_acceptance":"NOT_EVALUATED"}))
}
fn main()->Result<()>{
    let mut args=env::args().skip(1);
    let path=args.next().context("source file")?;
    let sha=args.next().context("expected digest")?;
    let receipt=args.next().context("receipt")?;
    ensure!(args.next().is_none(),"unsupported args");
    ensure!(sha.len()==64&&sha.bytes().all(|x|x.is_ascii_hexdigit()),"bad SHA");
    let original=fs::read(path)?;
    let result=inspect_case(&original,&sha)?;
    let mut file=fs::OpenOptions::new().create_new(true).write(true).open(receipt)?;
    file.write_all(&serde_json::to_vec_pretty(&result)?)?;
    file.write_all(b"\n")?;file.sync_all()?;
    println!("{}",serde_json::to_string(&json!({"status":result["status"]}))?);
    Ok(())
}
