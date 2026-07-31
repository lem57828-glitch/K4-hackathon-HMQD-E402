import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CODEBASE_DIR = ROOT_DIR / "codebase"
if str(CODEBASE_DIR) not in sys.path:
    sys.path.insert(0, str(CODEBASE_DIR))

from tools import (
    _fold,
    _snippet,
    _terms,
    read_post_thread,
    search_qna_posts,
    tag_vocabulary,
)


class TestTools(unittest.TestCase):
    def test_fold(self):
        self.assertEqual(_fold("Xin Chào"), "xin chao")
        self.assertEqual(_fold("Đơn hàng"), "don hang")
        self.assertEqual(_fold("Lỗi API 401!"), "loi api 401!")
        self.assertEqual(_fold(""), "")

    def test_terms(self):
        terms = _terms("Em bị lỗi 401 khi gọi API!")
        # "em", "bi", "khi" are stopwords
        self.assertIn("loi", terms)
        self.assertIn("401", terms)
        self.assertIn("goi", terms)
        self.assertIn("api", terms)
        self.assertNotIn("em", terms)
        self.assertNotIn("bi", terms)

    def test_snippet(self):
        short_text = "Nội dung ngắn"
        self.assertEqual(_snippet(short_text), "Nội dung ngắn")

        long_text = "A " * 150
        snip = _snippet(long_text)
        self.assertTrue(len(snip) <= 180)
        self.assertTrue(snip.endswith("…"))

    def test_tag_vocabulary(self):
        tags = tag_vocabulary()
        self.assertIsInstance(tags, list)
        self.assertIn("AI/LLM", tags)
        self.assertIn("Frontend", tags)
        self.assertIn("Backend", tags)

    def test_search_qna_posts_empty_query(self):
        res = search_qna_posts(query="")
        self.assertEqual(res["tool"], "search_qna_posts")
        self.assertEqual(res["results"], [])
        self.assertIn("trust_note", res)

    def test_search_qna_posts_only_stopwords(self):
        res = search_qna_posts(query="là và của cho có")
        self.assertEqual(res["results"], [])

    def test_search_qna_posts_valid_query(self):
        # Query with terms matching P-1005 (e.g. 401 API)
        res = search_qna_posts(query="Lỗi gọi API trả về 401", top_k=4)
        self.assertEqual(res["tool"], "search_qna_posts")
        self.assertGreater(len(res["results"]), 0)
        top_hit = res["results"][0]
        self.assertIn("post_id", top_hit)
        self.assertIn("title", top_hit)
        self.assertIn("raw_score", top_hit)
        self.assertIn("term_coverage", top_hit)

    def test_search_qna_posts_with_tag_filter(self):
        res_all = search_qna_posts(query="lỗi API")
        res_backend = search_qna_posts(query="lỗi API", tag="Backend")
        self.assertIsNotNone(res_backend)
        for post in res_backend["results"]:
            tags_lower = [t.lower() for t in post["tags"]]
            self.assertIn("backend", tags_lower)

    def test_read_post_thread_found(self):
        # P-1001 exists in qna_posts.json mock data
        res = read_post_thread(post_id="P-1001")
        self.assertEqual(res["tool"], "read_post_thread")
        self.assertEqual(res["post_id"], "P-1001")
        self.assertIn("title", res)
        self.assertIn("messages", res)
        self.assertIsInstance(res["messages"], list)
        self.assertGreater(len(res["messages"]), 0)

    def test_read_post_thread_case_insensitive(self):
        res = read_post_thread(post_id="p-1001")
        self.assertEqual(res["post_id"], "P-1001")

    def test_read_post_thread_not_found(self):
        res = read_post_thread(post_id="P-9999")
        self.assertEqual(res["tool"], "read_post_thread")
        self.assertEqual(res.get("error"), "post_not_found")
        self.assertIn("message", res)


if __name__ == "__main__":
    unittest.main()
