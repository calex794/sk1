// PUB-T-993: genuine natural-original 0x3F1 -> Writer-derived 0x3FF -> 0x401.
// No direct mutation of the SYID header. Each +1 arises exclusively from
// the unchanged upstream Writer in the inherited step() implementation.
const NATURAL_SOURCE_SHA:&str=
    "b4b005a7e6f662546cf07bdd155a1cf936293e6ceb6ac7f424456fee87051f1b";

fn header_value(input:&[u8])->Result<u32>{
    let quill=pub_cfb::read_stream_reader(
        Cursor::new(input),pub_reader::QUILL_STREAM_PATH)?;
    let catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&quill)?;
    Ok(catalog.syid.header.value)
}
fn header_byte_delta(a:u32,b:u32)->usize{
    a.to_le_bytes().iter().zip(b.to_le_bytes().iter())
        .filter(|(x,y)|x!=y).count()
}
fn full_raw_identity(a:&[u8],b:&[u8])->Value{
    physical_residue(a,b)
}
fn run_eight_cycles(source:&[u8],target_syid:u32,before:&str,inserted:&str)->Result<Value>{
    let mut current=source.to_vec();
    let mut cycles=Vec::<Value>::new();
    let mut steps=0usize;
    for cyc in 0..8_usize{
        let start=header_value(&current)?;
        let expected_start=1009_u32+2*cyc as u32;
        if start!=expected_start{
            cycles.push(json!({"cycle":cyc+1,"status":"START_COUNTER_DRIFT",
                               "observed_header":start,"expected_header":expected_start}));
            break;
        }
        let mut result=json!({
            "cycle":cyc+1,
            "status":"NOT_EVALUATED",
            "start_header":start,
            "after_insert_header":Value::Null,
            "after_delete_header":Value::Null,
            "insert":Value::Null,
            "delete":Value::Null,
            "expected_final_header":start.checked_add(2),
            "expected_changed_cycle_raw_bytes":start.checked_add(2).map(|end|
                header_byte_delta(start,end)),
            "cycle_raw":Value::Null,
            "cycle_cfb":Value::Null,
            "original_raw":Value::Null,
            "original_cfb":Value::Null,
            "matches_exact_raw_quill_model":Value::Null
        });
        let insert=step(&current,target_syid,before,inserted);
        result["insert"]=insert.receipt;
        let mid=match insert.bytes{
            Some(bytes)=>bytes,
            None=>{
                result["status"]=json!("INSERT_BLOCKED");
                cycles.push(result);break;
            }
        };
        steps+=1;
        let midheader=header_value(&mid)?;
        result["after_insert_header"]=json!(midheader);
        if start.checked_add(1)!=Some(midheader){
            result["status"]=json!("INSERT_SYID_COUNTER_DRIFT");
            cycles.push(result);break;
        }
        let deletion=step(&mid,target_syid,inserted,before);
        result["delete"]=deletion.receipt;
        let after=match deletion.bytes{
            Some(bytes)=>bytes,
            None=>{
                result["status"]=json!("DELETE_BLOCKED");
                cycles.push(result);break;
            }
        };
        steps+=1;
        let end=header_value(&after)?;
        result["after_delete_header"]=json!(end);
        let cycle_raw=full_raw_identity(&current,&after);
        let original_raw=full_raw_identity(source,&after);
        result["cycle_raw"]=cycle_raw.clone();
        result["original_raw"]=original_raw.clone();
        let cycle_cfb=match inspect_reverted_cfb(&current,&after){
            Ok(d)=>d,
            Err(_)=>{
                result["status"]=json!("CYCLE_CFB_DIFF_BLOCKED");
                cycles.push(result);break;
            }
        };
        let original_cfb=match inspect_reverted_cfb(source,&after){
            Ok(d)=>d,
            Err(_)=>{
                result["cycle_cfb"]=cycle_cfb;
                result["status"]=json!("ORIGINAL_CFB_DIFF_BLOCKED");
                cycles.push(result);break;
            }
        };
        let expected_end=start.checked_add(2);
        let expected_raw=expected_end.map(|value|header_byte_delta(start,value));
        let expected_original=header_byte_delta(1009_u32,end);
        let match_result=expected_end==Some(end)
            && cycle_raw["equal_length"]==true
            && cycle_raw["extra_bytes"]==0
            && cycle_raw["changed_same_offset_bytes"]==json!(expected_raw)
            && original_raw["equal_length"]==true
            && original_raw["extra_bytes"]==0
            && original_raw["changed_same_offset_bytes"]==json!(expected_original)
            && cycle_cfb["source_syid_first_dword"]==json!(start)
            && cycle_cfb["final_syid_first_dword"]==json!(end)
            && cycle_cfb["syid_first_dword_delta"]==2
            && cycle_cfb["syid_first_dword_changed_bytes"]==json!(expected_raw)
            && cycle_cfb["quill_changed_bytes_outside_syid_first_dword"]==0
            && cycle_cfb["same_quill_TEXT_payload_bytes"]==true
            && cycle_cfb["same_quill_story_syid_sequence"]==true
            && cycle_cfb["non_quill_streams_changed"]==0
            && cycle_cfb["missing_cfb_paths"]==0
            && cycle_cfb["added_cfb_paths"]==0
            && cycle_cfb["cfb_entry_type_changes"]==0
            && cycle_cfb["matched_descriptor_sequence"]==true
            && original_cfb["source_syid_first_dword"]==1009
            && original_cfb["final_syid_first_dword"]==json!(end)
            && original_cfb["syid_first_dword_delta"]==i64::from(end)-1009
            && original_cfb["quill_changed_bytes_outside_syid_first_dword"]==0
            && original_cfb["same_quill_TEXT_payload_bytes"]==true
            && original_cfb["same_quill_story_syid_sequence"]==true
            && original_cfb["non_quill_streams_changed"]==0
            && original_cfb["matched_descriptor_sequence"]==true;
        result["cycle_cfb"]=cycle_cfb;
        result["original_cfb"]=original_cfb;
        result["matches_exact_raw_quill_model"]=json!(match_result);
        result["status"]=json!(if match_result{"PASS"}else{"RAW_MODEL_COUNTEREXAMPLE"});
        cycles.push(result);
        if !match_result{break;}
        current=after;
    }
    Ok(json!({
        "completed_cycles":cycles.iter().filter(|c|c["status"]=="PASS").count(),
        "completed_writer_materializations":steps,
        "cycles":cycles,
        "reached_writer_generated_03ff":cycles.iter().any(|c|
            c["status"]=="PASS" && c["after_delete_header"]==1023),
        "reached_writer_generated_0401":header_value(&current)?==1025,
        "source_original_unchanged":sha256(source).to_string()==NATURAL_SOURCE_SHA
    }))
}
fn inspect_source(source:&[u8],expected:&str)->Result<Value>{
    ensure!(expected==NATURAL_SOURCE_SHA,"natural SHA not preregistered");
    ensure!(sha256(source).to_string()==expected,"input original SHA mismatch");
    ensure!(source.len()==471552,"source original size mismatch");
    let source_hash=sha256(source);
    let quill=pub_cfb::read_stream_reader(
        Cursor::new(source),pub_reader::QUILL_STREAM_PATH)?;
    let catalog=pub_quill::parse_confirmed_story_catalog(
        pub_core::StreamPath(pub_reader::QUILL_STREAM_PATH.into()),&quill)?;
    ensure!(catalog.syid.header.value==1009,"natural SYID no longer 0x3F1");
    ensure!(catalog.syid.count.value==65,"natural live SYID count changed");
    ensure!(catalog.syid.ids.iter().map(|s|s.value.0).max()==Some(965),
        "natural max live SYID changed");
    let mut result=json!({
        "schema":"sk1.cfb-exp-pub-t-993.source.v1",
        "source_sha256":expected,
        "source_bytes":source.len(),
        "original_natural_syid":1009,
        "source_syid_count":65,
        "source_syid_max_live":965,
        "source_intact":true,
        "candidate_stories":[],
        "status":"NOT_EVALUATED",
        "publisher_native_acceptance":"NOT_EVALUATED",
        "original_publisher_fe_ff_witness":false,
        "manual_syid_rewrite":false
    });
    let editor=match open_mature_0x2c_editor(source,source_hash){
        Ok(x)=>x,
        Err(_)=>{
            result["status"]=json!("SOURCE_EDITOR_OPEN_BLOCKED");
            return Ok(result);
        }
    };
    let selected=catalog.stories.iter().filter_map(|s|{
        let id=pub_reader::derive_pub_story_id(&source_hash,s.syid.0).ok()?;
        let value=editor.graph().stories.get(&id)?;
        if editor.can_replace_story_text(id).is_ok() &&
            value.text.chars().filter(|c|c.is_ascii_alphanumeric()).count()>=2{
            Some((s.syid.0,value.text.clone()))
        }else{None}
    }).take(3).collect::<Vec<_>>();
    if selected.is_empty(){
        result["status"]=json!("NO_ELIGIBLE_STORIES");
        return Ok(result);
    }
    let mut trials=Vec::<Value>::new();
    for (ordinal,(syid,before)) in selected.into_iter().enumerate(){
        let positions=before.char_indices().filter(|(_,c)|c.is_ascii_alphanumeric())
            .collect::<Vec<_>>();
        ensure!(positions.len()>=2,"selected Story without second ASCII");
        let (at,ch)=positions[1];
        let prev=before[..at].chars().last();
        let marker=['X','Q','Z'].into_iter().find(|c|Some(*c)!=prev && *c!=ch)
            .context("no safe marker")?;
        let mut inserted=before.clone();
        inserted.insert(at,marker);
        let sequence=run_eight_cycles(source,syid,&before,&inserted)?;
        trials.push(json!({
            "story_ordinal":ordinal,
            "story_utf16_length":before.encode_utf16().count(),
            "ascii_alphanumeric_count":positions.len(),
            "offset_utf16":before[..at].encode_utf16().count(),
            "sequence":sequence
        }));
    }
    result["candidate_stories"]=json!(trials);
    result["status"]=json!("EVALUATED");
    ensure!(sha256(source).to_string()==expected,"original source changed in memory");
    Ok(result)
}
fn main()->Result<()>{
    let mut a=env::args().skip(1);
    let path=a.next().context("source input")?;
    let expected=a.next().context("sha")?;
    let output=a.next().context("safe output receipt")?;
    ensure!(a.next().is_none(),"unexpected arguments");
    let data=fs::read(path)?;
    let result=inspect_source(&data,&expected)?;
    let mut f=fs::OpenOptions::new().write(true).create_new(true).open(output)?;
    f.write_all(&serde_json::to_vec_pretty(&result)?)?;
    f.write_all(b"\n")?;
    f.sync_all()?;
    println!("{}",serde_json::to_string(&json!({
        "source_sha256":expected,"status":result["status"],
        "eligible_story_trials":result["candidate_stories"].as_array().map(|a|a.len()).unwrap_or(0)
    }))?);
    Ok(())
}
