"""Vercel serverless entry point for POST /api/dashboard."""
import json
import pathlib
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from growth import service  # noqa: E402

FN = service.dashboard


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            code, body = 200, json.dumps(FN(payload), ensure_ascii=False, default=str).encode()
        except Exception as e:
            code, body = 500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
