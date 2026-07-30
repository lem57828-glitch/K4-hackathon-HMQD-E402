"""Hai tool trợ lý được dùng. Cả hai đọc từ `data/qna_posts.json` (mock data).

Cố tình tách thành 2 tool:
  - `search_qna_posts` trả về metadata + snippet, KHÔNG trả thread.
  - `read_post_thread` mới trả toàn bộ hội thoại.

Vì sao tách: bắt model phải mở thread ra đọc trước khi dám kết luận
"đã giải quyết chưa". Nếu gộp một tool, model sẽ đọc `status_label` rồi
kết luận luôn — đúng cái bẫy chúng tôi muốn tránh (xem data/MOCK-DATA.md).
"""

from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "data" / "qna_posts.json"

STOPWORDS = {
    "la", "va", "cua", "cho", "co", "khong", "duoc", "nay", "gi", "the", "nao",
    "minh", "ban", "toi", "em", "anh", "chi", "voi", "trong", "tren", "ve", "thi",
    "ma", "mot", "nhu", "de", "hay", "hoac", "nhung", "can", "phai", "se", "da",
    "dang", "bi", "boi", "tu", "den", "ra", "vao", "sao", "vi", "tai", "lam",
    "bao", "nhieu", "khi", "roi", "nhe", "nha", "cai", "cung", "hon", "rat",
    "qua", "lai", "moi", "them", "xin", "giup", "ai", "day", "nguoi", "kieu",
}

SNIPPET_CHARS = 180

# Nhắc lại luật đọc dữ liệu trong CHÍNH kết quả tool, để nếu system prompt bị
# nén/đổi thì luật vẫn đi kèm dữ liệu.
TRUST_NOTE = (
    "status_label la nhan nguoi gan tay tren Discord, KHONG phai su that. "
    "Phai goi read_post_thread va tu ket luan resolution tu noi dung hoi thoai."
)


def _fold(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", (text or "").lower())
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return stripped.replace("đ", "d")


def _terms(text: str) -> set[str]:
    raw = re.findall(r"[a-z0-9]+", _fold(text))
    return {token for token in raw if len(token) >= 2 and token not in STOPWORDS}


@lru_cache(maxsize=1)
def _dataset() -> dict[str, Any]:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _posts() -> list[dict[str, Any]]:
    return _dataset()["posts"]


def tag_vocabulary() -> list[str]:
    return list(_dataset()["tag_vocabulary"])


def _snippet(text: str) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= SNIPPET_CHARS else flat[:SNIPPET_CHARS - 1] + "…"


def search_qna_posts(query: str = "", tag: str = "", top_k: int = 4) -> dict[str, Any]:
    """Tìm post cũ trong #hỏi-đáp gần với câu hỏi đang được soạn."""
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
    for post in _posts():
        tags = post.get("tags") or []
        if wanted_tag and wanted_tag not in {item.lower() for item in tags}:
            continue

        title_terms = _terms(post["title"])
        body_terms = _terms(post.get("body", ""))
        tag_terms = _terms(" ".join(tags))
        # Thread cũng được tính điểm: nhiều câu hỏi khớp phần trả lời chứ không
        # khớp tiêu đề (ví dụ "charmap codec" nằm trong thread, không ở title).
        thread_terms = _terms(" ".join(message.get("content", "") for message in post.get("messages", [])))

        score = (
            3.0 * len(query_terms & title_terms)
            + 2.0 * len(query_terms & tag_terms)
            + 1.0 * len(query_terms & body_terms)
            + 0.5 * len(query_terms & thread_terms)
        )
        if score <= 0:
            continue

        # Chuẩn hoá về 0..1 theo số token của câu hỏi để model đọc được "khớp bao nhiêu".
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
        "total_posts_searched": len(_posts()),
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
                        "author": message.get("author"),
                        "role": message.get("role"),
                        "at": message.get("at"),
                        "content": message.get("content"),
                    }
                    for message in post.get("messages", [])
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

TOOL_DECLARATIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_qna_posts",
            "description": (
                "Tìm post cũ trong khu #hỏi-đáp của Discord khoá học. "
                "GỌI TOOL NÀY TRƯỚC cho mọi câu hỏi có nội dung kỹ thuật hoặc logistics, "
                "kể cả khi bạn nghĩ mình đã biết câu trả lời. "
                "Trả về tiêu đề, tag, nhãn status và snippet — KHÔNG trả nội dung thảo luận. "
                "Muốn biết vấn đề đã được giải quyết chưa thì phải gọi tiếp read_post_thread. "
                "Không cần gọi khi người dùng chỉ chào hỏi hoặc hỏi trợ lý là ai."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Từ khoá tìm kiếm bằng tiếng Việt/Anh, lấy từ tiêu đề + nội dung câu hỏi của người dùng. Giữ nguyên thông báo lỗi nếu có.",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Lọc theo đúng một tag: AI/LLM, Frontend, Backend, Database, Logistics. Để trống nếu chưa chắc.",
                    },
                    "top_k": {"type": "integer", "description": "Số post trả về, mặc định 4, tối đa 8."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_post_thread",
            "description": (
                "Đọc toàn bộ hội thoại của một post để tự kết luận vấn đề đã được giải quyết, "
                "đang xử lý, hay chưa rõ. BẮT BUỘC gọi trước khi trích dẫn bất kỳ post nào làm nguồn. "
                "Không được suy ra trạng thái từ status_label."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "post_id": {"type": "string", "description": "Mã post, ví dụ P-1005."},
                },
                "required": ["post_id"],
            },
        },
    },
]
