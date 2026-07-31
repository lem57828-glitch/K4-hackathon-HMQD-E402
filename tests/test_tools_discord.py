import sys
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CODEBASE_DIR = ROOT_DIR / "codebase"
if str(CODEBASE_DIR) not in sys.path:
    sys.path.insert(0, str(CODEBASE_DIR))

import tools_discord


class TestToolsDiscord(unittest.TestCase):
    def setUp(self):
        # Sample mock discord posts index
        self.sample_posts = [
            {
                "post_id": "P-2001",
                "thread_id": 123456,
                "url": "https://discord.com/channels/1/123456",
                "title": "Lỗi kết nối CSDL PostgreSQL",
                "body": "Tôi không kết nối được PostgreSQL từ backend Python",
                "author": "hocvien_1",
                "created_at": "2026-07-30T10:00:00Z",
                "tags": ["Database", "Backend"],
                "status_label": "solved",
                "reactions": {"👍": 2},
                "messages": [
                    {
                        "author": "hocvien_1",
                        "role": "student",
                        "at": "2026-07-30T10:00:00Z",
                        "content": "Tôi không kết nối được PostgreSQL từ backend Python",
                    },
                    {
                        "author": "TA_1",
                        "role": "ta",
                        "at": "2026-07-30T10:05:00Z",
                        "content": "Bạn hãy đổi DB_HOST thành localhost và kiểm tra port 5432.",
                    },
                    {
                        "author": "hocvien_1",
                        "role": "student",
                        "at": "2026-07-30T10:10:00Z",
                        "content": "Đã sửa được rồi, cảm ơn TA!",
                    },
                ],
            }
        ]
        self.sample_tags = ["AI/LLM", "Frontend", "Backend", "Database", "Logistics"]
        tools_discord.set_index(
            self.sample_posts,
            self.sample_tags,
            guild_id=111,
            channel_id=222,
            built_at="2026-07-30T12:00:00Z",
        )

    def test_index_stats(self):
        stats = tools_discord.index_stats()
        self.assertEqual(stats["source"], "discord")
        self.assertEqual(stats["post_count"], 1)
        self.assertEqual(stats["message_count"], 3)
        self.assertEqual(stats["solved_label_count"], 1)
        self.assertEqual(stats["guild_id"], 111)
        self.assertEqual(stats["channel_id"], 222)

    def test_tag_vocabulary(self):
        vocab = tools_discord.tag_vocabulary()
        self.assertEqual(vocab, self.sample_tags)

    def test_search_qna_posts(self):
        res = tools_discord.search_qna_posts(query="Lỗi PostgreSQL")
        self.assertEqual(res["tool"], "search_qna_posts")
        self.assertEqual(len(res["results"]), 1)
        self.assertEqual(res["results"][0]["post_id"], "P-2001")

    def test_search_qna_posts_tag_filter(self):
        res_db = tools_discord.search_qna_posts(query="PostgreSQL", tag="Database")
        self.assertEqual(len(res_db["results"]), 1)

        res_frontend = tools_discord.search_qna_posts(query="PostgreSQL", tag="Frontend")
        self.assertEqual(len(res_frontend["results"]), 0)

    def test_read_post_thread(self):
        res = tools_discord.read_post_thread("P-2001")
        self.assertEqual(res["tool"], "read_post_thread")
        self.assertEqual(res["post_id"], "P-2001")
        self.assertEqual(len(res["messages"]), 3)

        res_missing = tools_discord.read_post_thread("P-9999")
        self.assertEqual(res_missing.get("error"), "post_not_found")


if __name__ == "__main__":
    unittest.main()
