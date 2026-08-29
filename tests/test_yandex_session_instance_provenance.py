from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime, timedelta
from http.cookiejar import MozillaCookieJar
from pathlib import Path

from yandex_analytics_reaper.domain import ProbeContext, SessionProfile
from yandex_analytics_reaper.ingestion import YandexSessionManager


def _manager(tmp_path: Path, current_time: list[datetime]) -> YandexSessionManager:
    return YandexSessionManager(
        state_root=tmp_path / "sessions",
        base_url="https://yandex.ru/games",
        timeout_seconds=1.0,
        user_agent="session-instance-test",
        clock=lambda: current_time[0],
    )


def _profile_dir(tmp_path: Path) -> Path:
    return (
        tmp_path
        / "sessions"
        / "yandex_public"
        / SessionProfile.PERSISTENT_ANONYMOUS.value
        / "default"
    )


def test_clean_anonymous_never_gets_session_instance_id(tmp_path: Path) -> None:
    now = [datetime(2026, 8, 29, 9, 0, tzinfo=UTC)]
    manager = _manager(tmp_path, now)

    with manager.open(ProbeContext()) as session:
        assert session.context.session_instance_id is None


def test_persistent_anonymous_keeps_one_instance_id_across_cookie_churn(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 8, 29, 9, 0, tzinfo=UTC)]
    manager = _manager(tmp_path, now)
    requested = ProbeContext(session_profile=SessionProfile.PERSISTENT_ANONYMOUS)

    with manager.open(requested) as first:
        instance_id = first.context.session_instance_id
        first_hash = first.context.cookie_state_hash
        assert instance_id is not None
        assert instance_id.startswith("session:")
        assert len(instance_id) == len("session:") + 32
        first.client.cookies.set(
            "yandexuid",
            "private-cookie-value",
            domain=".yandex.ru",
            path="/",
        )

    now[0] += timedelta(days=2)
    with manager.open(requested) as second:
        assert second.context.session_instance_id == instance_id
        assert second.context.cookie_state_hash != first_hash
        assert second.context.profile_age_days == 2

    metadata = json.loads((_profile_dir(tmp_path) / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["session_instance_id"] == instance_id
    assert "private-cookie-value" not in json.dumps(metadata)


def test_legacy_persistent_metadata_is_backfilled_with_stable_instance_id(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 8, 29, 9, 0, tzinfo=UTC)]
    manager = _manager(tmp_path, now)
    profile_dir = _profile_dir(tmp_path)
    profile_dir.mkdir(parents=True)

    jar = MozillaCookieJar(str(profile_dir / "cookies.txt"))
    jar.save(ignore_discard=True, ignore_expires=False)
    (profile_dir / "metadata.json").write_text(
        '{"created_at":"2026-08-29T09:00:00Z"}',
        encoding="utf-8",
    )

    requested = ProbeContext(session_profile=SessionProfile.PERSISTENT_ANONYMOUS)
    with manager.open(requested) as first:
        instance_id = first.context.session_instance_id
        assert instance_id is not None

    saved = json.loads((profile_dir / "metadata.json").read_text(encoding="utf-8"))
    assert saved["session_instance_id"] == instance_id

    with manager.open(requested) as second:
        assert second.context.session_instance_id == instance_id


def test_explicit_profile_reset_creates_new_session_instance(tmp_path: Path) -> None:
    now = [datetime(2026, 8, 29, 9, 0, tzinfo=UTC)]
    manager = _manager(tmp_path, now)
    requested = ProbeContext(session_profile=SessionProfile.PERSISTENT_ANONYMOUS)

    with manager.open(requested) as first:
        first_id = first.context.session_instance_id
        assert first_id is not None

    shutil.rmtree(_profile_dir(tmp_path))

    with manager.open(requested) as second:
        second_id = second.context.session_instance_id
        assert second_id is not None
        assert second_id != first_id
