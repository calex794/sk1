#!/usr/bin/env python3
"""Read-only source-free regression: historical real Reader vs current secure
Reader and unchanged LibreOffice, all on the same publicly registered PDF grids.

IMPORTANT: historical-vs-current difference is not a one-variable experiment.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from pathlib import Path
import hashlib
import json
import subprocess
import sys

EXPECTED={
 "old":{"commit":"30a7bf813cb47198b2a70821564846ca49d640e1",
        "sha":"142d29a71c1936d322431200832010fffe97e5859729ab66c6c6ca909b628e45",
        "run":37935975286,"art":11618761670,"zip":"d286d77845f0d5b7ca2eb0ada3276a033e125747199804c42d93808dbe582f92"},
 "new":{"commit":"a654d1af59be6173cd31ba3b7be37b1155a28ba5",
        "sha":"4148af40d4b21f05ec3dcbbc5257e8aaff1f1730ea65e74dffc20c76cc891b6d",
        "run":38143407856,"art":11704131725,"zip":"a6c1d4faa1b3aee07c48de9592e770ded1072ec07a52e0247cc94e039a578fab"},
 "lo":{"sha":"2f3f1bcddaa6aa094b46893825593d9aef4789b6960620dfdaf8d01a6af5b5fd",
       "run":38145210671,"art":11704247616,"zip":"228d9833e65d491a865754a132e358b317dda64c2432c21ac1d7cca2a4fc261c"}
}
SECURITY="ea5689c6a1fff065297fa3ff3e84a153ed81ecfe"
PARENT="22a322ed10d9fe8a4ade45acf83bebd0442b691b"
SOURCE="apps/chaptera-server/src/reader_scene_v1.rs"
CONTROL_DIF=0.015

def sha(b):return hashlib.sha256(b).hexdigest()
def git(root,*args):
    return subprocess.run(["git",*args],cwd=root,capture_output=True,text=True,check=True,timeout=30).stdout.strip()

def load(path,which):
    content=Path(path).read_bytes()
    if sha(content)!=EXPECTED[which]["sha"]:
        raise ValueError(which+": SOURCE_FREE_ARTIFACT_SHA_DRIFT")
    return json.loads(content)

def image_policy(root):
    if git(root,"rev-parse","HEAD")!=SECURITY or git(root,"rev-parse","HEAD^")!=PARENT:
        raise ValueError("SECURITY_COMMIT_LINEAGE_DRIFT")
    touched=git(root,"diff","--name-only","HEAD^","HEAD").splitlines()
    if touched!=[SOURCE]:raise ValueError("NON_SINGLE_FILE_SECURITY_DIFF")
    old=git(root,"show","HEAD^:"+SOURCE)
    new=(root/SOURCE).read_text()
    guard="let browser_inline_safe = !image.source_exact;"
    before="let mut image_by_resource = HashMap::<String, (&str, &[u8])>::new();"
    if guard in old or guard not in new or before not in old:
        raise ValueError("SECURITY_RULE_MISSING")
    if "source_exact_browser_denied" not in new:
        raise ValueError("SECURITY_REASON_MISSING")
    if "MAX_INLINE_JPEG_RESOURCE_BYTES: usize = 5 * 1024 * 1024;" not in old:
        raise ValueError("JPEG_OLD_LIMIT_NOT_PRESENT")
    if "MAX_INLINE_JPEG_RESOURCE_BYTES: usize = 5 * 1024 * 1024;" not in new:
        raise ValueError("JPEG_LIMIT_WAS_ALTERED")
    return {
     "exact_one_file_diff":True,
     "parent":PARENT,"policy_commit":SECURITY,"modified_file":SOURCE,
     "policy_denies_source_exact_before_mime_size_check":True,
     "jpeg_five_mib_limit_unchanged":True,
     "security_reason":"source_exact_browser_denied",
     "raw_browser_image_reenable_allowed":False,
     "old_git_blob":git(root,"rev-parse","HEAD^:"+SOURCE),
     "new_git_blob":git(root,"rev-parse","HEAD:"+SOURCE)
    }

def fixtures(r):
    if (r["schema"]!="chaptera.publisher-visual-fingerprint-compare.v1"
        or r["pair_count"]!=55 or r["compared_page_count"]!=162
        or len(r["pages"])!=162 or len(r["pairs"])!=55):
        raise ValueError("UNSUPPORTED_READER_RECEIPT")
    pairs={p["fixture"]:p for p in r["pairs"]}
    pages={(p["fixture"],p["page"]):p for p in r["pages"]}
    if len(pairs)!=55 or len(pages)!=162:raise ValueError("DUPLICATE_READER_PAGES")
    return pairs,pages

def compare(old,new,lo,policy):
    if old["repository_commit_sha"]!=EXPECTED["old"]["commit"]:
        raise ValueError("HISTORICAL_SOURCE_COMMIT_DRIFT")
    if new["repository_commit_sha"]!=EXPECTED["new"]["commit"]:
        raise ValueError("CURRENT_SOURCE_COMMIT_DRIFT")
    oldpairs,oldpages=fixtures(old)
    newpairs,newpages=fixtures(new)
    if set(oldpairs)!=set(newpairs) or set(oldpages)!=set(newpages):
        raise ValueError("DIFFERENT_READER_DENOMINATORS")
    for fixture in oldpairs:
        x,y=oldpairs[fixture],newpairs[fixture]
        if (x["source_sha256"],x["reference_pages"],x["candidate_page_identity_order_sha256"])!=(
            y["source_sha256"],y["reference_pages"],y["candidate_page_identity_order_sha256"]):
            raise ValueError("SOURCE_OR_PAGE_ORDER_IDENTITY_DRIFT")
    if old["comparator"]!=new["comparator"]:
        raise ValueError("READER_COMPARATOR_DRIFT")
    bins=Counter()
    rows=[]
    for key in sorted(oldpages):
        a,b=oldpages[key],newpages[key]
        for idkey in ("candidate_page_identity_sha256","reference_state","reference_surface_stage","reference_media_extent_delta"):
            if a[idkey]!=b[idkey]:raise ValueError("REFERENCE_OR_GEOMETRY_DRIFT")
        d=b["changed_cell_count"]-a["changed_cell_count"]
        bins["worse" if d>0 else "better" if d<0 else "unchanged"]+=1
        rows.append({"fixture":key[0],"page":key[1],
                     "before":a["changed_cell_count"],"after":b["changed_cell_count"],
                     "delta":d,"same_identity":True})
    if len(rows)!=162 or bins!=Counter(worse=90,better=1,unchanged=71):
        raise ValueError("UNEXPECTED_HISTORICAL_DRIFT_CLASS")
    if sum(r["delta"] for r in rows)!=47869:raise ValueError("UNEXPECTED_PIXEL_DELTA")
    doc_before=Counter();doc_after=Counter()
    pages_before=Counter();pages_after=Counter()
    original=[]
    if lo["schema"]!="sk1.pub-t999.visual-ordinal.v1" or lo["task_id"]!="PUB-T-999":
        raise ValueError("LO_RECEIPT_SCHEMA_DRIFT")
    if lo["rar2_commit"]!=EXPECTED["new"]["commit"]:
        raise ValueError("LO_READER_SHA_DRIFT")
    native_ref=lo["publisher_reference_blob"]
    if native_ref!="1e87b52d268f87dcd4896f3d1af351a0b8cb9d96":
        raise ValueError("NATIVE_REF_DRIFT")
    for c in lo["cases"]:
        fixture=c["fixture"]
        if fixture not in oldpairs or oldpairs[fixture]["source_sha256"]!=c["pub_sha256"]:
            raise ValueError("LO_PUBLIC_PUB_SOURCE_ID_MISMATCH")
        doc_diffs_before=[];doc_diffs_after=[]
        for p in c["raster"]["pages"]:
            if p.get("status")!="COARSE_ORDINAL_MATCH":continue
            key=(fixture,p["ordinal_page"])
            before=oldpages[key]["changed_cell_fraction"]
            after=newpages[key]["changed_cell_fraction"]
            lscore=p["libreoffice_changed_fraction"]
            if after!=p["reader_changed_fraction"]:
                raise ValueError("LO_CURRENT_READER_MISMATCH")
            def winner(reader_diff):
                d=reader_diff-lscore
                return "LO" if d>CONTROL_DIF else "READER" if d< -CONTROL_DIF else "NEAR_TIE"
            bw=winner(before);aw=winner(after)
            pages_before[bw]+=1;pages_after[aw]+=1
            doc_diffs_before.append(before-lscore)
            doc_diffs_after.append(after-lscore)
            original.append({"fixture":fixture,"page":p["ordinal_page"],"native_pdf_sha256":c["reference_pdf_sha256"],
                             "historical_reader":before,"current_reader":after,"lo":lscore,
                             "historical_winner":bw,"current_winner":aw,
                             "changed_cell_delta_security_period":round((after-before)*4096)})
        if doc_diffs_before:
            def docwinner(x):
                d=sum(x)/len(x)
                return "LO" if d>CONTROL_DIF else "READER" if d< -CONTROL_DIF else "NEAR_TIE"
            doc_before[docwinner(doc_diffs_before)]+=1
            doc_after[docwinner(doc_diffs_after)]+=1
    if len(original)!=111 or len(lo["cases"])!=49:
        raise ValueError("WRONG_ORDINAL_DENOMINATOR")
    if (pages_before!=Counter(LO=48,READER=36,NEAR_TIE=27)
        or pages_after!=Counter(LO=85,READER=17,NEAR_TIE=9)):
        raise ValueError("WRONG_PAIR_CROSSOVER")
    if doc_before!=Counter(READER=20,LO=13,NEAR_TIE=6):
        raise ValueError("WRONG_HISTORICAL_DOCUMENT_RANKING")
    if doc_after!=Counter(LO=26,READER=8,NEAR_TIE=5):
        raise ValueError("WRONG_CURRENT_DOCUMENT_RANKING")
    original.sort(key=lambda x:x["changed_cell_delta_security_period"],reverse=True)
    summary={
       "registered_source_pub_count":55,"registered_publisher_raster_pages":162,
       "both_reader_page_identity_sha256_same":162,
       "reader_page_regressed_count":bins["worse"],
       "reader_page_improved_count":bins["better"],
       "reader_page_unchanged_count":bins["unchanged"],
       "added_changed_64x64_cells":sum(r["delta"] for r in rows),
       "historical_reader_full_mean":old["corpus_mean_changed_cell_fraction"],
       "current_secure_reader_full_mean":new["corpus_mean_changed_cell_fraction"],
       "lo_shared_pub_count":49,
       "lo_ranked_documents":39,"lo_ranked_ordinal_pages":111,
       "before_pages":dict(pages_before),"after_pages":dict(pages_after),
       "before_documents":dict(doc_before),"after_documents":dict(doc_after),
       "historical_reader_mean_shared":sum(x["historical_reader"] for x in original)/len(original),
       "current_reader_mean_shared":sum(x["current_reader"] for x in original)/len(original),
       "lo_mean_shared":sum(x["lo"] for x in original)/len(original),
       "historic_reader_current_reader_comparable_source":True,
       "historic_and_current_same_code_commit":False,
       "exact_one_change_controlled_browser_ab_executed":False,
       "all_page_regressions_attributed_only_to_security_rule":False
    }
    score={
      "schema":"sk1.pub-t1000.web-security-history.v1","task":"PUB-T-1000",
      "policy":policy,"input_artifacts":EXPECTED,
      "claim_boundaries":{
       "real_browser_before_and_after":True,
       "same_public_pub_and_publisher_reference":True,
       "source_free_no_pub_jpeg_pdf_png_uploaded":True,
       "security_guard_static_causal_for_source_exact_inline_admission":True,
       "other_intervening_main_commits_confound_all_page_pixel_causality":True,
       "historical_counterfactual_not_current_product_claim":True,
       "current_visual_85_17_9_is_real_user_facing_secure_reader":True,
       "publisher_surface_stage_known":False
      },
      "summary":summary,
      "largest_regressions":sorted(rows,key=lambda x:x["delta"],reverse=True)[:20],
      "largest_111_page_crossover":original[:20],
      "sample_022":{
        "sha256":"7079ad60fd8109796b84286d294cb490051a1517d8e52ac61e7c416dbd04428c",
        "historical_reader_changed_cells":oldpages[("022_7079ad60fd810979",1)]["changed_cell_count"],
        "current_reader_changed_cells":newpages[("022_7079ad60fd810979",1)]["changed_cell_count"],
        "lo_changed_cells":round(
          next(z["lo"] for z in original if z["fixture"].startswith("022_"))*4096),
        "jpeg_old_per_resource_limit":"5MiB",
        "security_policy_now_denies_source_exact_browsing":True
      }
    }
    if score["sample_022"]["historical_reader_changed_cells"]!=462:
        raise ValueError("SOURCE_022_HISTORICAL_DRIFT")
    if score["sample_022"]["current_reader_changed_cells"]!=3817:
        raise ValueError("SOURCE_022_CURRENT_DRIFT")
    if score["sample_022"]["lo_changed_cells"]!=540:
        raise ValueError("SOURCE_022_LO_DRIFT")
    return score

def main(argv):
    if len(argv)!=5:raise SystemExit("usage: audit.py PRE_POLICY_55_JSON CURRENT_55_JSON LO_49_JSON RAR2_SECURITY_COMMIT_CHECKOUT REPORT_JSON")
    old,new,lo,repo,out=argv
    old=load(old,"old");new=load(new,"new");lo=load(lo,"lo")
    policy=image_policy(Path(repo).resolve())
    obj=compare(old,new,lo,policy)
    path=Path(out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
    print("PUB-T-1000 PASS",json.dumps(obj["summary"],sort_keys=True))

if __name__=="__main__":main(sys.argv[1:])
