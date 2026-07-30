"""Nạp API key từ .env — không bao giờ commit .env (xem .gitignore)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_dotenv(path: Path, *, override: bool = False) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip("\"'")
        if key and (override or key not in os.environ):
            os.environ[key] = value


def load_env() -> None:
    """Thứ tự ưu tiên: biến môi trường đang có > QA_ENV_FILE > codebase/.env."""
    external = os.getenv("QA_ENV_FILE")
    if external:
        load_dotenv(Path(external).expanduser())
    load_dotenv(ROOT / ".env")
