import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
CODEBASE_DIR = ROOT_DIR / "codebase"
if str(CODEBASE_DIR) not in sys.path:
    sys.path.insert(0, str(CODEBASE_DIR))

from app import Handler
from assistant import Result, Trace


class MockSocket:
    def makefile(self, *args, **kwargs):
        return io.BytesIO(b"")


class DummyHandler(Handler):
    """Subclass of Handler overriding rfile/wfile for isolated unit testing."""

    def __init__(self, request_bytes: bytes):
        self.rfile = io.BytesIO(request_bytes)
        self.wfile = io.BytesIO()
        self.requestline = "GET / HTTP/1.1"
        self.request_version = "HTTP/1.1"
        self.client_address = ("127.0.0.1", 12345)
        self.command = "GET"
        self.path = "/"
        self.headers = {}

    def setup(self):
        pass

    def finish(self):
        pass

    def log_message(self, fmt, *args):
        pass  # suppress logging during tests


class TestApp(unittest.TestCase):
    def test_get_config(self):
        handler = DummyHandler(b"")
        handler.path = "/api/config"

        handler.do_GET()

        response_bytes = handler.wfile.getvalue()
        self.assertIn(b"200 OK", response_bytes)
        self.assertIn(b"application/json", response_bytes)

        # Extract JSON body
        header_end = response_bytes.find(b"\r\n\r\n") + 4
        body = json.loads(response_bytes[header_end:].decode("utf-8"))

        self.assertIn("model", body)
        self.assertIn("backend", body)
        self.assertIn("tags", body)

    def test_post_ask_empty_body(self):
        handler = DummyHandler(b"")
        handler.path = "/api/ask"
        handler.headers = {"Content-Length": "0"}

        handler.do_POST()

        response_bytes = handler.wfile.getvalue()
        self.assertIn(b"400 Bad Request", response_bytes)

    def test_post_ask_empty_question(self):
        payload = json.dumps({"title": "  ", "body": ""}).encode("utf-8")
        handler = DummyHandler(payload)
        handler.path = "/api/ask"
        handler.headers = {"Content-Length": str(len(payload))}

        handler.do_POST()

        response_bytes = handler.wfile.getvalue()
        self.assertIn(b"400 Bad Request", response_bytes)
        self.assertIn(b"Ch\xc6\xb0a nh\xe1\xba\xadp c\xc3\xa2u h\xe1\xbb\x8fi", response_bytes)  # "Chưa nhập câu hỏi"

    @patch("app.run")
    def test_post_ask_valid(self, mock_run):
        mock_result = Result(
            ok=True,
            output={
                "decision": "answer_from_post",
                "confidence": "high",
                "answer": "Đây là câu trả lời test",
                "sources": [],
                "warnings": [],
            },
            trace=Trace(model="mock-model", latency_ms=120),
        )
        mock_run.return_value = mock_result

        payload = json.dumps({"title": "Hỏi về API 401", "body": "Nội dung"}).encode("utf-8")
        handler = DummyHandler(payload)
        handler.path = "/api/ask"
        handler.headers = {"Content-Length": str(len(payload))}

        handler.do_POST()

        response_bytes = handler.wfile.getvalue()
        self.assertIn(b"200 OK", response_bytes)

        header_end = response_bytes.find(b"\r\n\r\n") + 4
        body = json.loads(response_bytes[header_end:].decode("utf-8"))

        self.assertTrue(body["ok"])
        self.assertEqual(body["output"]["decision"], "answer_from_post")
        self.assertEqual(body["trace"]["model"], "mock-model")


if __name__ == "__main__":
    unittest.main()
