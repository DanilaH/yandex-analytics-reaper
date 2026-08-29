from __future__ import annotations

import copy
import hashlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from http.cookiejar import CookieJar, LoadError, MozillaCookieJar
from pathlib import Path
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict

from yandex_analytics_reaper.domain import ProbeContext, SessionProfile
from yandex_analytics_reaper.sources.yandex import YandexPublicClient


class SessionConfigurationError(RuntimeError):
    """The requested session profile cannot be opened with current configuration."""


class SessionStateError(RuntimeError):
    """Persistent local session state is missing, corrupt, or cannot be safely updated."""


class _PersistentSessionMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    created_at: AwareDatetime


@dataclass(slots=True)
class PreparedYandexSession:
    """One prepared HTTP session plus the exact context persisted with its probe run."""

    client: YandexPublicClient
    context: ProbeContext
    _manager: YandexSessionManager
    _persistent_created_at: datetime | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: object, exc: BaseException | None, tb: object) -> None:
        state_error: Exception | None = None
        try:
            if self._persistent_created_at is not None:
                self._manager._persist_persistent_state(
                    self.client,
                    created_at=self._persistent_created_at,
                )
        except Exception as persist_exc:
            if exc is not None:
                exc.add_note(
                    "persistent Yandex session state also failed to save: "
                    f"{type(persist_exc).__name__}: {persist_exc}"
                )
            else:
                state_error = persist_exc
        finally:
            try:
                self.client.close()
            except Exception as close_exc:
                if exc is not None:
                    exc.add_note(
                        "Yandex HTTP session also failed to close: "
                        f"{type(close_exc).__name__}: {close_exc}"
                    )
                elif state_error is not None:
                    state_error.add_note(
                        "Yandex HTTP session also failed to close: "
                        f"{type(close_exc).__name__}: {close_exc}"
                    )
                else:
                    state_error = close_exc
        if state_error is not None:
            raise state_error


class YandexSessionManager:
    """Create clean or persistent anonymous Yandex HTTP sessions without leaking cookies."""

    source_id = YandexPublicClient.source_id

    def __init__(
        self,
        *,
        state_root: Path,
        base_url: str,
        timeout_seconds: float,
        user_agent: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.state_root = state_root
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent
        self.clock = clock or _utc_now

    def open(self, context: ProbeContext) -> PreparedYandexSession:
        now = _aware(self.clock(), "session clock result")

        if context.session_profile is SessionProfile.CLEAN_ANONYMOUS:
            effective_context = context.model_copy(
                update={"cookie_state_hash": None, "profile_age_days": 0}
            )
            return PreparedYandexSession(
                client=self._new_client(),
                context=ProbeContext.model_validate(effective_context.model_dump()),
                _manager=self,
            )

        if context.session_profile is SessionProfile.PERSISTENT_ANONYMOUS:
            jar, created_at = self._load_persistent_state(now)
            effective_context = context.model_copy(
                update={
                    "cookie_state_hash": _cookie_state_hash(jar),
                    "profile_age_days": _profile_age_days(created_at, now),
                }
            )
            return PreparedYandexSession(
                client=self._new_client(cookies=jar),
                context=ProbeContext.model_validate(effective_context.model_dump()),
                _manager=self,
                _persistent_created_at=created_at,
            )

        raise SessionConfigurationError(
            "authenticated_test requires an explicit credential provider; "
            "the default collector intentionally has no authenticated session source"
        )

    def _new_client(self, *, cookies: CookieJar | None = None) -> YandexPublicClient:
        return YandexPublicClient(
            base_url=self.base_url,
            timeout_seconds=self.timeout_seconds,
            user_agent=self.user_agent,
            cookies=cookies,
        )

    @property
    def _profile_dir(self) -> Path:
        return (
            self.state_root
            / self.source_id
            / SessionProfile.PERSISTENT_ANONYMOUS.value
            / "default"
        )

    @property
    def _cookie_path(self) -> Path:
        return self._profile_dir / "cookies.txt"

    @property
    def _metadata_path(self) -> Path:
        return self._profile_dir / "metadata.json"

    def _load_persistent_state(self, now: datetime) -> tuple[MozillaCookieJar, datetime]:
        cookie_exists = self._cookie_path.exists()
        metadata_exists = self._metadata_path.exists()
        if cookie_exists != metadata_exists:
            raise SessionStateError(
                "persistent anonymous session state is incomplete; "
                "delete the local profile directory to create a new baseline"
            )

        if not cookie_exists:
            return MozillaCookieJar(), now

        try:
            metadata = _PersistentSessionMetadata.model_validate_json(
                self._metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError) as exc:
            raise SessionStateError("persistent anonymous session metadata is invalid") from exc

        created_at = metadata.created_at
        if created_at > now:
            raise SessionStateError("persistent anonymous session creation time is in the future")

        jar = MozillaCookieJar(str(self._cookie_path))
        try:
            jar.load(ignore_discard=True, ignore_expires=False)
        except (OSError, LoadError) as exc:
            raise SessionStateError("persistent anonymous cookie jar is invalid") from exc
        return jar, created_at

    def _persist_persistent_state(
        self,
        client: YandexPublicClient,
        *,
        created_at: datetime,
    ) -> None:
        self._profile_dir.mkdir(parents=True, exist_ok=True)
        cookie_tmp = self._cookie_path.with_suffix(".tmp")
        metadata_tmp = self._metadata_path.with_suffix(".tmp")

        jar = MozillaCookieJar(str(cookie_tmp))
        for cookie in client.cookies.jar:
            if not cookie.is_expired():
                jar.set_cookie(copy.copy(cookie))

        try:
            jar.save(ignore_discard=True, ignore_expires=False)
            _make_private(cookie_tmp)
            metadata = _PersistentSessionMetadata(created_at=created_at)
            metadata_tmp.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
            _make_private(metadata_tmp)
            os.replace(cookie_tmp, self._cookie_path)
            os.replace(metadata_tmp, self._metadata_path)
            _make_private(self._cookie_path)
            _make_private(self._metadata_path)
        except OSError as exc:
            _unlink_if_exists(cookie_tmp)
            _unlink_if_exists(metadata_tmp)
            raise SessionStateError("persistent anonymous session state could not be saved") from exc


def _cookie_state_hash(jar: CookieJar) -> str:
    state: list[tuple[str, str, str, str, bool, int | None]] = []
    for cookie in jar:
        if cookie.is_expired():
            continue
        state.append(
            (
                cookie.domain or "",
                cookie.path or "",
                cookie.name,
                cookie.value or "",
                bool(cookie.secure),
                cookie.expires,
            )
        )
    state.sort(key=lambda item: (item[0], item[1], item[2]))
    encoded = json.dumps(
        state,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _profile_age_days(created_at: datetime, now: datetime) -> int:
    if now < created_at:
        raise SessionStateError("persistent anonymous session creation time is in the future")
    return (now - created_at).days


def _make_private(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        # Best effort on platforms/filesystems that do not expose POSIX permissions.
        pass


def _unlink_if_exists(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return value


def _utc_now() -> datetime:
    return datetime.now(UTC)
