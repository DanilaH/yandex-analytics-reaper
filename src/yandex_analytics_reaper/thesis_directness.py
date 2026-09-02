from __future__ import annotations

import statistics
from itertools import combinations
from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from yandex_analytics_reaper.analyst import (
    AnalystComparableMembership,
    AnalystMarketExportReport,
    AnalystSemanticEnrichmentReport,
    validate_analyst_market_export,
    validate_analyst_semantic_enrichment,
)
from yandex_analytics_reaper.thesis_intelligence import (
    ThesisDeclaration,
    ThesisIntelligenceError,
    ThesisSuiteDeclaration,
    canonical_model_hash,
    compile_thesis_suite,
)

ANALYST_DIRECTNESS_REVIEW_SPEC_VERSION: Literal["analyst-directness-review-v1"] = (
    "analyst-directness-review-v1"
)

type AnalystDirectnessVerdictV1 = Literal[
    "confirmed_direct",
    "adjacent",
    "not_direct",
    "unresolved",
]
type DirectnessReasonCodeV1 = Literal[
    "direct_mechanic_and_theme",
    "theme_incidental",
    "mechanic_mismatch",
    "theme_mismatch",
    "mechanic_applies_to_other_object",
    "broader_multi_object_scope",
    "insufficient_context",
    "other",
]
type DirectReviewStateV1 = Literal[
    "not_reviewed",
    "partially_reviewed",
    "all_reviewed_with_confirmed",
    "all_direct_candidates_reviewed_zero_confirmed",
    "no_direct_candidates",
]

_ALLOWED_REASONS: dict[AnalystDirectnessVerdictV1, frozenset[DirectnessReasonCodeV1]] = {
    "confirmed_direct": frozenset({"direct_mechanic_and_theme", "other"}),
    "adjacent": frozenset(
        {
            "theme_incidental",
            "mechanic_applies_to_other_object",
            "broader_multi_object_scope",
            "other",
        }
    ),
    "not_direct": frozenset(
        {
            "theme_incidental",
            "mechanic_mismatch",
            "theme_mismatch",
            "mechanic_applies_to_other_object",
            "broader_multi_object_scope",
            "other",
        }
    ),
    "unresolved": frozenset({"insufficient_context", "other"}),
}


class DirectnessReviewDecisionV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    analyst_verdict: AnalystDirectnessVerdictV1
    reason_code: DirectnessReasonCodeV1
    note: str | None = None
    reviewed_at: AwareDatetime

    @field_validator("platform_listing_id")
    @classmethod
    def validate_listing_id(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("review listing ID must be non-blank and already trimmed")
        return value

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str | None) -> str | None:
        if value is not None and (not value or value != value.strip()):
            raise ValueError("review note must be non-blank and already trimmed when present")
        return value

    @model_validator(mode="after")
    def validate_reason(self) -> Self:
        if self.reason_code not in _ALLOWED_REASONS[self.analyst_verdict]:
            raise ValueError("review verdict/reason_code pair is not allowed by v1 contract")
        if self.reason_code == "other" and self.note is None:
            raise ValueError("reason_code=other requires a review note")
        return self


class AnalystDirectnessReviewRow(DirectnessReviewDecisionV1):
    semantic_directness: Literal["direct_candidate"] = "direct_candidate"


class AnalystDirectnessReviewPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["analyst-directness-review-v1"] = ANALYST_DIRECTNESS_REVIEW_SPEC_VERSION
    suite_id: str
    suite_version: int = Field(ge=1)
    thesis_id: str
    thesis_version: int = Field(ge=1)
    semantic_report_content_hash: str
    review_scope: Literal["direct_candidates"] = "direct_candidates"
    rows: tuple[AnalystDirectnessReviewRow, ...]

    @field_validator("semantic_report_content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value

    @model_validator(mode="after")
    def validate_unique_rows(self) -> Self:
        ids = [item.platform_listing_id for item in self.rows]
        if len(set(ids)) != len(ids):
            raise ValueError("directness review listing IDs must be unique")
        return self


class AnalystDirectnessReviewReport(AnalystDirectnessReviewPayload):
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value


class QueryContributionV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query_text: str
    organic_member_count: int = Field(ge=0)
    unique_contribution_count: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.unique_contribution_count > self.organic_member_count:
            raise ValueError("unique query contribution cannot exceed organic member count")
        return self


class PairwiseQueryOverlapV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    left_query: str
    right_query: str
    intersection_count: int = Field(ge=0)
    union_count: int = Field(ge=0)
    jaccard: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_overlap(self) -> Self:
        if self.intersection_count > self.union_count:
            raise ValueError("query intersection cannot exceed union")
        expected = None if self.union_count == 0 else self.intersection_count / self.union_count
        if self.jaccard != expected:
            raise ValueError("query Jaccard does not match intersection/union")
        return self


class QuerySurfaceQualityV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    query_count: int = Field(ge=1)
    members_seen_by_multiple_queries: int = Field(ge=0)
    multi_query_member_share: float = Field(ge=0.0, le=1.0)
    mean_pairwise_jaccard: float | None = Field(default=None, ge=0.0, le=1.0)
    median_pairwise_jaccard: float | None = Field(default=None, ge=0.0, le=1.0)
    queries: tuple[QueryContributionV1, ...] = Field(min_length=1)
    pairwise: tuple[PairwiseQueryOverlapV1, ...]

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if len(self.queries) != self.query_count:
            raise ValueError("query quality row count must equal query_count")
        query_texts = tuple(item.query_text for item in self.queries)
        if len(set(query_texts)) != len(query_texts):
            raise ValueError("query quality rows must use unique query text")
        expected_pairs = tuple(combinations(query_texts, 2))
        actual_pairs = tuple((item.left_query, item.right_query) for item in self.pairwise)
        if actual_pairs != expected_pairs:
            raise ValueError("pairwise query rows do not follow declaration combinations")
        numeric = [item.jaccard for item in self.pairwise if item.jaccard is not None]
        expected_mean = None if not numeric else statistics.fmean(numeric)
        expected_median = None if not numeric else statistics.median(numeric)
        if self.mean_pairwise_jaccard != expected_mean:
            raise ValueError("mean pairwise Jaccard does not match pairwise rows")
        if self.median_pairwise_jaccard != expected_median:
            raise ValueError("median pairwise Jaccard does not match pairwise rows")
        return self


class CompetitorQualityV1(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_search_union_member_count: int = Field(ge=1)

    semantic_source_observed_count: int = Field(ge=0)
    semantic_source_missing_count: int = Field(ge=0)
    semantic_source_coverage_ratio: float = Field(ge=0.0, le=1.0)

    semantic_direct_candidate_count: int = Field(ge=0)
    semantic_adjacent_candidate_count: int = Field(ge=0)
    semantic_noise_candidate_count: int = Field(ge=0)
    semantic_insufficient_evidence_count: int = Field(ge=0)
    semantic_direct_candidate_share: float = Field(ge=0.0, le=1.0)

    review_artifact_present: bool
    reviewed_direct_candidate_count: int = Field(ge=0)
    confirmed_direct_count: int = Field(ge=0)
    adjacent_after_review_count: int = Field(ge=0)
    rejected_direct_false_positive_count: int = Field(ge=0)
    unresolved_direct_candidate_count: int = Field(ge=0)
    manual_direct_review_coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    direct_review_state: DirectReviewStateV1

    query_surface: QuerySurfaceQualityV1

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        raw = self.raw_search_union_member_count
        if self.semantic_source_observed_count + self.semantic_source_missing_count != raw:
            raise ValueError("semantic source coverage counts must equal raw search union")
        semantic_total = (
            self.semantic_direct_candidate_count
            + self.semantic_adjacent_candidate_count
            + self.semantic_noise_candidate_count
            + self.semantic_insufficient_evidence_count
        )
        if semantic_total != raw:
            raise ValueError("semantic directness counts must equal raw search union")
        if self.semantic_source_coverage_ratio != self.semantic_source_observed_count / raw:
            raise ValueError("semantic source coverage ratio does not match counts")
        if self.semantic_direct_candidate_share != self.semantic_direct_candidate_count / raw:
            raise ValueError("semantic direct candidate share does not match counts")

        direct = self.semantic_direct_candidate_count
        reviewed = self.reviewed_direct_candidate_count
        false_positive = self.rejected_direct_false_positive_count
        if reviewed > direct:
            raise ValueError("reviewed direct candidates cannot exceed semantic direct candidates")
        if false_positive < self.adjacent_after_review_count:
            raise ValueError("false-positive count must include adjacent-after-review rows")
        reviewed_sum = (
            self.confirmed_direct_count
            + false_positive
            + self.unresolved_direct_candidate_count
        )
        if reviewed_sum != reviewed:
            raise ValueError("review verdict counts do not sum to reviewed direct candidates")
        if not self.review_artifact_present and reviewed != 0:
            raise ValueError("review counts require a review artifact")

        if direct == 0:
            if self.manual_direct_review_coverage_ratio is not None:
                raise ValueError("zero-direct review coverage must be null")
            expected_state: DirectReviewStateV1 = "no_direct_candidates"
        else:
            expected_coverage = reviewed / direct
            if self.manual_direct_review_coverage_ratio != expected_coverage:
                raise ValueError("manual direct review coverage ratio does not match counts")
            if reviewed == 0:
                expected_state = "not_reviewed"
            elif reviewed < direct:
                expected_state = "partially_reviewed"
            elif self.confirmed_direct_count > 0:
                expected_state = "all_reviewed_with_confirmed"
            else:
                expected_state = "all_direct_candidates_reviewed_zero_confirmed"
        if self.direct_review_state != expected_state:
            raise ValueError("direct review state does not match review counts")

        surface = self.query_surface
        if surface.members_seen_by_multiple_queries > raw:
            raise ValueError("multi-query member count cannot exceed raw search union")
        if surface.multi_query_member_share != surface.members_seen_by_multiple_queries / raw:
            raise ValueError("multi-query member share does not match raw search union")
        if any(item.organic_member_count > raw for item in surface.queries):
            raise ValueError("query organic member count cannot exceed raw search union")
        return self


def build_directness_review(
    suite: ThesisSuiteDeclaration,
    semantic_report: AnalystSemanticEnrichmentReport,
    *,
    decisions: tuple[DirectnessReviewDecisionV1, ...],
) -> AnalystDirectnessReviewReport:
    suite = ThesisSuiteDeclaration.model_validate(suite.model_dump())
    semantic = validate_analyst_semantic_enrichment(semantic_report)
    thesis = _bind_semantic_report_to_suite(suite, semantic)

    by_id: dict[str, DirectnessReviewDecisionV1] = {}
    for decision in decisions:
        decision = DirectnessReviewDecisionV1.model_validate(decision.model_dump())
        if decision.platform_listing_id in by_id:
            raise ThesisIntelligenceError("directness review decisions must use unique listing IDs")
        by_id[decision.platform_listing_id] = decision

    semantic_by_id = {item.platform_listing_id: item for item in semantic.listings}
    for listing_id in by_id:
        semantic_row = semantic_by_id.get(listing_id)
        if semantic_row is None:
            raise ThesisIntelligenceError("reviewed listing does not exist in semantic report")
        if semantic_row.directness != "direct_candidate":
            raise ThesisIntelligenceError("v1 review may only classify semantic direct candidates")

    rows = tuple(
        AnalystDirectnessReviewRow(**by_id[row.platform_listing_id].model_dump(mode="python"))
        for row in semantic.listings
        if row.platform_listing_id in by_id
    )
    payload = AnalystDirectnessReviewPayload(
        suite_id=suite.suite_id,
        suite_version=suite.suite_version,
        thesis_id=thesis.thesis_id,
        thesis_version=thesis.thesis_version,
        semantic_report_content_hash=semantic.content_hash,
        rows=rows,
    )
    report = AnalystDirectnessReviewReport(
        **payload.model_dump(mode="python"),
        content_hash=canonical_model_hash(payload),
    )
    return validate_directness_review(report, suite=suite, semantic_report=semantic)


def validate_directness_review(
    report: AnalystDirectnessReviewReport,
    *,
    suite: ThesisSuiteDeclaration,
    semantic_report: AnalystSemanticEnrichmentReport,
) -> AnalystDirectnessReviewReport:
    report = AnalystDirectnessReviewReport.model_validate(report.model_dump())
    suite = ThesisSuiteDeclaration.model_validate(suite.model_dump())
    semantic = validate_analyst_semantic_enrichment(semantic_report)
    thesis = _bind_semantic_report_to_suite(suite, semantic)

    payload = AnalystDirectnessReviewPayload.model_validate(
        report.model_dump(exclude={"content_hash"})
    )
    if report.content_hash != canonical_model_hash(payload):
        raise ThesisIntelligenceError("directness review content_hash mismatch")
    if (
        report.suite_id != suite.suite_id
        or report.suite_version != suite.suite_version
        or report.thesis_id != thesis.thesis_id
        or report.thesis_version != thesis.thesis_version
        or report.semantic_report_content_hash != semantic.content_hash
    ):
        raise ThesisIntelligenceError(
            "directness review does not bind supplied suite/semantic report"
        )

    semantic_by_id = {item.platform_listing_id: item for item in semantic.listings}
    semantic_order = {
        item.platform_listing_id: index for index, item in enumerate(semantic.listings)
    }
    previous = -1
    for row in report.rows:
        semantic_row = semantic_by_id.get(row.platform_listing_id)
        if semantic_row is None or semantic_row.directness != "direct_candidate":
            raise ThesisIntelligenceError("review row does not bind a semantic direct candidate")
        index = semantic_order[row.platform_listing_id]
        if index <= previous:
            raise ThesisIntelligenceError("review rows do not follow semantic listing order")
        previous = index
    return report


def build_competitor_quality(
    suite: ThesisSuiteDeclaration,
    semantic_report: AnalystSemanticEnrichmentReport,
    market_export: AnalystMarketExportReport,
    *,
    review: AnalystDirectnessReviewReport | None = None,
) -> CompetitorQualityV1:
    suite = ThesisSuiteDeclaration.model_validate(suite.model_dump())
    semantic = validate_analyst_semantic_enrichment(semantic_report)
    export = validate_analyst_market_export(market_export)
    thesis = _bind_semantic_report_to_suite(suite, semantic)
    comparable_set_id = f"{suite.suite_id}--{thesis.thesis_id}"

    snapshot_mismatch = (
        semantic.snapshot_id != export.snapshot_id
        or semantic.snapshot_content_hash != export.snapshot_content_hash
    )
    if snapshot_mismatch:
        raise ThesisIntelligenceError(
            "semantic report and market export do not bind the same snapshot"
        )

    memberships = tuple(
        item for item in export.comparable_memberships if item.set_id == comparable_set_id
    )
    if not memberships:
        raise ThesisIntelligenceError("market export is missing thesis comparable membership")
    memberships = tuple(sorted(memberships, key=lambda item: item.member_ordinal))
    for membership in memberships:
        if (
            membership.set_version != 1
            or membership.query_family_id != thesis.thesis_id
            or membership.query_family_version != 1
        ):
            raise ThesisIntelligenceError(
                "comparable membership identity disagrees with suite compile contract"
            )
    ordinals = tuple(item.member_ordinal for item in memberships)
    if ordinals != tuple(range(len(memberships))):
        raise ThesisIntelligenceError(
            "thesis comparable member ordinals are not contiguous from zero"
        )
    member_ids = tuple(item.platform_listing_id for item in memberships)
    if len(set(member_ids)) != len(member_ids):
        raise ThesisIntelligenceError("thesis comparable contains duplicate listing IDs")
    semantic_ids = tuple(item.platform_listing_id for item in semantic.listings)
    if semantic_ids != member_ids:
        raise ThesisIntelligenceError(
            "semantic listing order does not equal frozen comparable order"
        )

    if review is not None:
        review = validate_directness_review(review, suite=suite, semantic_report=semantic)

    raw_count = len(member_ids)
    source_observed = sum(item.source is not None for item in semantic.listings)
    direct = sum(item.directness == "direct_candidate" for item in semantic.listings)
    adjacent = sum(item.directness == "adjacent_candidate" for item in semantic.listings)
    noise = sum(item.directness == "noise_candidate" for item in semantic.listings)
    insufficient = sum(item.directness == "insufficient_evidence" for item in semantic.listings)

    reviewed_rows = () if review is None else review.rows
    confirmed = sum(item.analyst_verdict == "confirmed_direct" for item in reviewed_rows)
    adjacent_after_review = sum(item.analyst_verdict == "adjacent" for item in reviewed_rows)
    not_direct = sum(item.analyst_verdict == "not_direct" for item in reviewed_rows)
    unresolved = sum(item.analyst_verdict == "unresolved" for item in reviewed_rows)
    reviewed_count = len(reviewed_rows)
    false_positive = adjacent_after_review + not_direct

    if direct == 0:
        coverage: float | None = None
        state: DirectReviewStateV1 = "no_direct_candidates"
    else:
        coverage = reviewed_count / direct
        if reviewed_count == 0:
            state = "not_reviewed"
        elif reviewed_count < direct:
            state = "partially_reviewed"
        elif confirmed > 0:
            state = "all_reviewed_with_confirmed"
        else:
            state = "all_direct_candidates_reviewed_zero_confirmed"

    return CompetitorQualityV1(
        raw_search_union_member_count=raw_count,
        semantic_source_observed_count=source_observed,
        semantic_source_missing_count=raw_count - source_observed,
        semantic_source_coverage_ratio=source_observed / raw_count,
        semantic_direct_candidate_count=direct,
        semantic_adjacent_candidate_count=adjacent,
        semantic_noise_candidate_count=noise,
        semantic_insufficient_evidence_count=insufficient,
        semantic_direct_candidate_share=direct / raw_count,
        review_artifact_present=review is not None,
        reviewed_direct_candidate_count=reviewed_count,
        confirmed_direct_count=confirmed,
        adjacent_after_review_count=adjacent_after_review,
        rejected_direct_false_positive_count=false_positive,
        unresolved_direct_candidate_count=unresolved,
        manual_direct_review_coverage_ratio=coverage,
        direct_review_state=state,
        query_surface=_build_query_surface(thesis, memberships, raw_count),
    )


def _build_query_surface(
    thesis: ThesisDeclaration,
    memberships: tuple[AnalystComparableMembership, ...],
    raw_count: int,
) -> QuerySurfaceQualityV1:
    query_sets: dict[str, set[str]] = {query: set() for query in thesis.queries}
    query_universe = set(thesis.queries)
    multiple = 0

    for membership in memberships:
        listing_id = membership.platform_listing_id
        source_queries = membership.source_queries
        if not source_queries or any(query not in query_universe for query in source_queries):
            raise ThesisIntelligenceError(
                "comparable membership source_queries disagree with thesis"
            )
        if len(set(source_queries)) != len(source_queries):
            raise ThesisIntelligenceError(
                "comparable membership source_queries contain duplicates"
            )
        if len(source_queries) > 1:
            multiple += 1
        for query in source_queries:
            query_sets[query].add(listing_id)

    query_rows = tuple(
        QueryContributionV1(
            query_text=query,
            organic_member_count=len(query_sets[query]),
            unique_contribution_count=sum(
                membership.platform_listing_id in query_sets[query]
                and len(membership.source_queries) == 1
                for membership in memberships
            ),
        )
        for query in thesis.queries
    )

    pairwise_rows: list[PairwiseQueryOverlapV1] = []
    for left, right in combinations(thesis.queries, 2):
        intersection = len(query_sets[left] & query_sets[right])
        union = len(query_sets[left] | query_sets[right])
        pairwise_rows.append(
            PairwiseQueryOverlapV1(
                left_query=left,
                right_query=right,
                intersection_count=intersection,
                union_count=union,
                jaccard=None if union == 0 else intersection / union,
            )
        )
    numeric = [item.jaccard for item in pairwise_rows if item.jaccard is not None]

    return QuerySurfaceQualityV1(
        query_count=len(thesis.queries),
        members_seen_by_multiple_queries=multiple,
        multi_query_member_share=multiple / raw_count,
        mean_pairwise_jaccard=None if not numeric else statistics.fmean(numeric),
        median_pairwise_jaccard=None if not numeric else statistics.median(numeric),
        queries=query_rows,
        pairwise=tuple(pairwise_rows),
    )


def _bind_semantic_report_to_suite(
    suite: ThesisSuiteDeclaration,
    semantic: AnalystSemanticEnrichmentReport,
) -> ThesisDeclaration:
    matching = tuple(item for item in suite.theses if item.thesis_id == semantic.thesis.thesis_id)
    if len(matching) != 1:
        raise ThesisIntelligenceError(
            "semantic thesis does not identify exactly one suite thesis"
        )
    thesis = matching[0]
    expected_semantic = next(
        item
        for item in compile_thesis_suite(suite).semantic_theses
        if item.thesis_id == thesis.thesis_id
    )
    if semantic.thesis != expected_semantic:
        raise ThesisIntelligenceError(
            "semantic report thesis declaration does not equal suite compilation"
        )
    return thesis


def _require_sha256(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError("value must be a lowercase SHA-256 hex digest")
