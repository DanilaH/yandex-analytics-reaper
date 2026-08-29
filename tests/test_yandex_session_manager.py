from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from yandex_analytics_reaper.domain import ProbeContext, SessionProfile
from yandex_analytics_reaper.ingestion import (
    PreparedYandexSession,
    SessionConfigurationError,
    SessionStateError,
    YandexSessionManager,
)


def _manager(tmp_path: Path, current_time: list[datetime]) -> YandexSessionManager:
    return YandexSessionManager(
        state_root=tmp_path / "sessions",
        base_url="https://yandex.ru/games",
        timeout_seconds=1.0,
        user_agent="session-test",
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


def _cookies(session: PreparedYandexSession) -> dict[str, str]:
    return {cookie.name: cookie.value for cookie in session.client.cookies.jar}


def test_clean_anonymous_uses_fresh_cookie_jar_for_every_run(tmp_path: Path) -> None:
    now = [datetime(2026, 8, 29, 9, 0, tzinfo=UTC)]
    manager = _manager(tmp_path, now)
    context = ProbeContext(session_profile=SessionProfile.CLEAN_ANONYMOUS)

    with manager.open(context) as first:
        assert first.context.session_profile is SessionProfile.CLEAN_ANONYMOUS
        assert first.context.cookie_state_hash is None
        assert first.context.profile_age_days == 0
        first.client.cookies.set(
            "anonymous-state",
            "first-run-only",
            domain=".yandex.ru",
            path="/",
        )

    with manager.open(context) as second:
        assert "anonymous-state" not in _cookies(second)
        assert second.context.cookie_state_hash is None
        assert second.context.profile_age_days == 0

    assert not (tmp_path / "sessions").exists()


def test_persistent_anonymous_reuses_cookie_state_and_records_only_fingerprint(
    tmp_path: Path,
) -> None:
    current_time = [datetime(2026, 8, 29, 9, 0, tzinfo=UTC)]
    manager = _manager(tmp_path, current_time)
    context = ProbeContext(session_profile=SessionProfile.PERSISTENT_ANONYMOUS)
    raw_cookie_value = "private-anonymous-cookie-value"

    with manager.open(context) as first:
        first_hash = first.context.cookie_state_hash
        assert first_hash is not None and len(first_hash) == 64
        assert first.context.profile_age_days == 0
        first.client.cookies.set(
            "yandexuid",
            raw_cookie_value,
            domain=".yandex.ru",
            path="/",
        )

    profile_dir = _profile_dir(tmp_path)
    assert (profile_dir / "cookies.txt").is_file()
    assert (profile_dir / "metadata.json").is_file()

    current_time[0] += timedelta(days=2)
    with manager.open(context) as second:
        assert _cookies(second)["yandexuid"] == raw_cookie_value
        assert second.context.cookie_state_hash is not None
        assert second.context.cookie_state_hash != first_hash
        assert second.context.profile_age_days == 2
        assert raw_cookie_value not in second.context.model_dump_json()


def test_persistent_anonymous_fails_closed_on_incomplete_state(tmp_path: Path) -> None:
    current_time = [datetime(2026, 8, 29, 9, 0, tzinfo=UTC)]
    manager = _manager(tmp_path, current_time)
    profile_dir = _profile_dir(tmp_path)
    profile_dir.mkdir(parents=True)
    (profile_dir / "metadata.json").write_text(
        '{"created_at":"2026-08-29T09:00:00Z"}',
        encoding="utf-8",
    )

    with pytest.raises(SessionStateError, match="incomplete"):
        manager.open(ProbeContext(session_profile=SessionProfile.PERSISTENT_ANONYMOUS))


def test_persistent_anonymous_rejects_existing_empty_profile_directory(tmp_path: Path) -> None:
    current_time = [datetime(2026, 8, 29, 9, 0, tzinfo=UTC)]
    manager = _manager(tmp_path, current_time)
    _profile_dir(tmp_path).mkdir(parents=True)

    with pytest.raises(SessionStateError, match="incomplete"):
        manager.open(ProbeContext(session_profile=SessionProfile.PERSISTENT_ANONYMOUS))


def test_authenticated_test_is_not_silently_downgraded_to_anonymous(tmp_path: Path) -> None:
    current_time = [datetime(2026, 8, 29, 9, 0, tzinfo=UTC)]
    manager = _manager(tmp_path, current_time)

    with pytest.raises(SessionConfigurationError, match="credential provider"):
        manager.open(ProbeContext(session_profile=SessionProfile.AUTHENTICATED_TEST))


def test_session_state_save_failure_does_not_mask_probe_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_time = [datetime(2026, 8, 29, 9, 0, tzinfo=UTC)]
    manager = _manager(tmp_path, current_time)

    def fail_persist(*args: object, **kwargs: object) -> None:
        raise SessionStateError("state write failed")

    monkeypatch.setattr(manager, "_persist_persistent_state", fail_persist)

    with pytest.raises(RuntimeError, match="probe failed") as exc_info:
        with manager.open(
            ProbeContext(session_profile=SessionProfile.PERSISTENT_ANONYMOUS)
        ):
            raise RuntimeError("probe failed")

    notes = getattr(exc_info.value, "__notes__", [])
    assert any("state write failed" in note for note in notes)
