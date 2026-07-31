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

from provider import ChatProvider, ModelResponse, ProviderError, ToolCall


class TestProvider(unittest.TestCase):
    def setUp(self):
        self.original_env = os.environ.copy()

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.original_env)

    def test_init_defaults(self):
        provider = ChatProvider()
        self.assertEqual(provider.base_url, "https://openrouter.ai/api/v1")
        self.assertEqual(provider.model, "google/gemini-3.5-flash-lite")
        self.assertEqual(provider.api_key_env, "OPENROUTER_API_KEY")

    def test_missing_api_key_raises_error(self):
        if "OPENROUTER_API_KEY" in os.environ:
            del os.environ["OPENROUTER_API_KEY"]
        provider = ChatProvider()
        with self.assertRaises(ProviderError):
            provider.complete([{"role": "user", "content": "Hi"}])

    @patch("urllib.request.urlopen")
    def test_complete_text_response(self, mock_urlopen):
        os.environ["OPENROUTER_API_KEY"] = "mock_key"

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [
                {
                    "message": {
                        "content": "Hello world response",
                        "tool_calls": []
                    }
                }
            ],
            "model": "google/gemini-3.5-flash-lite",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = ChatProvider()
        res = provider.complete([{"role": "user", "content": "Hello"}])

        self.assertIsInstance(res, ModelResponse)
        self.assertEqual(res.text, "Hello world response")
        self.assertEqual(len(res.tool_calls), 0)
        self.assertEqual(res.usage["total_tokens"], 15)

    @patch("urllib.request.urlopen")
    def test_complete_tool_call_response(self, mock_urlopen):
        os.environ["OPENROUTER_API_KEY"] = "mock_key"

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_abc123",
                                "function": {
                                    "name": "search_qna_posts",
                                    "arguments": json.dumps({"query": "Lỗi 401"})
                                }
                            }
                        ]
                    }
                }
            ],
            "model": "test-model"
        }).encode("utf-8")
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        provider = ChatProvider()
        res = provider.complete([{"role": "user", "content": "Check error"}])

        self.assertIsInstance(res, ModelResponse)
        self.assertEqual(len(res.tool_calls), 1)
        call = res.tool_calls[0]
        self.assertEqual(call.id, "call_abc123")
        self.assertEqual(call.name, "search_qna_posts")
        self.assertEqual(call.args, {"query": "Lỗi 401"})


if __name__ == "__main__":
    unittest.main()
