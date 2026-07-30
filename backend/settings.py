import os
from pathlib import Path


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
