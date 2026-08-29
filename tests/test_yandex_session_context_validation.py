from __future__ import annotations

import pytest

from yandex_analytics_reaper.domain import ProbeContext, SessionProfile
from yandex_analytics_reaper.ingestion.yandex_probes import _validate_effective_session_context


def test_clean_effective_context_rejects_session_instance_id() -> None:
    with pytest.raises(ValueError, match="clean_anonymous context cannot carry"):
        ProbeContext(
            session_profile=SessionProfile.CLEAN_ANONYMOUS,
            session_instance_id="session:0123456789abcdef0123456789abcdef",
            profile_age_days=0,
        )


def test_persistent_effective_context_requires_session_instance_id() -> None:
    with pytest.raises(ValueError, match="session instance ID"):
        _validate_effective_session_context(
            ProbeContext(
                session_profile=SessionProfile.PERSISTENT_ANONYMOUS,
                cookie_state_hash="a" * 64,
                profile_age_days=0,
            )
        )


def test_persistent_effective_context_accepts_complete_session_provenance() -> None:
    _validate_effective_session_context(
        ProbeContext(
            session_profile=SessionProfile.PERSISTENT_ANONYMOUS,
            session_instance_id="session:0123456789abcdef0123456789abcdef",
            cookie_state_hash="a" * 64,
            profile_age_days=0,
        )
    )
