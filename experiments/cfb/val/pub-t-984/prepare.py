#!/usr/bin/env python3
"""PUB-T-984: pin and derive only a deterministic natural-Story selector
from the immutable T963 inverse Writer harness. No duplicate Writer code.
"""
from pathlib import Path
import argparse
import subprocess

T963="2caeec283312b0865054ae6f5f93fc9ac1c76b9d"
T971="69989902bfdc87fac1aeb57ccb6a1f78872831fd"
T963_BLOB="b7c2452ce837b87c4c68b5bcb2a956ec4fedfd92"
T971_BLOB="e6cd5892fa4a59e0612631e68855a169095df584"

def git(cwd,*args):
    return subprocess.check_output(["git",*args],cwd=cwd,text=True).strip()

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--ref-inverse",required=True,type=Path)
    p.add_argument("--ref-corpus",required=True,type=Path)
    opts=p.parse_args()
    inverse=opts.ref_inverse.resolve(strict=True)
    corpus=opts.ref_corpus.resolve(strict=True)
    assert git(inverse,"rev-parse","HEAD")==T963, "inverse parent commit changed"
    assert git(corpus,"rev-parse","HEAD")==T971, "public source cohort commit changed"
    original=inverse/"experiments/cfb/val/pub-t-963/inspect_inverse.rs"
    selector=corpus/"experiments/quill/val/pub-t-971/run.py"
    assert git(inverse,"hash-object",str(original))==T963_BLOB, "inverse harness changed"
    assert git(corpus,"hash-object",str(selector))==T971_BLOB, "cohort selector changed"
    source=original.read_text(encoding="utf-8")
    start="    let eligible=editor.graph().stories.iter()\n"
    end="    let mut out_stories=Vec::new();"
    assert source.count(start)==1 and source.count(end)==1
    old=source[source.index(start):source.index(end)]
    assert "let catalog=pub_quill::parse_confirmed_story_catalog(" in old
    assert "NO_PLAIN_EDITABLE_STORY" in old
    new="""    let original_quill=pub_cfb::read_stream_reader(
        Cursor::new(source),pub_reader::QUILL_STREAM_PATH)?;
    let catalog=match pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()), &original_quill){
        Ok(x)=>x, Err(_)=>{
            report["result"]=json!("SOURCE_QUILL_PARSE_BLOCKED");
            return Ok(report);
        }
    };
    report["source_syid_first_dword"]=json!(catalog.syid.header.value);
    report["source_syid_count"]=json!(catalog.syid.count.value);
    report["source_syid_max_live_id"]=json!(
        catalog.syid.ids.iter().map(|s|s.value.0).max());
    // Deterministic source catalog ordinal; never choose based on Writer result.
    let eligible=catalog.stories.iter().filter_map(|story|{
        let id=pub_reader::derive_pub_story_id(&source_hash,story.syid.0).ok()?;
        let value=editor.graph().stories.get(&id)?;
        let ascii_count=value.text.chars().filter(|c|c.is_ascii_alphanumeric()).count();
        if editor.can_replace_story_text(id).is_ok() && ascii_count>=2 {
            Some((id,value.text.clone()))
        } else {None}
    }).take(3).collect::<Vec<_>>();
    report["eligible_story_count"]=json!(eligible.len());
    if eligible.is_empty(){
        report["result"]=json!("NO_PLAIN_EDITABLE_STORY");
        return Ok(report);
    }
"""
    source=source.replace(old,new)
    old_picks='        let picks=[("first",0_usize),("second",1_usize.min(n-1)),("middle",(n-1)/2)];'
    assert source.count(old_picks)==1, "source picking policy changed"
    source=source.replace(old_picks,'        let picks=[("second",1_usize)];')
    source=source.replace("pub-t-963","pub-t-984").replace("PUB-T-963","PUB-T-984")
    assert "sk1.cfb-diag-pub-t-984.inverse.v1" in source
    target=Path(__file__).resolve().parent/"real_inverse.rs"
    assert not target.exists(), "refusing to overwrite generated test code"
    target.write_text(source,encoding="utf-8")
    print("PUB-T-984 parent code + original 47-SHA selector pinned; one fixed second ASCII per source catalog Story")

if __name__=="__main__":
    main()
