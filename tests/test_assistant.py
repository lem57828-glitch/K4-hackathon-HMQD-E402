import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT_DIR = Path(__file__).resolve().parent.parent
CODEBASE_DIR = ROOT_DIR / "codebase"
if str(CODEBASE_DIR) not in sys.path:
    sys.path.insert(0, str(CODEBASE_DIR))

from assistant import Result, Trace, _extract_json, normalize_output, run, user_message
from provider import ModelResponse, ToolCall


class TestAssistant(unittest.TestCase):
    def test_extract_json_valid_plain(self):
        text = '{"decision": "answer_from_post", "confidence": "high"}'
        res = _extract_json(text)
        self.assertEqual(res["decision"], "answer_from_post")

    def test_extract_json_fenced(self):
        text = 'Here is the decision:\n```json\n{"decision": "create_new_post"}\n```\nHope it helps.'
        res = _extract_json(text)
        self.assertEqual(res["decision"], "create_new_post")

    def test_extract_json_surrounded_text(self):
        text = 'Some prefix text {"decision": "ask_clarify"} suffix text'
        res = _extract_json(text)
        self.assertEqual(res["decision"], "ask_clarify")

    def test_extract_json_invalid(self):
        self.assertIsNone(_extract_json("not a json at all"))
        self.assertIsNone(_extract_json("{broken json:"))

    def test_user_message_builder(self):
        msg = user_message("Tiêu đề test", "Nội dung test")
        self.assertIn("Tiêu đề nháp: Tiêu đề test", msg)
        self.assertIn("Nội dung nháp: Nội dung test", msg)
        self.assertIn("Tag hợp lệ:", msg)

    def test_normalize_output_valid(self):
        known_posts = {
            "P-1001": {"title": "Lỗi 401", "url": "https://discord.com/channels/1/1001"}
        }
        raw = {
            "decision": "answer_from_post",
            "confidence": "high",
            "answer": "Bạn cần kiểm tra API key.",
            "sources": [
                {
                    "post_id": "P-1001",
                    "title": "Model generated title (should be replaced)",
                    "url": "http://bad-url",
                    "resolution": "resolved",
                    "why": "Bài viết giải quyết đúng lỗi 401",
                }
            ],
            "suggested_tags": ["Backend", "Frontend", "InvalidTag"],
        }
        output = normalize_output(raw, known_posts=known_posts)
        warnings = output["warnings"]

        self.assertEqual(output["decision"], "answer_from_post")
        self.assertEqual(output["confidence"], "high")
        self.assertEqual(len(output["sources"]), 1)

        # Verified overwrite of title and url from known_posts
        source = output["sources"][0]
        self.assertEqual(source["title"], "Lỗi 401")
        self.assertEqual(source["url"], "https://discord.com/channels/1/1001")

        # Tags limited to max 2 canonical tags
        self.assertEqual(output["suggested_tags"], ["Backend", "Frontend"])
        self.assertIn("tag ngoài từ vựng bị bỏ: 'InvalidTag'", warnings)

    def test_normalize_output_hallucinated_source(self):
        known_posts = {}  # Empty tool findings
        raw = {
            "decision": "answer_from_post",
            "confidence": "high",
            "sources": [
                {
                    "post_id": "P-9999",
                    "resolution": "resolved",
                }
            ],
        }
        output = normalize_output(raw, known_posts=known_posts)
        warnings = output["warnings"]

        # Source P-9999 removed due to hallucination
        self.assertEqual(len(output["sources"]), 0)
        self.assertTrue(any("BỊA NGUỒN" in w for w in warnings))

    def test_normalize_output_rule_a_violation(self):
        known_posts = {
            "P-1007": {"title": "Model không gọi tool", "url": "http://disc/1007"}
        }
        raw = {
            "decision": "answer_from_post",
            "confidence": "high",
            "sources": [
                {
                    "post_id": "P-1007",
                    "resolution": "in_progress",
                }
            ],
        }
        output = normalize_output(raw, known_posts=known_posts)
        warnings = output["warnings"]

        # Warning generated because answer_from_post lacks a 'resolved' source
        self.assertTrue(any("vi phạm luật A" in w for w in warnings))

    def test_normalize_output_invalid_decision_fallback(self):
        raw = {"decision": "unknown_decision_type"}
        output = normalize_output(raw, known_posts={})
        warnings = output["warnings"]
        self.assertEqual(output["decision"], "create_new_post")
        self.assertTrue(any("decision không hợp lệ" in w for w in warnings))

    def test_run_agent_flow_direct_json(self):
        # Test agent run when model returns final decision JSON directly
        mock_provider = MagicMock()
        mock_provider.complete.return_value = ModelResponse(
            text='{"decision": "refuse_out_of_scope", "confidence": "high", "answer": "Tôi không hỗ trợ giải bài hộ."}',
            tool_calls=[],
            model="mock-model",
            usage={"total_tokens": 50},
        )

        res = run("Giải bài lab hộ em", "", provider=mock_provider)
        self.assertTrue(res.ok)
        self.assertEqual(res.output["decision"], "refuse_out_of_scope")
        self.assertEqual(res.trace.model, "mock-model")

    def test_run_agent_flow_with_tool_calls(self):
        # Test agent run executing tool calls then returning final decision
        mock_provider = MagicMock()

        # Step 1: Model requests tool call search_qna_posts
        resp_tool_call = ModelResponse(
            text=None,
            tool_calls=[
                ToolCall(
                    id="call_1",
                    name="search_qna_posts",
                    args={"query": "lỗi API 401"},
                )
            ],
            model="mock-model",
        )
        # Step 2: Model returns final JSON
        resp_final = ModelResponse(
            text='{"decision": "create_new_post", "confidence": "high", "draft_post": {"title": "Lỗi 401 khi gọi API", "body": "Em bị lỗi 401..."}}',
            tool_calls=[],
            model="mock-model",
        )

        mock_provider.complete.side_effect = [resp_tool_call, resp_final]

        res = run("Lỗi API 401", "Em gọi API bị 401", provider=mock_provider)
        self.assertTrue(res.ok)
        self.assertEqual(res.output["decision"], "create_new_post")
        self.assertEqual(len(res.trace.tool_calls), 1)
        self.assertEqual(res.trace.tool_calls[0]["name"], "search_qna_posts")


if __name__ == "__main__":
    unittest.main()
