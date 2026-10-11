#!/usr/bin/env python3
"""Bounded public Publisher forum HTTP availability probe; emits metadata only."""
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser

UA = "SK1-PUB-Archive-Research/0.1 (public access diagnostic; no bulk crawl)"
LIMIT = 262144
SOURCES = [
    ("google_groups", "https://groups.google.com/g/microsoft.public.publisher/c/S_GVhKXClfo", ["Publisher", "file"]),
    ("office_forums", "https://www.office-forums.com/threads/publisher-cannot-open-the-file-error-1100009.445052/", ["Publisher", "1100009"]),
    ("office_forums_prepress", "https://www.office-forums.com/threads/trying-to-overprint-keyline-on-inserted-pictures.1606388/", ["Publisher", "overprint"]),
    ("microsoft_support", "https://support.microsoft.com/en-us/publisher/change-page-size-paper-size-or-page-orientation-in-publisher", ["Publisher", "page"]),
]
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

opener = build_opener(NoRedirect)
def request(url, max_bytes=LIMIT):
    req=Request(url, headers={"User-Agent":UA,"Accept":"text/html,application/xhtml+xml"})
    try:
        with opener.open(req, timeout=15) as resp:
            status=resp.status
            body=resp.read(max_bytes+1)
            return status,body,resp.headers.get("Content-Type",""),resp.headers.get("Location","")
    except HTTPError as e:
        return e.code,b"","",e.headers.get("Location","")
    except (URLError,TimeoutError,OSError) as e:
        return None,b"","",str(type(e).__name__),""

def main():
    out=[]
    robots_cache={}
    for ident,url,markers in SOURCES:
        host=urlparse(url).hostname
        robots="https://"+host+"/robots.txt"
        if host not in robots_cache:
            status,body,_,_=request(robots,65536)
            if status==200 and body and len(body)<=65536:
                p=RobotFileParser()
                p.parse(body.decode("utf-8","replace").splitlines())
                robots_cache[host]=(True,p)
            else:
                robots_cache[host]=(False,None)
            time.sleep(1.5)
        ok,parser=robots_cache[host]
        row={"id":ident,"url":url,"robots_available":ok}
        if not ok:
            row["result"]="skipped_robots_unavailable"
        elif not parser.can_fetch(UA,url):
            row["result"]="skipped_robots_disallow"
        else:
            status,body,kind,location=request(url)
            lower=body.decode("utf-8","replace").lower()
            row.update({"status":status,"size_bytes":len(body),"sha256":hashlib.sha256(body).hexdigest() if body else None,
                        "marker_hits":sum(m.lower() in lower for m in markers),
                        "oversize":len(body)>LIMIT,
                        "result":("blocked" if status in (403,429) else
                                  "redirect" if status in (301,302,303,307,308) else
                                  "html_with_markers" if status==200 and body and not len(body)>LIMIT and sum(m.lower() in lower for m in markers)==len(markers) else
                                  "html_without_markers" if status==200 else "http_error")})
            # Do not follow cross-host redirects. Store only a host, no tracking query.
            if location: row["redirect_host"]=urlparse(location).hostname
        out.append(row)
        time.sleep(1.5)
    result={"schema":"sk1.public-forum-access.v1","captured_utc":datetime.now(timezone.utc).isoformat(),"sources":out}
    dest=Path("experiment-results/forum_access.json")
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({"source_count":len(out),"results":[{"id":x["id"],"result":x["result"],"status":x.get("status")} for x in out]}))
if __name__=="__main__":
    main()
