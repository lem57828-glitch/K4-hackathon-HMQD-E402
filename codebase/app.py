"""Web UI cho trợ lý #hỏi-đáp — stdlib thuần, không pip install.

Chạy:  python codebase/app.py
Mở:    http://127.0.0.1:8000

Server chỉ làm 2 việc: phục vụ ui/index.html và nhận POST /api/ask rồi gọi
assistant.run(). Mọi quyết định vẫn nằm ở assistant.py — UI không có nhánh
logic nào tự quyết thay model.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from assistant import run  # noqa: E402
from provider import ChatProvider  # noqa: E402
from tool_backend import BACKEND, tag_vocabulary  # noqa: E402

ROOT = Path(__file__).resolve().parent
UI_PATH = ROOT / "ui" / "index.html"
MAX_BODY_BYTES = 64 * 1024


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:  # bớt ồn, chỉ log lỗi
        if not str(args[1] if len(args) > 1 else "").startswith("2"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, payload: dict) -> None:
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            if not UI_PATH.exists():
                self._send_json(500, {"error": f"Thiếu {UI_PATH}"})
                return
            self._send(200, UI_PATH.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/config":
            provider = ChatProvider()
            self._send_json(200, {
                "model": provider.model,
                "base_url": provider.base_url,
                "api_key_env": provider.api_key_env,
                "api_key_present": bool(os.getenv(provider.api_key_env)),
                "backend": BACKEND,
                "tags": tag_vocabulary(),
            })
        else:
            self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/api/ask":
            self._send_json(404, {"error": "not_found"})
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY_BYTES:
            self._send_json(400, {"ok": False, "error": "Body rỗng hoặc quá lớn"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self._send_json(400, {"ok": False, "error": f"JSON không hợp lệ: {exc}"})
            return

        title = str(payload.get("title") or "")
        body = str(payload.get("body") or "")
        if not title.strip() and not body.strip():
            self._send_json(400, {"ok": False, "error": "Chưa nhập câu hỏi"})
            return

        model = str(payload.get("model") or "").strip() or None
        try:
            result = run(title, body, provider=ChatProvider(model=model))
        except Exception as exc:  # lỗi lạ vẫn phải hiện lên UI, không nuốt
            self._send_json(200, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})
            return

        self._send_json(200, {
            "ok": result.ok,
            "error": result.error,
            "output": result.output,
            "trace": result.trace.as_dict(),
        })


def main() -> None:
    host = os.getenv("QA_UI_HOST", "127.0.0.1")
    port = int(os.getenv("QA_UI_PORT", "8000"))

    provider = ChatProvider()
    print(f"  model      : {provider.model}")
    print(f"  base_url   : {provider.base_url}")
    if os.getenv(provider.api_key_env):
        print(f"  api key    : {provider.api_key_env} OK")
    else:
        print(f"  api key    : THIEU ({provider.api_key_env}) "
              f"-> copy codebase/.env.example thanh codebase/.env roi dien key")
    url = f"http://{host}:{port}"
    print(f"\n  UI         : {url}   (Ctrl+C de dung)\n")

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDa dung server.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
