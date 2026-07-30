"""Lời gọi AI thật — endpoint kiểu OpenAI Chat Completions, chỉ dùng stdlib.

Chạy được với mọi endpoint OpenAI-compatible:
  - OpenRouter (mặc định)  : QA_API_KEY_ENV=OPENROUTER_API_KEY
  - OpenAI                 : QA_BASE_URL=https://api.openai.com/v1
  - Gemini (compat layer)  : QA_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai

Không dùng SDK để nhóm nào cũng chạy được bằng `python` trần, không pip install.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "google/gemini-3.5-flash-lite"
DEFAULT_KEY_ENV = "OPENROUTER_API_KEY"
# Chặn max_tokens: output của chúng tôi là 1 khối JSON ngắn, không cần dài.
# Để mặc định cao thì OpenRouter free tier trả 402 "requires more credits".
DEFAULT_MAX_TOKENS = 1200


class ProviderError(RuntimeError):
    """Lỗi từ phía provider — để lại nguyên văn cho eval ghi nhận, không nuốt."""


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict[str, Any]


@dataclass
class ModelResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    model: str = ""


class ChatProvider:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_key_env: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
        timeout: int = 90,
        max_retries: int = 3,
    ) -> None:
        self.base_url = (base_url or os.getenv("QA_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.api_key_env = api_key_env or os.getenv("QA_API_KEY_ENV") or DEFAULT_KEY_ENV
        self.model = model or os.getenv("QA_MODEL") or DEFAULT_MODEL
        self.max_tokens = max_tokens or int(os.getenv("QA_MAX_TOKENS") or DEFAULT_MAX_TOKENS)
        self.timeout = timeout
        self.max_retries = max_retries

    def _api_key(self) -> str:
        key = os.getenv(self.api_key_env)
        if not key:
            raise ProviderError(
                f"Thiếu API key: biến môi trường {self.api_key_env} chưa được set. "
                "Copy codebase/.env.example thành codebase/.env rồi điền key."
            )
        return key

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        *,
        temperature: float = 0.0,
        tool_choice: str | None = None,
        response_format_json: bool = False,
    ) -> ModelResponse:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = tool_choice or "auto"
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key()}",
                "Content-Type": "application/json",
                # OpenRouter dùng 2 header này để gắn nhãn app, không bắt buộc.
                "HTTP-Referer": "https://local.demo/discord-qa-assistant",
                "X-Title": "Discord QA Assistant (hackathon)",
            },
            method="POST",
        )

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
                last_error = ProviderError(f"HTTP {exc.code} từ provider: {detail}")
                # 429/5xx thì đáng thử lại; 4xx khác là lỗi của mình, fail nhanh.
                if exc.code not in (408, 409, 429, 500, 502, 503, 504):
                    raise last_error from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                last_error = ProviderError(f"Không gọi được provider: {exc}")
            if attempt < self.max_retries:
                time.sleep(2 * attempt)
        else:
            raise last_error or ProviderError("Gọi provider thất bại không rõ lý do")

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        calls: list[ToolCall] = []
        for raw_call in message.get("tool_calls") or []:
            function = raw_call.get("function") or {}
            try:
                args = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {"_raw_arguments": function.get("arguments")}
            calls.append(ToolCall(
                id=raw_call.get("id") or f"call_{len(calls)}",
                name=function.get("name") or "",
                args=args if isinstance(args, dict) else {"value": args},
            ))

        return ModelResponse(
            text=message.get("content"),
            tool_calls=calls,
            usage=data.get("usage") or {},
            model=data.get("model") or self.model,
        )
