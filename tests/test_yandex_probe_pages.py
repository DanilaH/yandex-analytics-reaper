from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import pytest

from yandex_analytics_reaper.domain import ProbeContext, ProbeKind, ProbeRun, SessionProfile
from yandex_analytics_reaper.sources.yandex.parsers import PageInfo
from yandex_analytics_reaper.sources.yandex.probes import probe_page_from_yandex
from yandex_analytics_reaper.storage import RawSnapshotMetadata


def _run(*, query: str | None = None) -> tuple[ProbeRun, ProbeContext]:
    context = ProbeContext(language="ru", device_type="desktop", platform="desktop_other")
    run = ProbeRun(
        id="probe:test",
        source_id="yandex_public",
        request_key=("catalogue.search" if query is not None else "catalogue.feed"),
        kind=(ProbeKind.SEARCH if query is not None else ProbeKind.RECOMMENDATION_FEED),
        context_id="probe-context:test",
        query_text=query,
        requested_page_limit=3,
        started_at=datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
    )
    return run, context


def _metadata(
    run: ProbeRun,
    context: ProbeContext,
    *,
    page_id: str | None = None,
    rtx_reqid: str | None = None,
) -> RawSnapshotMetadata:
    params: dict[str, object] = {"lang": context.language}
    if page_id is not None:
        params["page_id"] = page_id
    if rtx_reqid is not None:
        params["rtx-reqid"] = rtx_reqid
    request_context: dict[str, object] = {
        "probe_context": context.model_dump(mode="json"),
        "params": params,
    }
    if run.query_text is not None:
        request_context["query"] = run.query_text
    body = b"{}"
    return RawSnapshotMetadata(
        id="20260829T090001000000Z-probepage1",
        source_id=run.source_id,
        retrieved_at=datetime(2026, 8, 29, 9, 0, 1, tzinfo=UTC),
        request_key=run.request_key,
        method="GET",
        url="https://yandex.ru/games/test",
        request_context=request_context,
        content_path="raw/body.json",
        metadata_path="raw/metadata.json",
        content_hash=hashlib.sha256(body).hexdigest(),
        http_status=200,
        content_type="application/json",
        schema_hash=None,
    )


def test_factory_preserves_request_and_response_pagination_tokens() -> None:
    run, context = _run()
    metadata = _metadata(run, context, page_id="page-1", rtx_reqid="req-1")

    page = probe_page_from_yandex(
        run=run,
        context=context,
        metadata=metadata,
        page_index=1,
        page_info=PageInfo(
            next_page_id="page-2",
            rtx_reqid="req-2",
            has_next_page=True,
        ),
    )

    assert page.request_page_id == "page-1"
    assert page.request_rtx_reqid == "req-1"
    assert page.response_next_page_id == "page-2"
    assert page.response_rtx_reqid == "req-2"
    assert page.has_next_page is True


def test_factory_accepts_legacy_raw_context_without_nullable_session_instance() -> None:
    run, context = _run()
    metadata = _metadata(run, context)
    raw_probe_context = dict(metadata.request_context["probe_context"])
    raw_probe_context.pop("session_instance_id")
    legacy = metadata.model_copy(
        update={
            "request_context": {
                **metadata.request_context,
                "probe_context": raw_probe_context,
            }
        }
    )

    page = probe_page_from_yandex(
        run=run,
        context=context,
        metadata=legacy,
        page_index=0,
        page_info=PageInfo(),
    )

    assert page.run_id == run.id


def test_factory_does_not_treat_missing_instance_as_persistent_instance() -> None:
    context = ProbeContext(
        session_profile=SessionProfile.PERSISTENT_ANONYMOUS,
        session_instance_id="session:0123456789abcdef0123456789abcdef",
        cookie_state_hash="a" * 64,
        profile_age_days=0,
    )
    run = ProbeRun(
        id="probe:persistent",
        source_id="yandex_public",
        request_key="catalogue.feed",
        kind=ProbeKind.RECOMMENDATION_FEED,
        context_id="probe-context:persistent",
        requested_page_limit=1,
        started_at=datetime(2026, 8, 29, 9, 0, tzinfo=UTC),
    )
    metadata = _metadata(run, context)
    raw_probe_context = dict(metadata.request_context["probe_context"])
    raw_probe_context.pop("session_instance_id")
    legacy_shaped = metadata.model_copy(
        update={
            "request_context": {
                **metadata.request_context,
                "probe_context": raw_probe_context,
            }
        }
    )

    with pytest.raises(ValueError, match="context does not match"):
        probe_page_from_yandex(
            run=run,
            context=context,
            metadata=legacy_shaped,
            page_index=0,
            page_info=PageInfo(),
        )


def test_factory_rejects_context_or_search_query_mismatch() -> None:
    run, context = _run(query="merge")
    metadata = _metadata(run, context)
    different_context = ProbeContext(language="ru", device_type="mobile")

    with pytest.raises(ValueError, match="context does not match"):
        probe_page_from_yandex(
            run=run,
            context=different_context,
            metadata=metadata,
            page_index=0,
            page_info=PageInfo(),
        )

    bad_query_metadata = metadata.model_copy(
        update={
            "request_context": {
                **metadata.request_context,
                "query": "obby",
            }
        }
    )
    with pytest.raises(ValueError, match="query does not match"):
        probe_page_from_yandex(
            run=run,
            context=context,
            metadata=bad_query_metadata,
            page_index=0,
            page_info=PageInfo(),
        )
