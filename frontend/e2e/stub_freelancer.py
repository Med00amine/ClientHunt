"""Tiny stand-in for the Freelancer.com public API so the browser test never touches the real service."""
import json, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer

NOW = int(time.time())
PROJECTS = [
    {"id": 9001, "title": "Stub LLM support agent", "seo_url": "machine-learning/Stub-LLM-support-agent-9001", "type": "fixed", "status": "active",
     "frontend_project_status": "open", "nonpublic": False, "deleted": False, "budget": {"minimum": 300, "maximum": 900},
     "currency": {"code": "USD", "sign": "$", "exchange_rate": 1.0}, "bid_stats": {"bid_count": 3, "bid_avg": 400},
     "time_submitted": NOW - 600, "jobs": [{"id": 1, "name": "Python"}, {"id": 2, "name": "Machine Learning (ML)"}],
     "description": "Build an LLM agent with RAG in Python. Remote.", "language": "en", "urgent": False},
    {"id": 9002, "title": "Stub crowded chatbot", "seo_url": "ai/Stub-crowded-chatbot-9002", "type": "hourly", "status": "active",
     "frontend_project_status": "open", "nonpublic": False, "deleted": False, "budget": {"minimum": 10, "maximum": 30},
     "currency": {"code": "USD", "sign": "$", "exchange_rate": 1.0}, "bid_stats": {"bid_count": 120, "bid_avg": 20},
     "time_submitted": NOW - 7200, "jobs": [{"id": 3, "name": "Chatbot"}], "description": "A simple chatbot.", "language": "en", "urgent": False},
]


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/health"):
            body = b"ok"
        else:
            body = json.dumps({"status": "success", "result": {"projects": PROJECTS, "total_count": len(PROJECTS)}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


HTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
