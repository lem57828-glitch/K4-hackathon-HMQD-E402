"""Hai tool y hệt `tools.py` nhưng dữ liệu đến từ Discord thật.

Kiến trúc — vì sao có lớp INDEX ở giữa thay vì gọi thẳng Discord API:

  1. Tool function là **sync** (`assistant.py` gọi trong vòng lặp thường),
     discord.py là **async**. Gọi async từ trong sync là chỗ dễ deadlock nhất.
  2. Mỗi lượt search mà quét lại forum thì dính rate limit ngay, và người dùng
     phải chờ thêm vài giây trong khi model đang treo.

Nên bot quét forum -> dựng INDEX trong RAM -> tool đọc INDEX đồng bộ. INDEX có
cùng cấu trúc với `data/qna_posts.json`, tức là đọc code search bên dưới sẽ thấy
nó giống hệt bản mock — chủ ý, để đổi backend không đổi hành vi tìm kiếm.

**Shape trả về phải giữ nguyên như `tools.py`.** `assistant.py` dựng
`known_posts` từ `results[].post_id`; đổi shape là vỡ hàng rào chống bịa nguồn.
"""

from __future__ import annotations

import copy
import threading
from typing import Any

# Dùng lại nguyên các hàm chuẩn hoá tiếng Việt + luật đọc dữ liệu của bản mock.
# Hai backend phải chấm điểm giống nhau thì so sánh kết quả mới có nghĩa.
from tools import SNIPPET_CHARS, TRUST_NOTE, _fold, _snippet, _terms  # noqa: F401
from tools import TOOL_DECLARATIONS as _MOCK_DECLARATIONS

DEFAULT_TAGS = ["AI/LLM", "Frontend", "Backend", "Database", "Logistics"]

# Bot ghi vào INDEX từ thread của event loop, tool đọc từ thread khác
# (assistant chạy trong to_thread). Khoá cho chắc.
_LOCK = threading.Lock()
_INDEX: dict[str, Any] = {
    "posts": [],
    "tag_vocabulary": list(DEFAULT_TAGS),
    "guild_id": None,
    "channel_id": None,
    "built_at": None,
    "source": "chưa dựng",
}

# TOOL_DECLARATIONS phải là CÙNG MỘT list object mà assistant.py giữ tham chiếu,
# nên chỉ được sửa tại chỗ, không gán lại.
TOOL_DECLARATIONS: list[dict[str, Any]] = copy.deepcopy(_MOCK_DECLARATIONS)


def _patch_tag_description(tags: list[str]) -> None:
    """Cập nhật mô tả tham số `tag` theo đúng tag có thật trên forum."""
    for declaration in TOOL_DECLARATIONS:
        properties = declaration["function"]["parameters"]["properties"]
        if "tag" in properties:
            properties["tag"]["description"] = (
                f"Lọc theo đúng một tag: {', '.join(tags)}. Để trống nếu chưa chắc."
            )


def set_index(
    posts: list[dict[str, Any]],
    tags: list[str],
    *,
    guild_id: int | None = None,
    channel_id: int | None = None,
    built_at: str | None = None,
) -> None:
    """Bot gọi hàm này sau mỗi lần quét forum xong."""
    clean_tags = [tag for tag in tags if tag] or list(DEFAULT_TAGS)
    with _LOCK:
        _INDEX["posts"] = posts
        _INDEX["tag_vocabulary"] = clean_tags
        _INDEX["guild_id"] = guild_id
        _INDEX["channel_id"] = channel_id
        _INDEX["built_at"] = built_at
        _INDEX["source"] = "discord"
    _patch_tag_description(clean_tags)


def index_stats() -> dict[str, Any]:
    with _LOCK:
        posts = _INDEX["posts"]
        return {
            "source": _INDEX["source"],
            "post_count": len(posts),
            "message_count": sum(len(post.get("messages", [])) for post in posts),
            "solved_label_count": sum(1 for post in posts if post.get("status_label") == "solved"),
            "tag_vocabulary": list(_INDEX["tag_vocabulary"]),
            "built_at": _INDEX["built_at"],
            "guild_id": _INDEX["guild_id"],
            "channel_id": _INDEX["channel_id"],
        }


def _posts() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_INDEX["posts"])


def tag_vocabulary() -> list[str]:
    with _LOCK:
        return list(_INDEX["tag_vocabulary"])


def search_qna_posts(query: str = "", tag: str = "", top_k: int = 4) -> dict[str, Any]:
    """Tìm post cũ trong forum #hỏi-đáp gần với câu hỏi đang được soạn."""
    posts = _posts()
    if not posts:
        return {
            "tool": "search_qna_posts",
            "query": query,
            "results": [],
            "note": "Index chua dung xong hoac forum rong. Dung bia post.",
            "trust_note": TRUST_NOTE,
        }

    query_terms = _terms(query)
    if not query_terms:
        return {
            "tool": "search_qna_posts",
            "query": query,
            "results": [],
            "note": "Query rong hoac chi gom stopword — khong tra ket qua.",
            "trust_note": TRUST_NOTE,
        }

    wanted_tag = (tag or "").strip().lower()
    hits: list[dict[str, Any]] = []
    for post in posts:
        tags = post.get("tags") or []
        if wanted_tag and wanted_tag not in {item.lower() for item in tags}:
            continue

        title_terms = _terms(post["title"])
        body_terms = _terms(post.get("body", ""))
        tag_terms = _terms(" ".join(tags))
        thread_terms = _terms(" ".join(m.get("content", "") for m in post.get("messages", [])))

        score = (
            3.0 * len(query_terms & title_terms)
            + 2.0 * len(query_terms & tag_terms)
            + 1.0 * len(query_terms & body_terms)
            + 0.5 * len(query_terms & thread_terms)
        )
        if score <= 0:
            continue

        coverage = len(query_terms & (title_terms | body_terms | tag_terms | thread_terms)) / len(query_terms)
        messages = post.get("messages", [])
        hits.append({
            "post_id": post["post_id"],
            "title": post["title"],
            "url": post["url"],
            "tags": tags,
            "status_label": post.get("status_label"),
            "snippet": _snippet(post.get("body", "")),
            "message_count": len(messages),
            "last_reply_at": messages[-1]["at"] if messages else post.get("created_at"),
            "last_reply_role": messages[-1].get("role") if messages else None,
            "created_at": post.get("created_at"),
            "raw_score": round(score, 2),
            "term_coverage": round(coverage, 2),
        })

    hits.sort(key=lambda item: (item["raw_score"], item["term_coverage"]), reverse=True)
    limit = max(1, min(int(top_k or 4), 8))
    return {
        "tool": "search_qna_posts",
        "query": query,
        "tag_filter": tag or None,
        "total_posts_searched": len(posts),
        "results": hits[:limit],
        "trust_note": TRUST_NOTE,
    }


def read_post_thread(post_id: str = "") -> dict[str, Any]:
    """Đọc toàn bộ hội thoại của một post để tự kết luận trạng thái."""
    wanted = (post_id or "").strip().upper()
    for post in _posts():
        if post["post_id"].upper() == wanted:
            return {
                "tool": "read_post_thread",
                "post_id": post["post_id"],
                "title": post["title"],
                "url": post["url"],
                "tags": post.get("tags") or [],
                "status_label": post.get("status_label"),
                "reactions": post.get("reactions") or {},
                "messages": [
                    {
                        "author": m.get("author"),
                        "role": m.get("role"),
                        "at": m.get("at"),
                        "content": m.get("content"),
                    }
                    for m in post.get("messages", [])
                ],
                "trust_note": TRUST_NOTE,
            }
    return {
        "tool": "read_post_thread",
        "error": "post_not_found",
        "post_id": post_id,
        "message": "Khong co post nao co id nay. Dung bia noi dung thread.",
    }


TOOL_FUNCTIONS = {
    "search_qna_posts": search_qna_posts,
    "read_post_thread": read_post_thread,
}

_patch_tag_description(list(DEFAULT_TAGS))
