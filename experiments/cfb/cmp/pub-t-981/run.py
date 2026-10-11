#!/usr/bin/env python3
"""PUB-T-981: SHA-pinned, source-safe research census; not a product parser."""
import hashlib, io, json, struct, sys, urllib.request
from collections import Counter,defaultdict
from pathlib import Path
import olefile

REV="ae62bb5116b9aee19ebd5834e3a82066132c9f7f"
BASE="https://raw.githubusercontent.com/apache/poi/"+REV+"/test-data/"
INPUT=[
("DOC","document/WithArtShapes.doc",53760,"27793c37a4605ddb4f206acf2134b088f8f5f4b7"),
("DOC","document/pictures_escher.doc",120320,"4870bc7ab2d4311d9d102557c84eaad1802eca30"),
("DOC","document/FloatingPictures.doc",335360,"15b06cf3f079bb8d59ae3141b2371c527af73fd3"),
("XLS","spreadsheet/SheetWithDrawing.xls",17408,"e1395291b01b08e0100c1616c868bc30af681d7f"),
("XLS","spreadsheet/DrawingAndComments.xls",43520,"8be6c9e5269041068944e7938873b19c0198d2ac"),
("XLS","spreadsheet/SimpleWithImages.xls",48128,"1567fd1ffcd97d390d65a0c02a06f0bd146d0ace"),
("PPT","slideshow/text_shapes.ppt",11264,"c36183ac35f11b33518d2f1ebc0b5bca15ab7b54"),
("PPT","slideshow/pictures.ppt",75776,"9f6ce6dea18f1c2e0b1fdf7fda9e8edf1bb4e46d"),
("PPT","slideshow/PictureTypeZero.ppt",100864,"66b4e50c0011578c937f1a5e094a5ab4b1d4b212"),
("PUB","publisher/Simple.pub",65536,"2397b9d01cfa159de2f73cf5c990d9698eb69567"),
("PUB","publisher/SampleNewsletter.pub",291840,"94900925af5832c493784f3cb51563f838a64df8"),
("PUB","publisher/Sample3_2010.pub",72704,"d2982c06bbb6e228951781f23d56ea5928893d2b")]
assert len(INPUT)==12 and sum(t[2] for t in INPUT)<1500000
def h(d,o,e):
 if o+8>e:raise ValueError("header bounds")
 vi,t,n=struct.unpack_from("<HHI",d,o)
 if not 0xf000<=t<=0xf1ff or n>e-o-8 or n>4000000:raise ValueError("record bounds")
 return {"offset":o,"type":"0x%04X"%t,"ver":vi&15,"instance":vi>>4,"length":n+8,"payload_len":n}
def walk(d,o,end,fmt,depth=0):
 if depth>22:raise ValueError("nesting")
 r=h(d,o,end); stop=o+r["length"]; out=[r]
 if r["ver"]==15:
  p=o+8; previous=None
  while p<stop:
   try: kids,q=walk(d,p,stop,fmt,depth+1)
   except ValueError:
    if fmt!="PUB" or previous not in ("0xF000","0xF002") or p+12>stop:raise
    kids,q=walk(d,p+4,stop,fmt,depth+1)
   if q<=p:raise ValueError("progress")
   out.extend(kids);p=q;previous=kids[0]["type"]
   if len(out)>25000:raise ValueError("count cap")
  if p!=stop:raise ValueError("container remainder")
 return out,stop
def scan(d,fmt,scope):
 out=[];roots=[];tests=[];p=0
 while p+8<=len(d):
  if struct.unpack_from("<H",d,p+2)[0] not in (0xf000,0xf002) or d[p]&15!=15:
   p+=1;continue
  try: rec,end=walk(d,p,len(d),fmt)
  except ValueError:p+=1;continue
  if len(rec)<3 or not any(x["type"] in ("0xF006","0xF008","0xF00A","0xF00B","0xF121","0xF122") for x in rec):
   p+=1;continue
  roots.append({"scope":scope,"offset":p,"length":end-p,"kind":rec[0]["type"]})
  corrupt=bytearray(d);struct.pack_into("<I",corrupt,p+4,len(d)-p+1)
  try:walk(corrupt,p,len(corrupt),fmt);tests.append(False)
  except ValueError:tests.append(True)
  for x in rec:
   z=dict(x);o=z["offset"];z["scope"]=scope
   z["sha256_record"]=hashlib.sha256(d[o:o+z["length"]]).hexdigest()
   if z["type"] in ("0xF00B","0xF121","0xF122"):
    c=z["instance"];start=o+8;avail=z["payload_len"]
    valid=c<=4000 and c*6<=avail;entries=[];complex_len=0
    if valid:
     for i in range(c):
      op,v=struct.unpack_from("<HI",d,start+i*6)
      entries.append({"id":op&0x3fff,"fComplex":bool(op&0x8000),"fBid":bool(op&0x4000)})
      if op&0x8000:complex_len+=v
     valid=complex_len<=avail-c*6
    z["fopt"]={"valid":valid,"entries":entries if valid else [],"complex_bytes":complex_len}
   if z["type"]=="0xF006":
    n=struct.unpack_from("<I",d,o+12)[0] if z["payload_len"]>=16 else 0
    z["fdgg"]={"cidcl":n,"length_valid":n>0 and z["payload_len"]==16+8*(n-1)}
   if z["type"]=="0xF008":z["fdg"]={"length_valid":z["payload_len"]==8}
   if z["type"]=="0xF010":z["anchor_bytes"]=z["payload_len"]
   out.append(z)
  p=end
 return roots,out,tests
def biff(data):
 p=0;records=[];draw=[]
 while p+4<=len(data):
  t,n=struct.unpack_from("<HH",data,p)
  if n>len(data)-p-4:break
  records.append((t,p,n));p+=4+n
  if len(records)>100000:break
 for i,(t,o,n) in enumerate(records):
  if t not in (0xeb,0xec):continue
  fragments=[data[o+4:o+4+n]];j=i+1
  while j<len(records) and records[j][0]==0x3c:
   _,q,size=records[j];fragments.append(data[q+4:q+4+size]);j+=1
  draw.append((o,t,b"".join(fragments),len(fragments)))
 return draw
def load(path,n,blobsha):
 url=BASE+path
 with urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":"SK1-PUB-T-981"}),timeout=25) as r:
  if r.status!=200 or r.geturl()!=url:raise ValueError("source redirect")
  data=r.read(500001)
 if len(data)!=n or hashlib.sha1(b"blob "+str(n).encode()+b"\0"+data).hexdigest()!=blobsha:
  raise ValueError("source drift")
 if data[:8]!=bytes.fromhex("d0cf11e0a1b11ae1"):raise ValueError("non CFB")
 return data
def main(out):
 sources=[];allrecords=[]
 for fmt,path,n,blobsha in INPUT:
  row={"format":fmt,"source":path,"git_blob_sha1":blobsha,"source_bytes":n,"status":"NOT_EVALUATED"}
  try:
   data=load(path,n,blobsha);row["source_sha256"]=hashlib.sha256(data).hexdigest()
   ole=olefile.OleFileIO(io.BytesIO(data));streams=ole.listdir(streams=True,storages=False)
   if len(streams)>120:raise ValueError("too many streams")
   roots=[];records=[];controls=[];scopes=[]
   for parts in streams:
    name="/".join(parts);low=name.lower()
    allow=(fmt=="PUB" and low.endswith("escherstm") or fmt=="DOC" and low in ("worddocument","0table","1table","data") or fmt=="PPT" and low in ("powerpoint document","pictures") or fmt=="XLS" and low in ("workbook","book"))
    if not allow:continue
    if ole.get_size(parts)>4000000:raise ValueError("stream size")
    payload=ole.openstream(parts).read()
    pieces=[(name,payload)]
    if fmt=="XLS":pieces=[(name+"/BIFF_%04X@%d_frag%d"%(t,o,f),v) for o,t,v,f in biff(payload)]
    for scope,block in pieces:
     r,found,checks=scan(block,fmt,scope)
     roots.extend(r);records.extend(found);controls.extend(checks)
     scopes.append({"scope":scope,"bytes":len(block),"roots":len(r)})
   ole.close()
   ids=Counter(k["id"] for r in records for k in r.get("fopt",{}).get("entries",[]))
   row.update(status="SHA_VERIFIED_AND_SCANNED",roots=roots,controls=controls,scopes=scopes,records_total=len(records),record_types=dict(Counter(r["type"] for r in records)),fopt_ids=dict(ids),anchor_lengths=dict(Counter(str(r["anchor_bytes"]) for r in records if "anchor_bytes" in r)))
   for record in records:record.update(format=fmt,source=path)
   allrecords.extend(records)
  except Exception as e:row["reason"]=type(e).__name__
  sources.append(row);print(fmt,path,row["status"],len(row.get("roots",[])))
 byfmt=defaultdict(set);byids=defaultdict(set);byhash=defaultdict(set)
 for row in sources:
  byfmt[row["format"]].update(row.get("record_types",{}))
  byids[row["format"]].update(row.get("fopt_ids",{}))
 for r in allrecords:byhash[r["sha256_record"]].add(r["format"])
 labels=("DOC","XLS","PPT","PUB")
 pair=[{"left":a,"right":b,"shared_types":sorted(byfmt[a]&byfmt[b]),"shared_fopt_ids":sorted(byids[a]&byids[b],key=int)} for i,a in enumerate(labels) for b in labels[i+1:]]
 result={"schema":"sk1.cfb.cmp.pub-t-981.v1","apache_poi_commit":REV,"sources":sources,"source_count":len(sources),"sha_verified_count":sum(x["status"]=="SHA_VERIFIED_AND_SCANNED" for x in sources),"pairwise":pair,"exact_record_cross_format":[{"sha256_record":h,"formats":sorted(fmts)} for h,fmts in byhash.items() if len(fmts)>=2],"limitations":"DOC/PPT/PUB stream-carved grammar-validated root; XLS BIFF EB/EC plus contiguous Continue; no Microsoft Publisher native acceptance"}
 out.mkdir(parents=True,exist_ok=True)
 (out/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
 (out/"records.json").write_text(json.dumps({"schema":"sk1.cfb.cmp.pub-t-981.records.v1","records":allrecords},indent=2,sort_keys=True)+"\n")
 print("record metadata",len(allrecords))
if __name__=="__main__":main(Path(sys.argv[1]))
