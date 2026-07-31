"""Vòng lặp trợ lý: câu hỏi nháp -> tool calls -> một khối JSON quyết định.

Quyết định AI trung tâm (đúng lát cắt trong spec §4):
  1. có post cũ nào trả lời được câu này không, và
  2. đọc hội thoại trong post đó thì vấn đề đã giải quyết chưa.

Mọi lời gọi model đều là gọi thật (xem provider.py). Không có nhánh nào hardcode
câu trả lời. Phần mock duy nhất là nguồn dữ liệu post (data/qna_posts.json).
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from env_loader import load_env
from provider import ChatProvider, ProviderError
from tool_backend import TOOL_DECLARATIONS, TOOL_FUNCTIONS, tag_vocabulary

ROOT = Path(__file__).resolve().parent
SYSTEM_PROMPT_PATH = ROOT / "prompts" / "system_prompt.md"
MAX_TOOL_ROUNDS = 4

DECISIONS = {"answer_from_post", "create_new_post", "ask_clarify", "refuse_out_of_scope"}
RESOLUTIONS = {"resolved", "in_progress", "unclear"}
CONFIDENCES = {"high", "medium", "low"}

load_env()


@dataclass
class Trace:
    """Vết chạy — ghi ra eval/runs/ và hiện trong UI (HAX G11: giải thích vì sao)."""

    rounds: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    latency_ms: int = 0
    usage: dict[str, Any] = field(default_factory=dict)
    raw_final: str | None = None
    repair_used: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "latency_ms": self.latency_ms,
            "usage": self.usage,
            "tool_calls": self.tool_calls,
            "rounds": self.rounds,
            "repair_used": self.repair_used,
            "raw_final": self.raw_final,
        }


@dataclass
class Result:
    ok: bool
    output: dict[str, Any]
    trace: Trace
    error: str | None = None


def system_prompt() -> str:
    return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")


def user_message(title: str, body: str) -> str:
    parts = ["Học viên đang soạn post mới trong #hỏi-đáp."]
    if title.strip():
        parts.append(f"Tiêu đề nháp: {title.strip()}")
    if body.strip():
        parts.append(f"Nội dung nháp: {body.strip()}")
    parts.append(f"Tag hợp lệ: {', '.join(tag_vocabulary())}")
    return "\n".join(parts)


def _extract_json(text: str) -> dict[str, Any] | None:
    """Model hay bọc JSON trong ```json fence hoặc thêm lời dẫn — bóc ra."""
    if not text:
        return None
    candidate = text.strip()
    fence = re.search(r"```(?:json)?\s*(.+?)```", candidate, re.S)
    if fence:
        candidate = fence.group(1).strip()
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(candidate[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def normalize_output(raw: dict[str, Any], *, known_posts: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], list[str]]:
    """Ép output về đúng hợp đồng. Trả về (output, danh sách chỗ đã phải sửa).

    Sửa ở đây là để UI không vỡ, nhưng mọi lần sửa đều được ghi vào `warnings`
    và tính là lỗi khi chấm eval — không im lặng dọn rác cho model.
    """
    warnings: list[str] = []

    decision = str(raw.get("decision") or "").strip()
    if decision not in DECISIONS:
        warnings.append(f"decision không hợp lệ: {decision!r} -> create_new_post")
        decision = "create_new_post"

    confidence = str(raw.get("confidence") or "").strip().lower()
    if confidence not in CONFIDENCES:
        warnings.append(f"confidence không hợp lệ: {confidence!r} -> low")
        confidence = "low"

    sources: list[dict[str, Any]] = []
    for item in raw.get("sources") or []:
        if not isinstance(item, dict):
            warnings.append("bỏ một source không phải object")
            continue
        post_id = str(item.get("post_id") or "").strip().upper()
        known = known_posts.get(post_id)
        if not known:
            warnings.append(f"BỊA NGUỒN: post_id {post_id!r} không có trong kết quả tool -> bỏ")
            continue
        resolution = str(item.get("resolution") or "").strip().lower()
        if resolution not in RESOLUTIONS:
            warnings.append(f"resolution không hợp lệ cho {post_id}: {resolution!r} -> unclear")
            resolution = "unclear"
        # title/url luôn lấy từ tool, không lấy chữ model tự viết.
        sources.append({
            "post_id": post_id,
            "title": known["title"],
            "url": known["url"],
            "resolution": resolution,
            "why": str(item.get("why") or "").strip(),
        })

    vocabulary = {tag.lower(): tag for tag in tag_vocabulary()}
    tags: list[str] = []
    for tag in raw.get("suggested_tags") or []:
        canonical = vocabulary.get(str(tag).strip().lower())
        if canonical and canonical not in tags:
            tags.append(canonical)
        elif not canonical:
            warnings.append(f"tag ngoài từ vựng bị bỏ: {tag!r}")
    if len(tags) > 2:
        warnings.append("nhiều hơn 2 tag -> giữ 2 tag đầu")
        tags = tags[:2]

    draft = raw.get("draft_post")
    if decision == "create_new_post":
        if not isinstance(draft, dict) or not str(draft.get("title") or "").strip():
            warnings.append("create_new_post nhưng thiếu draft_post")
            draft = None
        else:
            draft = {
                "title": str(draft.get("title") or "").strip(),
                "body": str(draft.get("body") or "").strip(),
            }
    else:
        draft = None

    clarify = raw.get("clarify_question")
    clarify = str(clarify).strip() if clarify else None
    if decision == "ask_clarify" and not clarify:
        warnings.append("ask_clarify nhưng thiếu clarify_question")
    if decision != "ask_clarify":
        clarify = None

    if decision == "answer_from_post" and not any(item["resolution"] == "resolved" for item in sources):
        warnings.append("answer_from_post nhưng không có nguồn nào resolved (vi phạm luật A)")

    return {
        "decision": decision,
        "confidence": confidence,
        "answer": str(raw.get("answer") or "").strip(),
        "sources": sources,
        "suggested_tags": tags,
        "draft_post": draft,
        "clarify_question": clarify,
        "next_step": str(raw.get("next_step") or "").strip(),
        "warnings": warnings,
    }


def run(title: str, body: str, *, provider: ChatProvider | None = None) -> Result:
    provider = provider or ChatProvider()
    trace = Trace()
    started = time.monotonic()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt()},
        {"role": "user", "content": user_message(title, body)},
    ]
    # Chỉ post đã đi qua tool mới được phép làm nguồn — chống bịa link.
    known_posts: dict[str, dict[str, Any]] = {}

    final_text: str | None = None
    try:
        for round_index in range(1, MAX_TOOL_ROUNDS + 1):
            response = provider.complete(messages, TOOL_DECLARATIONS, temperature=0.0)
            trace.model = response.model
            for key, value in (response.usage or {}).items():
                if isinstance(value, (int, float)):
                    trace.usage[key] = trace.usage.get(key, 0) + value

            record: dict[str, Any] = {
                "round": round_index,
                "assistant_text": response.text,
                "calls": [{"name": call.name, "args": call.args} for call in response.tool_calls],
            }

            if not response.tool_calls:
                trace.rounds.append(record)
                final_text = response.text
                break

            messages.append({
                "role": "assistant",
                "content": response.text or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.name, "arguments": json.dumps(call.args, ensure_ascii=False)},
                    }
                    for call in response.tool_calls
                ],
            })

            for call in response.tool_calls:
                function = TOOL_FUNCTIONS.get(call.name)
                if not function:
                    payload: dict[str, Any] = {"error": "unknown_tool", "name": call.name}
                else:
                    try:
                        payload = function(**call.args)
                    except TypeError as exc:
                        payload = {"error": "bad_arguments", "message": str(exc)}
                    except Exception as exc:  # tool lỗi là bằng chứng, không nuốt
                        payload = {"error": type(exc).__name__, "message": str(exc)}

                for post in payload.get("results") or []:
                    known_posts[post["post_id"].upper()] = post
                if payload.get("post_id") and not payload.get("error"):
                    known_posts[str(payload["post_id"]).upper()] = {
                        "post_id": payload["post_id"],
                        "title": payload.get("title", ""),
                        "url": payload.get("url", ""),
                    }

                trace.tool_calls.append({"name": call.name, "args": call.args, "result": payload})
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(payload, ensure_ascii=False),
                })

            trace.rounds.append(record)
        else:
            # Hết vòng mà model vẫn gọi tool: chốt bằng một lượt không cho tool.
            messages.append({
                "role": "user",
                "content": "Đã hết lượt gọi tool. Trả về khối JSON quyết định ngay, chỉ dựa trên dữ liệu tool đã trả.",
            })
            response = provider.complete(messages, temperature=0.0, response_format_json=True)
            final_text = response.text
            trace.rounds.append({"round": "final_forced", "assistant_text": response.text, "calls": []})
    except ProviderError as exc:
        trace.latency_ms = int((time.monotonic() - started) * 1000)
        return Result(ok=False, output={}, trace=trace, error=str(exc))

    trace.raw_final = final_text
    parsed = _extract_json(final_text or "")

    if parsed is None:
        # Một lần sửa: yêu cầu model trả lại đúng JSON. Có dùng thì ghi vào trace.
        trace.repair_used = True
        try:
            repair = provider.complete(
                messages + [
                    {"role": "assistant", "content": final_text or ""},
                    {"role": "user", "content": "Output vừa rồi không phải JSON hợp lệ. Trả lại ĐÚNG một khối JSON theo hợp đồng, không thêm chữ nào."},
                ],
                temperature=0.0,
                response_format_json=True,
            )
        except ProviderError as exc:
            trace.latency_ms = int((time.monotonic() - started) * 1000)
            return Result(ok=False, output={}, trace=trace, error=str(exc))
        trace.raw_final = repair.text
        parsed = _extract_json(repair.text or "")

    trace.latency_ms = int((time.monotonic() - started) * 1000)

    if parsed is None:
        return Result(ok=False, output={}, trace=trace, error="Model không trả về JSON đọc được")

    output = normalize_output(parsed, known_posts=known_posts)
    return Result(ok=True, output=output, trace=trace)


if __name__ == "__main__":
    import argparse
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Chạy trợ lý một lần từ dòng lệnh")
    parser.add_argument("--title", default="", help="Tiêu đề post nháp")
    parser.add_argument("--body", default="", help="Nội dung post nháp")
    parser.add_argument("--model", default=None)
    parser.add_argument("--trace", action="store_true", help="In cả vết tool call")
    args = parser.parse_args()

    result = run(args.title, args.body, provider=ChatProvider(model=args.model))
    if not result.ok:
        print(f"LỖI: {result.error}")
        raise SystemExit(1)
    print(json.dumps(result.output, ensure_ascii=False, indent=2))
    if args.trace:
        print("\n--- TRACE ---")
        print(json.dumps(result.trace.as_dict(), ensure_ascii=False, indent=2)[:6000])
