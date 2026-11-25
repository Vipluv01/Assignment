"""Growth Center server. Standard library only.

    python3 server.py            ->  http://localhost:8000
    PORT=8080 python3 server.py

Set ANTHROPIC_API_KEY (and `pip install -r requirements.txt`) or GEMINI_API_KEY to turn on
the AI copilot. A `.env` file next to this script is read if present.
"""
import json
import mimetypes
import os
import pathlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent
WEB = ROOT / "web"

env = ROOT / ".env"
if env.exists():
    for line in env.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from growth import service  # noqa: E402  (after .env so the provider is detected)

ROUTES = {"/api/dashboard": service.dashboard, "/api/chat": service.chat, "/api/ai-check": lambda payload: service.copilot.gemini_check()}


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body: bytes, ctype="application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/healthz":
            return self._send(200, b'{"ok":true}')
        rel = "index.html" if path in ("/", "") else path.lstrip("/")
        f = (WEB / rel).resolve()
        if WEB not in f.parents or not f.is_file():
            return self._send(404, b'{"error":"not found"}')
        self._send(200, f.read_bytes(), (mimetypes.guess_type(f.name)[0] or "application/octet-stream") + ("; charset=utf-8" if f.suffix in (".html", ".js", ".css") else ""))

    def do_POST(self):
        fn = ROUTES.get(self.path.split("?")[0])
        if not fn:
            return self._send(404, b'{"error":"not found"}')
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 5_000_000:
                return self._send(413, b'{"error":"request too large"}')
            payload = json.loads(self.rfile.read(n) or b"{}")
            out = fn(payload)
            self._send(200, json.dumps(out, ensure_ascii=False, default=str).encode())
        except Exception as e:  # report instead of dropping the connection
            self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}).encode())

    def log_message(self, fmt, *args):
        if os.environ.get("QUIET") != "1":
            super().log_message(fmt, *args)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    print(f"Growth Center on http://localhost:{port}   (AI copilot provider: {service.copilot.provider_name()})")
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
