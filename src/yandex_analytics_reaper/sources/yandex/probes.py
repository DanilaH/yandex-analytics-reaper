from __future__ import annotations

from collections.abc import Mapping

from yandex_analytics_reaper.domain import ProbeContext, ProbePage, ProbeRun
from yandex_analytics_reaper.storage import RawSnapshotMetadata

from .parsers import PageInfo

_SUPPORTED_REQUEST_KEYS = {"catalogue.feed", "catalogue.search"}


def probe_page_from_yandex(
    *,
    run: ProbeRun,
    context: ProbeContext,
    metadata: RawSnapshotMetadata,
    page_index: int,
    page_info: PageInfo,
) -> ProbePage:
    """Validate raw request identity and map one parsed Yandex page into a generic probe page."""

    if metadata.source_id != run.source_id:
        raise ValueError("raw probe page source_id does not match probe run")
    if metadata.request_key != run.request_key:
        raise ValueError("raw probe page request_key does not match probe run")
    if metadata.request_key not in _SUPPORTED_REQUEST_KEYS:
        raise ValueError(f"unsupported paginated Yandex request_key: {metadata.request_key}")

    raw_context = metadata.request_context.get("probe_context")
    if not _probe_context_matches(raw_context, context):
        raise ValueError("raw probe page context does not match probe run context")

    if metadata.request_key == "catalogue.search":
        raw_query = metadata.request_context.get("query")
        if not isinstance(raw_query, str) or raw_query.strip() != run.query_text:
            raise ValueError("raw search query does not match probe run query")

    params = metadata.request_context.get("params")
    if not isinstance(params, Mapping):
        raise ValueError("raw paginated probe request is missing params metadata")

    return ProbePage(
        run_id=run.id,
        page_index=page_index,
        raw_snapshot_id=metadata.id,
        retrieved_at=metadata.retrieved_at,
        request_page_id=_optional_token(params.get("page_id")),
        request_rtx_reqid=_optional_token(params.get("rtx-reqid")),
        response_next_page_id=page_info.next_page_id,
        response_rtx_reqid=page_info.rtx_reqid,
        has_next_page=page_info.has_next_page,
    )


def _probe_context_matches(raw_context: object, context: ProbeContext) -> bool:
    if not isinstance(raw_context, Mapping):
        return False
    expected = context.model_dump(mode="json")
    if expected.get("session_instance_id") is None and "session_instance_id" not in raw_context:
        expected.pop("session_instance_id", None)
    return dict(raw_context) == expected


def _optional_token(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("pagination token in raw request metadata must be a string")
    stripped = value.strip()
    return stripped or None
