#!/usr/bin/env python3
"""T979: controlled read-only-origin Quill redundant-byte rescue probe."""
import hashlib, json, urllib.request
from pathlib import Path

REF="ae62bb5116b9aee19ebd5834e3a82066132c9f7f"
CASES={
 "Sample3.pub":{"blob":"4f19bec93d25f3d80501490dd108abef4f09b6cb","n":14,"gap":2034,"a":5028,"b":5106},
 "Sample4.pub":{"blob":"445df85f092970c36d4b3003d375331a707d6b3c","n":26,"gap":2022,"a":5016,"b":5094}
}
def u16(b,p):return int.from_bytes(b[p:p+2],"little")
def u32(b,p):return int.from_bytes(b[p:p+4],"little")
def get_stream(file):
 sector=1<<u16(file,30);fat=[]
 for i in range(u32(file,44)):
  sid=u32(file,76+4*i)
  for j in range(sector//4):fat.append(u32(file,(sid+1)*sector+4*j))
 def chain(start):
  out=[];seen=set()
  while start not in (0xfffffffe,0xffffffff):
   if start in seen or start>=len(fat) or len(out)>10000:raise ValueError("bad FAT")
   seen.add(start);out.append(start);start=fat[start]
  return out
 def read(start,length):
  nodes=chain(start)
  return b"".join(file[(sid+1)*sector:(sid+2)*sector] for sid in nodes)[:length],nodes
 directory,_=read(u32(file,48),2**30)
 D=[]
 for i in range(len(directory)//128):
  p=128*i
  if not directory[p+66]:D.append(None);continue
  name=directory[p:p+u16(directory,p+64)-2].decode("utf-16le")
  D.append((name,u32(directory,p+68),u32(directory,p+72),u32(directory,p+76),u32(directory,p+116),u32(directory,p+120)))
 found=[]
 def walk(i,path):
  if i==0xffffffff:return
  name,l,r,ch,st,n=D[i];walk(l,path)
  full=path+"/"+name
  if full=="/Quill/QuillSub/CONTENTS":found.append((st,n))
  if ch!=0xffffffff:walk(ch,full)
  walk(r,path)
 walk(D[0][3],"")
 assert len(found)==1
 q,ids=read(*found[0])
 def phys(off):return (ids[off//sector]+1)*sector+off%sector
 return q,phys

def run(name,case):
 url=f"https://raw.githubusercontent.com/apache/poi/{REF}/test-data/publisher/{name}"
 with urllib.request.urlopen(url,timeout=25) as r:file=bytes(r.read())
 # git blob identity, not file sha256
 blobhash=hashlib.sha1(b"blob "+str(len(file)).encode()+b"\0"+file).hexdigest()
 assert blobhash==case["blob"],(name,blobhash)
 q,phys=get_stream(file)
 n=case["n"];gap=case["gap"];a=case["a"];b=case["b"]
 assert q[gap:gap+n]==q[a:a+n]==q[b:b+n]
 assert len(set((gap,a,b)))==3
 # Perturb one byte in first TOKN occurrence; recovery uses ONLY two unchanged candidates.
 idx=n//2
 original=file
 bad=bytearray(file);bad[phys(a+idx)]^=0x5a
 def recover_from_consensus(candidate):
  stream,_=get_stream(candidate)
  ga=stream[gap:gap+n];bo=stream[b:b+n]
  if ga!=bo:return None,"candidate_conflict"
  if stream[a:a+n]==ga:return None,"not_damaged"
  restored=bytearray(candidate)
  for i,value in enumerate(ga):restored[phys(a+i)]=value
  return bytes(restored),"restored_candidate"
 recovered,status=recover_from_consensus(bytes(bad))
 assert status=="restored_candidate" and recovered==original
 # Two candidate corruptions must reject; simultaneous target+gap+other TOKN.
 multi=bytearray(bad);multi[phys(gap+idx)]^=0x33;multi[phys(b+idx)]^=0x7b
 out,reason=recover_from_consensus(bytes(multi));assert out is None and reason=="candidate_conflict"
 # Protected clean source must never be modified.
 clean,clean_reason=recover_from_consensus(original);assert clean is None and clean_reason=="not_damaged"
 # Malicious false-consensus negative: two colluding copies changed to the same byte.
 collude=bytearray(bad);v=q[gap+idx]^0x23
 collude[phys(gap+idx)]=v;collude[phys(b+idx)]=v
 suspicious,recovered_reason=recover_from_consensus(bytes(collude))
 # Detector cannot establish authority without an independently authenticated candidate.
 if suspicious is not None:assert suspicious!=original
 return {"file":name,"source_sha256":hashlib.sha256(original).hexdigest(),"quill_length":len(q),"logical_gap":gap,"source_tokn_matches":[a,b],"length":n,"probe_index":idx,"single_byte_recovery":{"status":status,"whole_pub_sha256_equal":hashlib.sha256(recovered).digest()==hashlib.sha256(original).digest()},"healthy_control":clean_reason,"conflicting_donors_control":reason,"colluding_donors_control":{"status":"inconclusive_undetectable_without_trust","algorithm_would_accept":suspicious is not None,"restores_original":suspicious==original}}
def main():
 result={"schema":"sk1/t979-controlled-self-donor-v1","authority":"synthetic_only","publisher_native":"not_run","cases":[run(k,v) for k,v in CASES.items()]}
 assert all(x["single_byte_recovery"]["whole_pub_sha256_equal"] for x in result["cases"])
 out=Path("results-t979");out.mkdir(exist_ok=True)
 (out/"report.json").write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
 print(json.dumps({"status":"PASS","cases":len(result["cases"]),"synthetic_restored":2,"native":"NOT_RUN","critical_negative":"colluding donors cannot be trusted"},sort_keys=True))
if __name__=="__main__":main()
