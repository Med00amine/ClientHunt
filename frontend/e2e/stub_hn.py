"""Tiny stand-in for the Hacker News (Algolia) API so the browser test never touches the real service."""
import json, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

NOW = int(time.time())
THREAD = {"objectID": "700", "title": "Ask HN: Freelancer? Seeking freelancer? (Stub 2026)", "num_comments": 30, "created_at_i": NOW - 86400}
COMMENTS = [
    {"objectID": "9001", "parent_id": 700, "created_at_i": NOW - 600,
     "comment_text": "SEEKING FREELANCER | Stub Labs | Stub LLM support agent | Remote<p>We need someone to build an LLM agent with RAG in Python. "
                     "Contact Dana Stub &lt;dana@stublabs.example&gt; with your portfolio."},
    {"objectID": "9002", "parent_id": 700, "created_at_i": NOW - 1200,
     "comment_text": "SEEKING WORK | Remote<p>I build LLM apps. Email me: me@seeker.example"},
]


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        url = urlsplit(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path.startswith("/health"):
            body = b"ok"
        elif "story_" in q.get("tags", ""):
            body = json.dumps({"hits": COMMENTS if q["tags"].endswith("story_700") else [], "nbPages": 1}).encode()
        else:
            body = json.dumps({"hits": [THREAD] if "Seeking freelancer" in q.get("query", "") else []}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
