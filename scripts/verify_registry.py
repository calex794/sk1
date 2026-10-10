#!/usr/bin/env python3
"""SK1 local metadata gate. NOT an authorization service for Notion leases.

Validates unique task-scoped identities and refuses unregistered code.
No network calls, GitHub token, or Notion credentials.
"""
from __future__ import annotations
import json
from pathlib import Path, PurePosixPath
import re
import sys

SCHEMA="sk1.experiment-registry.v1"
LEGACY={f"SK1-EXP-{i:03d}" for i in range(1,6)}
TASK_KEY=re.compile(r"^SK1-([A-Z][A-Z0-9]*)-(EXP|VAL|DIAG|CMP|BENCH)-(PUB-T-[1-9][0-9]*)$")
NOTION_URL=re.compile(r"^https://app[.]notion[.]com/p/[a-f0-9]{32}$")
AREA={"CFB","QUILL","VERSIONS"}
TYPES={"EXP","VAL","DIAG","CMP","BENCH"}
REQUIRED={"key","kind","area","type","task_id","state",
          "task_notion","evidence_notion","code_path","git_ref"}
EXPERIMENT_MARKERS={"run.py","main.py","__main__.py"}


def path_is_safe(value:object)->bool:
    if not isinstance(value,str) or not value or "\\" in value:
        return False
    p=PurePosixPath(value)
    return (not p.is_absolute() and all(x not in ("..",".") for x in value.split("/"))
            and len(p.parts)>=2 and p.parts[0]=="experiments"
            and p.as_posix()==value)


def verify(root:Path)->list[str]:
    errors=[]
    root=Path(root)
    path=root/"experiments/registry.json"
    try:
        document=json.loads(path.read_text(encoding="utf-8"))
    except (OSError,ValueError) as e:
        return [f"cannot parse experiments/registry.json: {type(e).__name__}"]
    if set(document)!={"schema","authority","records"} or document.get("schema")!=SCHEMA:
        errors.append("registry root schema mismatch")
    records=document.get("records")
    if not isinstance(records,list):
        return errors+["registry.records must be a list"]
    seen_keys=set()
    seen_tasks=set()
    seen_task_links=set()
    seen_paths=set()
    recorded_main=set()
    listed_legacy=set()
    for i,r in enumerate(records):
        label=f"records[{i}]"
        if not isinstance(r,dict) or set(r)!=REQUIRED:
            errors.append(f"{label}: fields mismatch")
            continue
        key=r["key"]
        if not isinstance(key,str):
            errors.append(f"{label}: key not string")
            continue
        if key in seen_keys:
            errors.append(f"{label}: duplicate experiment key {key}")
        seen_keys.add(key)
        area,typ,kind,state=r["area"],r["type"],r["kind"],r["state"]
        code,ref=r["code_path"],r["git_ref"]
        if area not in AREA or typ not in TYPES:
            errors.append(f"{label}: unknown task classification")
        if kind not in ("legacy","task") or state not in ("parked","claimed","running","completed"):
            errors.append(f"{label}: invalid kind or state")
        if not path_is_safe(code):
            errors.append(f"{label}: unsafe or noncanonical code_path")
        elif code in seen_paths:
            errors.append(f"{label}: duplicate code_path {code}")
        seen_paths.add(code if isinstance(code,str) else label)
        for field in ("task_notion","evidence_notion"):
            val=r[field]
            if val is not None and (not isinstance(val,str) or not NOTION_URL.fullmatch(val)):
                errors.append(f"{label}: {field} must be a valid Notion page URL")
        if state=="completed" and r["evidence_notion"] is None:
            errors.append(f"{label}: completed task lacks verified Notion evidence")
        if kind=="legacy":
            listed_legacy.add(key)
            if key not in LEGACY:
                errors.append(f"{label}: new legacy numbered ID forbidden: {key}")
            if (r["task_id"] is not None or r["task_notion"] is not None
                or state!="completed" or ref!="main"
                or (isinstance(code,str) and code!=f"experiments/{key.lower()}")):
                errors.append(f"{label}: legacy identity/path/status changed")
        elif kind=="task":
            task=r["task_id"]
            match=TASK_KEY.fullmatch(key)
            if (not isinstance(task,str) or not match or
                (area,typ,task)!=match.groups()):
                errors.append(f"{label}: ID must equal SK1-AREA-TYPE-NotionTaskID")
            if task in seen_tasks:
                errors.append(f"{label}: duplicate canonical Notion Task ID {task}")
            seen_tasks.add(task)
            if r["task_notion"] is None:
                errors.append(f"{label}: task row URL missing")
            elif r["task_notion"] in seen_task_links:
                errors.append(f"{label}: duplicate Notion task URL")
            seen_task_links.add(r["task_notion"])
            if isinstance(code,str) and isinstance(task,str):
                expected=f"experiments/{str(area).lower()}/{str(typ).lower()}/{task.lower()}"
                if code!=expected:
                    errors.append(f"{label}: task ID and folder mismatch")
            if state=="parked":
                if ref is not None:
                    errors.append(f"{label}: parked task must have no git_ref")
            elif not isinstance(ref,str) or not re.fullmatch(r"sk1/[a-z0-9-]+",ref):
                errors.append(f"{label}: active/done task must use explicit task branch")
        if isinstance(code,str) and path_is_safe(code):
            folder=root/code
            if state=="parked" and folder.exists():
                errors.append(f"{label}: parked task contains executable folder")
            if ref=="main":
                recorded_main.add(code)
                if not (folder.is_dir() and (folder/"README.md").is_file()):
                    errors.append(f"{label}: on-main experiment missing README")
    if listed_legacy!=LEGACY:
        errors.append("missing or extra legacy IDs: expected exactly SK1-EXP-001..005")
    # Independently inspect the checked-out tree for unregistered executable
    # workspaces. A remote task branch is not required to exist on main.
    experiments=root/"experiments"
    for f in experiments.rglob("*"):
        if not f.is_file():
            continue
        if f.name not in EXPERIMENT_MARKERS and f.suffix!=".rs":
            continue
        folder=f.parent
        rel=folder.relative_to(root).as_posix()
        owners=[code for code in seen_paths if isinstance(code,str)
                and (rel==code or rel.startswith(code+"/"))]
        if len(owners)!=1:
            errors.append(f"unregistered or ambiguous experiment executable: {f.relative_to(root).as_posix()}")
        elif owners[0] not in recorded_main:
            # Files on a separate task branch are valid only if the registry
            # mentions the exact non-main git ref; parked remains prohibited.
            found=[r for r in records if isinstance(r,dict)
                   and r.get("code_path")==owners[0]]
            if not found or found[0]["state"]=="parked":
                errors.append(f"unclaimed experiment code: {f.relative_to(root).as_posix()}")
    return errors


if __name__=="__main__":
    errs=verify(Path(__file__).resolve().parents[1])
    if errs:
        for e in errs:
            print("REGISTRY FAIL:",e,file=sys.stderr)
        sys.exit(1)
    print("SK1 registry PASS: canonical Task IDs unique, legacy preserved, executable workspaces registered")
