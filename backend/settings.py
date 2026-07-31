import hashlib
import os
import re
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).resolve().parent


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def resolve_path(env_name: str, default: str) -> Path:
    raw_value = os.getenv(env_name, default).strip()
    path = Path(raw_value)

    if path.is_absolute():
        return path

    if path.parts and path.parts[0] == "backend":
        return BASE_DIR.parent / path

    return BASE_DIR / path


def csv_env(name: str, default: str = "*") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def normalize_session_id(session_id: Optional[str]) -> str:
    raw_session = (session_id or "default").strip() or "default"
    return hashlib.sha1(raw_session.encode("utf-8")).hexdigest()[:24]


def collection_name_for_session(base_name: str, session_id: Optional[str]) -> str:
    safe_base = re.sub(r"[^a-zA-Z0-9_-]+", "_", base_name).strip("_-") or "doc_chatbot"
    safe_base = safe_base[:30]
    return f"{safe_base}_{normalize_session_id(session_id)}"


def documents_dir_for_session(base_dir: Path, session_id: Optional[str]) -> Path:
    return base_dir / "sessions" / normalize_session_id(session_id)
