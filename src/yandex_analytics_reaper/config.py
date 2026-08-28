from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    yandex_base_url: str
    http_timeout_seconds: float
    user_agent: str


def load_settings() -> Settings:
    return Settings(
        data_dir=Path(os.getenv("REAPER_DATA_DIR", "./data")),
        yandex_base_url=os.getenv("REAPER_YANDEX_BASE_URL", "https://yandex.ru/games"),
        http_timeout_seconds=float(os.getenv("REAPER_HTTP_TIMEOUT_SECONDS", "30")),
        user_agent=os.getenv(
            "REAPER_USER_AGENT",
            "YandexAnalyticsReaper/0.1 (+private-research)",
        ),
    )
