#!/usr/bin/env python3
"""Read-only Office Forums post extraction audit. No forum text leaves memory.

The output holds URL, checksums, lengths, count, and predeclared *technical*
signal presence only. It contains no raw HTML, quoted posts, names or email.
"""
from __future__ import annotations
import hashlib
import json
import re
import sys
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.robotparser import RobotFileParser

UA = "SK1-PUB-Archive-Research/0.1 (bounded public-source audit)"
LIMIT = 384 * 1024
SOURCES = [
    {
        "id": "office_1100009",
        "url": "https://www.office-forums.com/threads/publisher-cannot-open-the-file-error-1100009.445052/",
        "signals": {
            "error_1100009": "1100009",
            "publisher_2003": "2003",
            "publisher_2007": "2007",
            "hotfix_972566": "972566",
            "bad_file_flag": "promptforbadfiles",
            "norton_mention": "norton",
            "kb_329820": "329820",
            "administrator_suggestion": "administrator",
        },
    },
    {
        "id": "office_overprint",
        "url": "https://www.office-forums.com/threads/trying-to-overprint-keyline-on-inserted-pictures.1606388/",
        "signals": {
            "overprint": "overprint",
            "composite": "composite",
            "separations": "separation",
            "adobe": "adobe",
            "knockout": "knockout",
        },
    },
    {
        "id": "office_linked_picture",
        "url": "https://www.office-forums.com/threads/publication-loses-picture.115049/",
        "signals": {
            "picture": "picture",
            "linked_picture": "linked",
            "graphics_manager": "graphics manager",
            "print": "print",
        },
    },
]

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

OPENER = build_opener(NoRedirect)

def get(url, bound):
    req = Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/xhtml+xml"})
    try:
        with OPENER.open(req, timeout=16) as resp:
            body = resp.read(bound + 1)
            return {"status": resp.status, "body": body,
                    "content_type": resp.headers.get("Content-Type", "")}
    except HTTPError as e:
        return {"status": e.code, "body": b"", "content_type": ""}
    except (URLError, TimeoutError, OSError) as e:
        return {"status": None, "body": b"", "error_type": type(e).__name__, "content_type": ""}

class PostExtractor(HTMLParser):
    """Capture only XenForo post bodies, never surrounding navigation."""
    def __init__(self, target):
        super().__init__(convert_charrefs=True)
        self.target = target
        self.depth = 0
        self.buffer = []
        self.posts = []
        self.inside_ignore = 0
        self.next_page = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set(attrs.get("class", "").split())
        if tag == "a" and ("pageNav-jump--next" in classes or "page-nav-jump--next" in classes):
            self.next_page = True
        if tag == "link" and attrs.get("rel") == "next":
            self.next_page = True
        if self.depth:
            self.depth += 1
            if tag in ("script", "style"):
                self.inside_ignore += 1
            if tag in ("p", "br", "li", "div", "blockquote"):
                self.buffer.append(" ")
            if not self.inside_ignore and tag == "a":
                href = attrs.get("href", "")
                kb = re.search(r"/kb/([0-9]{5,8})", href, flags=re.I)
                if kb:
                    self.buffer.append(" kb/" + kb.group(1) + " ")
        elif tag in ("div", "article") and self.target in classes:
            self.depth = 1
            self.buffer = []

    def handle_startendtag(self, tag, attrs):
        if self.depth and tag == "br":
            self.buffer.append(" ")

    def handle_data(self, data):
        if self.depth and not self.inside_ignore:
            self.buffer.append(data)

    def handle_endtag(self, tag):
        if self.depth:
            if tag in ("script", "style") and self.inside_ignore:
                self.inside_ignore -= 1
            self.depth -= 1
            if not self.depth:
                txt = re.sub(r"\s+", " ", " ".join(self.buffer)).strip()
                if txt:
                    self.posts.append(txt)
                self.buffer = []

def parse_posts(html):
    for target in ("bbWrapper", "message-body", "message-content"):
        p = PostExtractor(target)
        p.feed(html)
        if p.posts:
            return target, p.posts, p.next_page
    return None, [], False

def test_parser():
    html = (
        '<nav>1100009 Norton</nav><div class="bbWrapper">Hello <b>Publisher</b> '
        '1100009 <a href="/kb/329820/en-us">source</a>.</div>'
        '<div class="bbWrapper">Second &amp; post</div>'
    )
    method, posts, next_page = parse_posts(html)
    assert method == "bbWrapper" and len(posts) == 2 and not next_page
    assert "Norton" not in " ".join(posts)
    assert "329820" in posts[0] and "Publisher" in posts[0]
    assert "Second & post" in posts[1]
    method, posts, next_page = parse_posts("<nav>Publisher</nav>")
    assert method is None and posts == [] and not next_page
    method, posts, next_page = parse_posts('<article class="message-body">post</article>')
    assert method == "message-body" and posts == ["post"]
    print("synthetic parser controls PASS")

def allowed(host, url, cache):
    if host not in cache:
        result = get("https://" + host + "/robots.txt", 65536)
        if result["status"] != 200 or not result["body"] or len(result["body"]) > 65536:
            cache[host] = ("robots_unavailable", None)
        else:
            parser = RobotFileParser()
            parser.parse(result["body"].decode("utf-8", "replace").splitlines())
            cache[host] = ("robots_ok", parser)
        time.sleep(1.5)
    reason, parser = cache[host]
    if parser is None:
        return reason
    return "allowed" if parser.can_fetch(UA, url) else "robots_disallow"

def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--self-test":
        test_parser()
        return
    records = []
    robots_cache = {}
    for src in SOURCES:
        host = urlparse(src["url"]).hostname
        result = {"id": src["id"], "url": src["url"]}
        permit = allowed(host, src["url"], robots_cache)
        result["robots"] = permit
        if permit != "allowed":
            result["outcome"] = "skipped_" + permit
            records.append(result)
            continue
        response = get(src["url"], LIMIT)
        status = response["status"]
        result["status"] = status
        if status != 200:
            result["outcome"] = "blocked" if status in (403, 429) else "http_failure"
            result["error_type"] = response.get("error_type")
        else:
            payload = response["body"]
            result["html_bytes"] = len(payload)
            result["html_sha256"] = hashlib.sha256(payload).hexdigest()
            result["truncated"] = len(payload) > LIMIT
            if result["truncated"]:
                result["outcome"] = "truncated_html"
            else:
                match = re.search(r"charset\s*=\s*['\"]?([\w-]+)", response["content_type"], re.I)
                charset = match.group(1) if match else "utf-8"
                try:
                    html = payload.decode(charset, "replace")
                except LookupError:
                    html = payload.decode("utf-8", "replace")
                parser_type, posts, next_page = parse_posts(html)
                result["selector"] = parser_type
                result["post_count"] = len(posts)
                result["post_text_characters"] = sum(map(len, posts))
                result["post_sha256"] = [
                    hashlib.sha256(x.encode("utf-8")).hexdigest() for x in posts
                ]
                result["next_page_detected"] = next_page
                whole = " ".join(posts).lower()
                result["signal_in_posts"] = {
                    name: term.lower() in whole for name, term in src["signals"].items()
                }
                result["outcome"] = (
                    "posts_extracted" if len(posts) > 0
                    and result["post_text_characters"] >= 80
                    else "no_substantive_posts"
                )
        records.append(result)
        time.sleep(1.5)
    output = {
        "schema": "sk1.forum-post-text-audit.v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "policy": "public URLs only, no redirects, robots respected; no raw HTML or post text persisted",
        "records": records,
    }
    folder = Path("experiment-results")
    folder.mkdir(exist_ok=True)
    (folder / "forum_text_audit.json").write_text(
        json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"total": len(records), "summaries": [
        {"id": x["id"], "outcome": x["outcome"], "status": x.get("status"),
         "posts": x.get("post_count"), "chars": x.get("post_text_characters"),
         "signals": x.get("signal_in_posts")}
        for x in records
    ]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
