from __future__ import annotations

import os
from dataclasses import dataclass


def _int_from_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer.") from exc

    if value <= 0:
        raise ValueError(f"{name} must be greater than zero.")

    return value


@dataclass(frozen=True)
class Settings:
    app_name: str = "Citation Cleaner PDF"
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = _int_from_env("PORT", 8000)
    max_upload_mb: int = _int_from_env("MAX_UPLOAD_MB", 25)


settings = Settings()
