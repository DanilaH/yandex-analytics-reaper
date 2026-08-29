from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from yandex_analytics_reaper.domain import (
    Platform,
    ProbeContext,
    ProbeKind,
    ProbePage,
    ProbeRunStatus,
    SessionProfile,
)
from yandex_analytics_reaper.sources.yandex.parsers import GameCard, YandexFeedParser
from yandex_analytics_reaper.sources.yandex.probes import probe_page_from_yandex
from yandex_analytics_reaper.storage import (
    FilesystemRawSnapshotStore,
    ProbeRunRecord,
    SQLiteProbeRunStore,
)

SPEC_VERSION = "taxonomy-diversity-sample-v1"
SOURCE_ID = "yandex_public"
PARSER_NAME = "YandexFeedParser"
PARSER_VERSION = "2"
DEFAULT_TARGET_SIZE = 150
DEFAULT_MAX_PER_DEVELOPER = 2
_PAGINATION_KEYS = {"page_id", "rtx-reqid"}


class TaxonomySamplingError(ValueError):
    """Explicit raw probe evidence cannot form the requested taxonomy sample."""


class TaxonomySampleManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-diversity-sample-v1"] = "taxonomy-diversity-sample-v1"
    sample_id: str
    target_size: int = Field(default=DEFAULT_TARGET_SIZE, ge=100, le=200)
    max_per_developer: Literal[2] = DEFAULT_MAX_PER_DEVELOPER
    run_ids: tuple[str, ...] = Field(min_length=1)

    @field_validator("sample_id")
    @classmethod
    def validate_sample_id(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("taxonomy sample_id must be nonblank and already trimmed")
        return value

    @field_validator("run_ids")
    @classmethod
    def validate_run_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(value.strip() for value in values)
        if any(not value for value in normalized):
            raise ValueError("taxonomy sampling run IDs cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("taxonomy sampling run IDs must be unique")
        return normalized


class TaxonomySampleEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    probe_run_id: str
    raw_snapshot_id: str
    page_index: int = Field(ge=0)
    source_object_path: str
    origin_key: str


class TaxonomySampleCandidate(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    app_id: int
    observed_titles: tuple[str, ...] = ()
    developer_keys: tuple[str, ...] = ()
    category_ids: tuple[int, ...] = ()
    tag_ids: tuple[int, ...] = ()
    origin_keys: tuple[str, ...] = ()
    evidence: tuple[TaxonomySampleEvidence, ...] = Field(min_length=1)


class TaxonomySampleMember(TaxonomySampleCandidate):
    ordinal: int = Field(ge=0)


class TaxonomyDiversitySampleReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["taxonomy-diversity-sample-v1"] = "taxonomy-diversity-sample-v1"
    sample_id: str
    parser_name: str = PARSER_NAME
    parser_version: str = PARSER_VERSION
    context_id: str
    input_run_ids: tuple[str, ...]
    target_size: int
    max_per_developer: int
    candidate_pool_size: int
    selected: tuple[TaxonomySampleMember, ...]
    pool_category_id_count: int
    selected_category_id_count: int
    pool_tag_id_count: int
    selected_tag_id_count: int
    selected_known_developer_count: int
    selected_origin_keys: tuple[str, ...]
    sample_content_hash: str


@dataclass
class _CandidateAccumulator:
    app_id: int
    titles: set[str] = field(default_factory=set)
    developer_keys: set[str] = field(default_factory=set)
    category_ids: set[int] = field(default_factory=set)
    tag_ids: set[int] = field(default_factory=set)
    origin_keys: set[str] = field(default_factory=set)
    evidence: list[TaxonomySampleEvidence] = field(default_factory=list)


class YandexTaxonomyDiversitySampler:
    """Replay explicit Yandex feed/search runs and select a deterministic diverse sample."""

    def __init__(
        self,
        *,
        raw_store: FilesystemRawSnapshotStore,
        probe_store: SQLiteProbeRunStore,
    ) -> None:
        self.raw_store = raw_store
        self.probe_store = probe_store

    def analyze(self, manifest: TaxonomySampleManifest) -> TaxonomyDiversitySampleReport:
        parser = YandexFeedParser()
        if parser.version != PARSER_VERSION:
            raise TaxonomySamplingError(
                f"{SPEC_VERSION} requires {PARSER_NAME}@{PARSER_VERSION}; "
                f"current parser is @{parser.version}"
            )

        accumulators: dict[str, _CandidateAccumulator] = {}
        expected_context: ProbeContext | None = None
        expected_context_id: str | None = None
        sorted_run_ids = tuple(sorted(manifest.run_ids))

        for run_id in sorted_run_ids:
            record = self.probe_store.get_run(run_id)
            if record is None:
                raise TaxonomySamplingError(f"probe run does not exist: {run_id}")
            _validate_run(record)
            if expected_context is None:
                expected_context = record.context
                expected_context_id = record.run.context_id
            elif (
                record.context != expected_context
                or record.run.context_id != expected_context_id
            ):
                raise TaxonomySamplingError(
                    "taxonomy sampling runs must share one exact ProbeContext"
                )
            self._replay_run(record, parser, accumulators)

        if expected_context_id is None:
            raise RuntimeError("validated taxonomy sample unexpectedly has no probe context")

        candidates = tuple(
            _candidate_from_accumulator(listing_id, accumulator)
            for listing_id, accumulator in sorted(accumulators.items())
        )
        if len(candidates) < manifest.target_size:
            raise TaxonomySamplingError(
                f"organic candidate pool={len(candidates)} is smaller than "
                f"target_size={manifest.target_size}; broaden the explicit input runs"
            )

        selected = select_taxonomy_diversity_candidates(
            candidates,
            target_size=manifest.target_size,
            max_per_developer=manifest.max_per_developer,
        )
        pool_categories = {value for item in candidates for value in item.category_ids}
        selected_categories = {value for item in selected for value in item.category_ids}
        pool_tags = {value for item in candidates for value in item.tag_ids}
        selected_tags = {value for item in selected for value in item.tag_ids}
        selected_developers = {
            developer
            for item in selected
            for developer in item.developer_keys
        }
        selected_origins = tuple(
            sorted({origin for item in selected for origin in item.origin_keys})
        )
        content_hash = _sample_content_hash(
            manifest,
            sorted_run_ids,
            selected,
        )
        return TaxonomyDiversitySampleReport(
            sample_id=manifest.sample_id,
            context_id=expected_context_id,
            input_run_ids=sorted_run_ids,
            target_size=manifest.target_size,
            max_per_developer=manifest.max_per_developer,
            candidate_pool_size=len(candidates),
            selected=selected,
            pool_category_id_count=len(pool_categories),
            selected_category_id_count=len(selected_categories),
            pool_tag_id_count=len(pool_tags),
            selected_tag_id_count=len(selected_tags),
            selected_known_developer_count=len(selected_developers),
            selected_origin_keys=selected_origins,
            sample_content_hash=content_hash,
        )

    def _replay_run(
        self,
        record: ProbeRunRecord,
        parser: YandexFeedParser,
        accumulators: dict[str, _CandidateAccumulator],
    ) -> None:
        run = record.run
        for page in record.pages:
            try:
                metadata = self.raw_store.get_metadata(run.source_id, page.raw_snapshot_id)
                body = self.raw_store.get_body(run.source_id, page.raw_snapshot_id)
            except (OSError, ValueError) as exc:
                raise TaxonomySamplingError(
                    f"raw replay failed for {run.id} page {page.page_index}: {exc}"
                ) from exc
            if metadata.request_key != run.request_key:
                raise TaxonomySamplingError(
                    f"raw page for {run.id} request_key does not match persisted run"
                )
            if not 200 <= metadata.http_status < 300:
                raise TaxonomySamplingError(
                    f"raw page for {run.id} does not have successful HTTP status"
                )
            _validate_request(record, page, metadata.request_context)
            try:
                parsed = parser.parse(body)
                replayed = probe_page_from_yandex(
                    run=run,
                    context=record.context,
                    metadata=metadata,
                    page_index=page.page_index,
                    page_info=parsed.page_info,
                )
            except ValueError as exc:
                raise TaxonomySamplingError(
                    f"raw page for {run.id} cannot be replayed consistently: {exc}"
                ) from exc
            if replayed != page:
                raise TaxonomySamplingError(
                    f"replayed page for {run.id}[{page.page_index}] does not match storage"
                )

            origin_key = _origin_key(record)
            for card in parsed.games:
                if card.sponsored:
                    continue
                if card.source_object_path is None:
                    raise TaxonomySamplingError(
                        "parsed organic taxonomy candidate is missing source_object_path"
                    )
                _accumulate_card(
                    accumulators,
                    card,
                    TaxonomySampleEvidence(
                        probe_run_id=run.id,
                        raw_snapshot_id=metadata.id,
                        page_index=page.page_index,
                        source_object_path=card.source_object_path,
                        origin_key=origin_key,
                    ),
                )


def select_taxonomy_diversity_candidates(
    candidates: Sequence[TaxonomySampleCandidate],
    *,
    target_size: int,
    max_per_developer: int,
) -> tuple[TaxonomySampleMember, ...]:
    """Deterministic greedy coverage/max-distance selection used by the v1 sampler."""

    pool = tuple(sorted(candidates, key=lambda item: item.platform_listing_id))
    if target_size < 1:
        raise ValueError("taxonomy diversity target_size must be positive")
    if target_size > len(pool):
        raise ValueError("taxonomy diversity target_size exceeds candidate pool")
    if max_per_developer < 1:
        raise ValueError("max_per_developer must be positive")
    listing_ids = tuple(item.platform_listing_id for item in pool)
    if len(listing_ids) != len(set(listing_ids)):
        raise ValueError("taxonomy diversity candidates must have unique listing IDs")

    frequencies = Counter(
        token
        for candidate in pool
        for token in _feature_tokens(candidate)
    )
    selected_candidates: list[TaxonomySampleCandidate] = []
    selected_ids: set[str] = set()
    covered_features: set[str] = set()
    covered_origins: set[str] = set()
    developer_counts: Counter[str] = Counter()

    while len(selected_candidates) < target_size:
        eligible = [
            candidate
            for candidate in pool
            if candidate.platform_listing_id not in selected_ids
            and all(
                developer_counts[key] < max_per_developer
                for key in candidate.developer_keys
            )
        ]
        if not eligible:
            raise ValueError(
                "developer diversity cap prevents reaching target_size; broaden the candidate pool"
            )

        def selection_key(
            candidate: TaxonomySampleCandidate,
        ) -> tuple[Fraction, int, Fraction, Fraction, str]:
            features = _feature_tokens(candidate)
            new_feature_weight = sum(
                (Fraction(1, frequencies[token]) for token in features - covered_features),
                start=Fraction(0, 1),
            )
            rarity_weight = sum(
                (Fraction(1, frequencies[token]) for token in features),
                start=Fraction(0, 1),
            )
            new_origin_count = len(set(candidate.origin_keys) - covered_origins)
            min_distance = (
                Fraction(1, 1)
                if not selected_candidates
                else min(
                    _jaccard_distance(features, _feature_tokens(selected))
                    for selected in selected_candidates
                )
            )
            return (
                -new_feature_weight,
                -new_origin_count,
                -min_distance,
                -rarity_weight,
                candidate.platform_listing_id,
            )

        chosen = min(eligible, key=selection_key)
        selected_candidates.append(chosen)
        selected_ids.add(chosen.platform_listing_id)
        covered_features.update(_feature_tokens(chosen))
        covered_origins.update(chosen.origin_keys)
        developer_counts.update(chosen.developer_keys)

    return tuple(
        TaxonomySampleMember(ordinal=ordinal, **candidate.model_dump())
        for ordinal, candidate in enumerate(selected_candidates)
    )


def _validate_run(record: ProbeRunRecord) -> None:
    run = record.run
    context = record.context
    if run.source_id != SOURCE_ID:
        raise TaxonomySamplingError(f"{SPEC_VERSION} requires source_id={SOURCE_ID}")
    expected_request_key = {
        ProbeKind.RECOMMENDATION_FEED: "catalogue.feed",
        ProbeKind.SEARCH: "catalogue.search",
    }.get(run.kind)
    if expected_request_key is None or run.request_key != expected_request_key:
        raise TaxonomySamplingError(
            "taxonomy sampling accepts only recommendation-feed or search probe runs"
        )
    if run.status is not ProbeRunStatus.COMPLETED or run.completed_at is None:
        raise TaxonomySamplingError("taxonomy sampling requires completed probe runs")
    if run.kind is ProbeKind.SEARCH and run.query_text is None:
        raise TaxonomySamplingError("taxonomy search run requires persisted query_text")
    if run.kind is ProbeKind.RECOMMENDATION_FEED and run.query_text is not None:
        raise TaxonomySamplingError("taxonomy feed run must not carry query_text")

    pages = record.pages
    page_count = len(pages)
    if not 1 <= page_count <= run.requested_page_limit:
        raise TaxonomySamplingError("taxonomy sampling run has invalid persisted page count")
    if tuple(page.page_index for page in pages) != tuple(range(page_count)):
        raise TaxonomySamplingError("taxonomy sampling run pages are not contiguous from zero")
    if page_count < run.requested_page_limit and pages[-1].has_next_page:
        raise TaxonomySamplingError(
            "taxonomy sampling run stopped before its limit without source exhaustion"
        )

    if (
        context.session_profile is not SessionProfile.CLEAN_ANONYMOUS
        or context.session_instance_id is not None
        or context.cookie_state_hash is not None
        or context.profile_age_days != 0
        or context.country_observed is not None
        or context.collector_region is not None
    ):
        raise TaxonomySamplingError(
            "taxonomy-diversity-sample-v1 requires clean anonymous null-region provenance"
        )
    if (
        context.language != "ru"
        or context.device_type != "desktop"
        or context.platform != "desktop_other"
    ):
        raise TaxonomySamplingError(
            "taxonomy-diversity-sample-v1 requires ru/desktop/desktop_other context"
        )


def _validate_request(
    record: ProbeRunRecord,
    page: ProbePage,
    request_context: Mapping[str, object],
) -> None:
    if record.run.kind is ProbeKind.RECOMMENDATION_FEED:
        _validate_feed_request(request_context, record.context, page)
        return
    if record.run.kind is ProbeKind.SEARCH:
        _validate_search_request(
            request_context,
            record.context,
            record.run.query_text,
            page,
        )
        return
    raise TaxonomySamplingError("unsupported taxonomy sampling run kind")


def _validate_feed_request(
    request_context: Mapping[str, object],
    context: ProbeContext,
    page: ProbePage,
) -> None:
    if set(request_context) != {"probe_context", "params"}:
        raise TaxonomySamplingError("feed raw request context has undeclared top-level fields")
    if request_context.get("probe_context") != context.model_dump(mode="json"):
        raise TaxonomySamplingError("feed raw probe_context does not match persisted context")
    params = request_context.get("params")
    if not isinstance(params, Mapping):
        raise TaxonomySamplingError("feed raw request is missing params metadata")
    expected_keys = {"games_count", "with_promos", "lang", "device-type", "platform"}
    if page.page_index > 0:
        expected_keys |= _PAGINATION_KEYS
    if set(params) != expected_keys:
        raise TaxonomySamplingError("feed raw params do not match expected request shape")
    games_count = params.get("games_count")
    if (
        not isinstance(games_count, int)
        or isinstance(games_count, bool)
        or not 1 <= games_count <= 100
    ):
        raise TaxonomySamplingError("feed raw games_count must be an integer between 1 and 100")
    expected = {
        "with_promos": "false",
        "lang": context.language,
        "device-type": context.device_type,
        "platform": context.platform,
    }
    for key, value in expected.items():
        if params.get(key) != value:
            raise TaxonomySamplingError(f"feed raw param {key} does not match persisted context")
    _validate_pagination(params, page, prefix="feed")


def _validate_search_request(
    request_context: Mapping[str, object],
    context: ProbeContext,
    query_text: str | None,
    page: ProbePage,
) -> None:
    if query_text is None:
        raise TaxonomySamplingError("search run unexpectedly lacks query_text")
    if set(request_context) != {"probe_context", "query", "params"}:
        raise TaxonomySamplingError("search raw request context has undeclared top-level fields")
    if request_context.get("probe_context") != context.model_dump(mode="json"):
        raise TaxonomySamplingError("search raw probe_context does not match persisted context")
    if request_context.get("query") != query_text:
        raise TaxonomySamplingError("search raw query does not match persisted run query_text")
    params = request_context.get("params")
    if not isinstance(params, Mapping):
        raise TaxonomySamplingError("search raw request is missing params metadata")
    expected_keys = {"query", "lang"}
    if page.page_index > 0:
        expected_keys |= _PAGINATION_KEYS
    if set(params) != expected_keys:
        raise TaxonomySamplingError("search raw params do not match expected request shape")
    if params.get("query") != query_text or params.get("lang") != context.language:
        raise TaxonomySamplingError("search raw query/lang do not match persisted run context")
    _validate_pagination(params, page, prefix="search")


def _validate_pagination(
    params: Mapping[str, object],
    page: ProbePage,
    *,
    prefix: str,
) -> None:
    expected_page_id = None if page.page_index == 0 else page.request_page_id
    expected_rtx = None if page.page_index == 0 else page.request_rtx_reqid
    if _optional_token(params.get("page_id"), prefix=prefix) != expected_page_id:
        raise TaxonomySamplingError(f"{prefix} raw page_id does not match stored page linkage")
    if _optional_token(params.get("rtx-reqid"), prefix=prefix) != expected_rtx:
        raise TaxonomySamplingError(
            f"{prefix} raw rtx-reqid does not match stored page linkage"
        )


def _optional_token(value: object, *, prefix: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TaxonomySamplingError(f"{prefix} pagination token must be a string")
    stripped = value.strip()
    return stripped or None


def _origin_key(record: ProbeRunRecord) -> str:
    if record.run.kind is ProbeKind.RECOMMENDATION_FEED:
        return "feed"
    if record.run.kind is ProbeKind.SEARCH and record.run.query_text is not None:
        return f"search:{record.run.query_text}"
    raise TaxonomySamplingError("validated run unexpectedly lacks an origin key")


def _accumulate_card(
    accumulators: dict[str, _CandidateAccumulator],
    card: GameCard,
    evidence: TaxonomySampleEvidence,
) -> None:
    listing_id = f"{Platform.YANDEX_GAMES.value}:{card.app_id}"
    accumulator = accumulators.setdefault(listing_id, _CandidateAccumulator(app_id=card.app_id))
    if accumulator.app_id != card.app_id:
        raise RuntimeError("taxonomy candidate accumulator listing identity collision")
    if card.title:
        accumulator.titles.add(card.title)
    developer_key = _developer_key(card)
    if developer_key is not None:
        accumulator.developer_keys.add(developer_key)
    accumulator.category_ids.update(card.category_ids)
    accumulator.tag_ids.update(card.tag_ids)
    accumulator.origin_keys.add(evidence.origin_key)
    accumulator.evidence.append(evidence)


def _developer_key(card: GameCard) -> str | None:
    developer = card.developer
    if developer is None:
        return None
    if developer.id is not None:
        return f"id:{developer.id}"
    if developer.name is None:
        return None
    name = developer.name.strip().lower()
    return f"name:{name}" if name else None


def _candidate_from_accumulator(
    listing_id: str,
    accumulator: _CandidateAccumulator,
) -> TaxonomySampleCandidate:
    evidence = tuple(
        sorted(
            accumulator.evidence,
            key=lambda item: (
                item.probe_run_id,
                item.page_index,
                item.raw_snapshot_id,
                item.source_object_path,
            ),
        )
    )
    return TaxonomySampleCandidate(
        platform_listing_id=listing_id,
        app_id=accumulator.app_id,
        observed_titles=tuple(sorted(accumulator.titles)),
        developer_keys=tuple(sorted(accumulator.developer_keys)),
        category_ids=tuple(sorted(accumulator.category_ids)),
        tag_ids=tuple(sorted(accumulator.tag_ids)),
        origin_keys=tuple(sorted(accumulator.origin_keys)),
        evidence=evidence,
    )


def _feature_tokens(candidate: TaxonomySampleCandidate) -> set[str]:
    category_tokens = {f"category:{value}" for value in candidate.category_ids}
    tag_tokens = {f"tag:{value}" for value in candidate.tag_ids}
    return category_tokens | tag_tokens


def _jaccard_distance(first: set[str], second: set[str]) -> Fraction:
    union = first | second
    if not union:
        return Fraction(0, 1)
    return Fraction(len(union - (first & second)), len(union))


def _sample_content_hash(
    manifest: TaxonomySampleManifest,
    input_run_ids: tuple[str, ...],
    selected: tuple[TaxonomySampleMember, ...],
) -> str:
    payload = {
        "spec_version": manifest.spec_version,
        "sample_id": manifest.sample_id,
        "target_size": manifest.target_size,
        "max_per_developer": manifest.max_per_developer,
        "input_run_ids": input_run_ids,
        "selected": [item.model_dump(mode="json") for item in selected],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
