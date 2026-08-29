from __future__ import annotations

from datetime import UTC, datetime

from yandex_analytics_reaper.sources.yandex.schema_contracts import (
    schema_comparison_scope_for_snapshot,
)
from yandex_analytics_reaper.storage import RawSnapshotMetadata


def _metadata(
    *,
    session_profile: str,
    session_instance_id: str | None,
    cookie_state_hash: str | None,
    profile_age_days: int | None,
) -> RawSnapshotMetadata:
    return RawSnapshotMetadata(
        id="20260829T090000000000Z-scope00001",
        source_id="yandex_public",
        retrieved_at=datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
        request_key="catalogue.feed",
        method="GET",
        url="https://yandex.ru/games/api/catalogue/v2/feed/",
        request_context={
            "probe_context": {
                "language": "ru",
                "device_type": "desktop",
                "platform": "desktop_other",
                "country_observed": None,
                "collector_region": None,
                "session_profile": session_profile,
                "session_instance_id": session_instance_id,
                "cookie_state_hash": cookie_state_hash,
                "profile_age_days": profile_age_days,
            },
            "params": {
                "games_count": 20,
                "with_promos": "false",
                "lang": "ru",
                "device-type": "desktop",
                "platform": "desktop_other",
            },
        },
        content_path="raw/body.json",
        metadata_path="raw/metadata.json",
        content_hash="0" * 64,
        http_status=200,
        content_type="application/json",
        schema_hash=None,
    )


def test_cookie_fingerprint_and_profile_age_do_not_fragment_schema_scope() -> None:
    instance_id = "session:0123456789abcdef0123456789abcdef"
    first = _metadata(
        session_profile="persistent_anonymous",
        session_instance_id=instance_id,
        cookie_state_hash="a" * 64,
        profile_age_days=0,
    )
    later = _metadata(
        session_profile="persistent_anonymous",
        session_instance_id=instance_id,
        cookie_state_hash="b" * 64,
        profile_age_days=12,
    )

    assert schema_comparison_scope_for_snapshot(first) == schema_comparison_scope_for_snapshot(later)


def test_nullable_session_instance_is_backward_compatible_with_legacy_scope() -> None:
    current = _metadata(
        session_profile="clean_anonymous",
        session_instance_id=None,
        cookie_state_hash=None,
        profile_age_days=0,
    )
    legacy_probe_context = dict(current.request_context["probe_context"])
    legacy_probe_context.pop("session_instance_id")
    legacy = current.model_copy(
        update={
            "request_context": {
                **current.request_context,
                "probe_context": legacy_probe_context,
            }
        }
    )

    assert schema_comparison_scope_for_snapshot(current) == schema_comparison_scope_for_snapshot(
        legacy
    )


def test_persistent_session_instance_remains_part_of_schema_scope() -> None:
    first = _metadata(
        session_profile="persistent_anonymous",
        session_instance_id="session:0123456789abcdef0123456789abcdef",
        cookie_state_hash="a" * 64,
        profile_age_days=0,
    )
    reset = _metadata(
        session_profile="persistent_anonymous",
        session_instance_id="session:fedcba9876543210fedcba9876543210",
        cookie_state_hash="a" * 64,
        profile_age_days=0,
    )

    assert schema_comparison_scope_for_snapshot(first) != schema_comparison_scope_for_snapshot(reset)


def test_session_profile_remains_part_of_schema_scope() -> None:
    clean = _metadata(
        session_profile="clean_anonymous",
        session_instance_id=None,
        cookie_state_hash=None,
        profile_age_days=0,
    )
    persistent = _metadata(
        session_profile="persistent_anonymous",
        session_instance_id="session:0123456789abcdef0123456789abcdef",
        cookie_state_hash="a" * 64,
        profile_age_days=0,
    )

    assert schema_comparison_scope_for_snapshot(clean) != schema_comparison_scope_for_snapshot(
        persistent
    )
