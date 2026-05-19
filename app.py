from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from competitor_agents.pipeline import DEFAULT_COMPETITORS, DEFAULT_INDUSTRY, run_pipeline


ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"
RUNS_DIR = ROOT / "runs"


class AppHandler(BaseHTTPRequestHandler):
    def _send_headers(self, status: int, content_type: str, content_length: int = 0) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.end_headers()

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self._send_headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self._send_headers(200, content_type, len(body))
        self.wfile.write(body)

    def do_HEAD(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_headers(200, "text/html; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._send_headers(200, "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_headers(200, "application/javascript; charset=utf-8")
            return
        self._send_headers(404, "application/json; charset=utf-8")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"/", "/index.html"}:
            self._send_file(STATIC_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/styles.css":
            self._send_file(STATIC_DIR / "styles.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_file(STATIC_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/api/demo":
            result = run_pipeline(DEFAULT_INDUSTRY, DEFAULT_COMPETITORS)
            RUNS_DIR.mkdir(exist_ok=True)
            (RUNS_DIR / f"{result['run_id']}.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self._send_json(result)
            return
        self._send_json({"error": "Not found"}, status=404)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/analyze":
            self._send_json({"error": "Not found"}, status=404)
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON payload"}, status=400)
            return

        industry = str(payload.get("industry") or DEFAULT_INDUSTRY).strip()
        competitors = payload.get("competitors") or DEFAULT_COMPETITORS
        if isinstance(competitors, str):
            competitors = [item.strip() for item in competitors.split(",") if item.strip()]

        if not industry or not competitors:
            self._send_json({"error": "industry and competitors are required"}, status=400)
            return

        use_live_sources = bool(payload.get("use_live_sources"))
        result = run_pipeline(industry, competitors[:5], use_live_sources=use_live_sources)
        RUNS_DIR.mkdir(exist_ok=True)
        (RUNS_DIR / f"{result['run_id']}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._send_json(result)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    try:
        server = ThreadingHTTPServer((host, port), AppHandler)
    except PermissionError as exc:
        print(
            f"Cannot bind to http://{host}:{port}: {exc}. "
            "Try running from your normal Terminal, or set another port, for example: PORT=8080 python3 app.py",
            file=sys.stderr,
        )
        raise SystemExit(1)
    except OSError as exc:
        print(
            f"Cannot start server at http://{host}:{port}: {exc}. "
            "If the port is busy, try: PORT=8080 python3 app.py",
            file=sys.stderr,
        )
        raise SystemExit(1)
    print(f"Agent competitor analysis app running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
