"""Chọn nguồn dữ liệu cho 2 tool — mock JSON hay Discord thật.

    QA_TOOL_BACKEND=mock      (mặc định) -> tools.py, đọc data/qna_posts.json
    QA_TOOL_BACKEND=discord              -> tools_discord.py, đọc index dựng từ forum

`assistant.py` chỉ import qua file này, nên đổi backend **không đụng** vòng lặp
agent, system prompt, hay hàng rào chống bịa nguồn. Hai backend bắt buộc trả về
cùng một shape — `assistant.py` dựng `known_posts` từ `results[].post_id`, đổi
shape là vỡ luôn hàng rào chống bịa.
"""

from __future__ import annotations

import os

from env_loader import load_env

# Phải nạp .env TRƯỚC khi đọc QA_TOOL_BACKEND, nếu không biến trong .env
# sẽ chưa tồn tại lúc file này chạy.
load_env()

BACKEND = (os.getenv("QA_TOOL_BACKEND") or "mock").strip().lower()

if BACKEND == "discord":
    from tools_discord import TOOL_DECLARATIONS, TOOL_FUNCTIONS, tag_vocabulary
else:
    BACKEND = "mock"
    from tools import TOOL_DECLARATIONS, TOOL_FUNCTIONS, tag_vocabulary

__all__ = ["BACKEND", "TOOL_DECLARATIONS", "TOOL_FUNCTIONS", "tag_vocabulary"]
