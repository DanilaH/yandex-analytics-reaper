from __future__ import annotations

import csv
import hashlib
import html as html_lib
import json
import re
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from yandex_analytics_reaper.sources.yandex.parsers import GameDetails, YandexGetGamesParser
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore

from .snapshot import AnalystSnapshotReport, validate_analyst_snapshot_report

ANALYST_SEMANTIC_THESIS_SPEC_VERSION: Literal["analyst-semantic-thesis-v1"] = (
    "analyst-semantic-thesis-v1"
)
ANALYST_SEMANTIC_ENRICHMENT_SPEC_VERSION: Literal["analyst-semantic-enrichment-v1"] = (
    "analyst-semantic-enrichment-v1"
)
ANALYST_SEMANTIC_CLASSIFIER_VERSION: Literal["lexical-directness-v1"] = (
    "lexical-directness-v1"
)
_YANDEX_LISTING_PREFIX = "yandex_games:"
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")

SemanticMatchStatus = Literal["match", "no_match", "unknown", "not_configured"]
SemanticDirectness = Literal[
    "direct_candidate",
    "adjacent_candidate",
    "noise_candidate",
    "insufficient_evidence",
]
SemanticTextField = Literal[
    "title",
    "description",
    "instruction",
    "seo_description",
    "categories_names",
]
_TEXT_FIELDS: tuple[SemanticTextField, ...] = (
    "title",
    "description",
    "instruction",
    "seo_description",
    "categories_names",
)


class AnalystSemanticError(ValueError):
    """Semantic enrichment cannot be reconstructed without weakening provenance."""


class AnalystSemanticRule(BaseModel):
    """Transparent lexical rule for one thesis dimension."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    terms: tuple[str, ...] = Field(min_length=1)

    @field_validator("terms")
    @classmethod
    def validate_terms(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized: set[str] = set()
        for value in values:
            if not value or value != value.strip():
                raise ValueError("semantic terms must be non-blank and already trimmed")
            token = _normalize_text(value)
            if not token:
                raise ValueError("semantic terms must contain searchable text")
            if token in normalized:
                raise ValueError("semantic terms must be unique after normalization")
            normalized.add(token)
        return values


class AnalystSemanticThesisDeclaration(BaseModel):
    """Versioned lexical triage definition for one mechanic × theme thesis."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["analyst-semantic-thesis-v1"]
    thesis_id: str
    version: int = Field(ge=1)
    label: str
    target_set_ids: tuple[str, ...] = ()
    theme: AnalystSemanticRule
    mechanic: AnalystSemanticRule
    reward_grammar: AnalystSemanticRule | None = None

    @field_validator("thesis_id", "label")
    @classmethod
    def validate_trimmed_non_blank(cls, value: str) -> str:
        if not value or value != value.strip():
            raise ValueError("thesis identifiers/labels must be non-blank and already trimmed")
        return value

    @field_validator("target_set_ids")
    @classmethod
    def validate_target_set_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not value or value != value.strip() for value in values):
            raise ValueError("target_set_ids must be non-blank and already trimmed")
        if len(set(values)) != len(values):
            raise ValueError("target_set_ids must be unique")
        return values


class AnalystSemanticCorpus(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = None
    description: str | None = None
    instruction: str | None = None
    seo_description: str | None = None
    categories_names: tuple[str, ...] = ()
    category_ids: tuple[int, ...] = ()
    tag_ids: tuple[int, ...] = ()


class AnalystSemanticSourceReference(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_snapshot_id: str
    retrieved_at: str
    source_object_path: str
    parser_name: str
    parser_version: str


class AnalystSemanticEvidenceSnippet(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    field: SemanticTextField
    term: str
    snippet: str


class AnalystSemanticDimensionResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: SemanticMatchStatus
    matched_terms: tuple[str, ...] = ()
    evidence_snippets: tuple[AnalystSemanticEvidenceSnippet, ...] = ()

    @model_validator(mode="after")
    def validate_result(self) -> Self:
        if self.status == "match":
            if not self.matched_terms or not self.evidence_snippets:
                raise ValueError("matched semantic dimension requires terms and evidence snippets")
        elif self.matched_terms or self.evidence_snippets:
            raise ValueError("non-match semantic dimension cannot claim matched evidence")
        return self


class AnalystSemanticListingRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    platform_listing_id: str
    external_app_id: str
    canonical_url: str
    comparable_set_ids: tuple[str, ...] = Field(min_length=1)
    source: AnalystSemanticSourceReference | None
    corpus: AnalystSemanticCorpus
    theme_match: AnalystSemanticDimensionResult
    mechanic_match: AnalystSemanticDimensionResult
    reward_grammar_match: AnalystSemanticDimensionResult
    directness: SemanticDirectness


class AnalystSemanticEnrichmentPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["analyst-semantic-enrichment-v1"]
    classifier_version: Literal["lexical-directness-v1"]
    snapshot_id: str
    snapshot_content_hash: str
    thesis: AnalystSemanticThesisDeclaration
    listings: tuple[AnalystSemanticListingRow, ...] = Field(min_length=1)


class AnalystSemanticEnrichmentReport(AnalystSemanticEnrichmentPayload):
    content_hash: str

    @field_validator("snapshot_content_hash", "content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        invalid_character = any(character not in "0123456789abcdef" for character in value)
        if len(value) != 64 or invalid_character:
            raise ValueError("semantic report hashes must be lowercase SHA-256 hex digests")
        return value


class AnalystSemanticEnricher:
    """Replay frozen rich metadata into an auditable lexical directness triage artifact."""

    def __init__(self, *, raw_store: FilesystemRawSnapshotStore) -> None:
        self.raw_store = raw_store

    def build(
        self,
        snapshot: AnalystSnapshotReport,
        thesis: AnalystSemanticThesisDeclaration,
    ) -> AnalystSemanticEnrichmentReport:
        snapshot = validate_analyst_snapshot_report(snapshot)
        thesis = AnalystSemanticThesisDeclaration.model_validate(thesis.model_dump())
        target_listing_order, memberships = _target_listings(snapshot, thesis.target_set_ids)
        latest_details = self._latest_catalogue_details(snapshot, set(target_listing_order))

        rows = tuple(
            self._listing_row(
                listing_id,
                memberships[listing_id],
                latest_details.get(listing_id),
                thesis,
            )
            for listing_id in target_listing_order
        )
        payload = AnalystSemanticEnrichmentPayload(
            spec_version=ANALYST_SEMANTIC_ENRICHMENT_SPEC_VERSION,
            classifier_version=ANALYST_SEMANTIC_CLASSIFIER_VERSION,
            snapshot_id=snapshot.snapshot_id,
            snapshot_content_hash=snapshot.content_hash,
            thesis=thesis,
            listings=rows,
        )
        return AnalystSemanticEnrichmentReport.model_validate(
            {**payload.model_dump(mode="python"), "content_hash": _payload_hash(payload)}
        )

    def _latest_catalogue_details(
        self,
        snapshot: AnalystSnapshotReport,
        target_listing_ids: set[str],
    ) -> dict[str, tuple[datetime, str, GameDetails]]:
        parser = YandexGetGamesParser()
        latest: dict[str, tuple[datetime, str, GameDetails]] = {}
        for binding in snapshot.rich_metadata:
            if binding.request_key != "catalogue.get_games":
                continue
            parser_mismatch = (
                binding.parser_name != type(parser).__name__
                or binding.parser_version != parser.version
            )
            if parser_mismatch:
                raise AnalystSemanticError(
                    "semantic enrichment requires the same get_games parser version as the frozen "
                    f"snapshot; got {binding.parser_name}@{binding.parser_version}, "
                    f"current {type(parser).__name__}@{parser.version}"
                )
            metadata = self.raw_store.get_metadata(binding.source_id, binding.raw_snapshot_id)
            body = self.raw_store.get_body(binding.source_id, binding.raw_snapshot_id)
            if metadata.content_hash != binding.content_hash:
                raise AnalystSemanticError(
                    f"rich snapshot {binding.raw_snapshot_id} content hash changed"
                )
            parsed = parser.parse(body)
            by_listing = {
                f"{_YANDEX_LISTING_PREFIX}{details.app_id}": details for details in parsed.games
            }
            for listing_id in binding.relevant_listing_ids:
                if listing_id not in target_listing_ids:
                    continue
                details = by_listing.get(listing_id)
                if details is None:
                    raise AnalystSemanticError(
                        f"rich snapshot {binding.raw_snapshot_id} no longer parses "
                        f"relevant listing {listing_id}"
                    )
                candidate = (binding.retrieved_at, binding.raw_snapshot_id, details)
                current = latest.get(listing_id)
                if current is None or (candidate[0], candidate[1]) > (current[0], current[1]):
                    latest[listing_id] = candidate
        return latest

    @staticmethod
    def _listing_row(
        listing_id: str,
        set_ids: tuple[str, ...],
        selected: tuple[datetime, str, GameDetails] | None,
        thesis: AnalystSemanticThesisDeclaration,
    ) -> AnalystSemanticListingRow:
        if selected is None:
            corpus = AnalystSemanticCorpus()
            source = None
        else:
            retrieved_at, raw_snapshot_id, details = selected
            corpus = AnalystSemanticCorpus(
                title=details.title,
                description=details.description,
                instruction=details.instruction,
                seo_description=details.seo_description,
                categories_names=details.categories_names,
                category_ids=details.category_ids,
                tag_ids=details.tag_ids,
            )
            if details.source_object_path is None:
                raise AnalystSemanticError(
                    f"get_games listing {listing_id} is missing source_object_path"
                )
            source = AnalystSemanticSourceReference(
                raw_snapshot_id=raw_snapshot_id,
                retrieved_at=_iso(retrieved_at),
                source_object_path=details.source_object_path,
                parser_name=YandexGetGamesParser.__name__,
                parser_version=YandexGetGamesParser.version,
            )

        fields = _searchable_fields(corpus)
        theme = _evaluate_dimension(fields, thesis.theme)
        mechanic = _evaluate_dimension(fields, thesis.mechanic)
        reward = (
            AnalystSemanticDimensionResult(status="not_configured")
            if thesis.reward_grammar is None
            else _evaluate_dimension(fields, thesis.reward_grammar)
        )
        external_app_id = _external_app_id(listing_id)
        return AnalystSemanticListingRow(
            platform_listing_id=listing_id,
            external_app_id=external_app_id,
            canonical_url=f"https://yandex.ru/games/app/{external_app_id}",
            comparable_set_ids=set_ids,
            source=source,
            corpus=corpus,
            theme_match=theme,
            mechanic_match=mechanic,
            reward_grammar_match=reward,
            directness=_directness(theme.status, mechanic.status),
        )


def validate_analyst_semantic_enrichment(
    report: AnalystSemanticEnrichmentReport,
) -> AnalystSemanticEnrichmentReport:
    validated = AnalystSemanticEnrichmentReport.model_validate(report.model_dump())
    payload = AnalystSemanticEnrichmentPayload.model_validate(
        validated.model_dump(exclude={"content_hash"})
    )
    if validated.content_hash != _payload_hash(payload):
        raise AnalystSemanticError("semantic enrichment content_hash does not match content")
    return validated


def write_analyst_semantic_csv(report: AnalystSemanticEnrichmentReport, path: Path) -> None:
    report = validate_analyst_semantic_enrichment(report)
    fieldnames = [
        "platform_listing_id",
        "external_app_id",
        "canonical_url",
        "comparable_set_ids",
        "directness",
        "theme_match",
        "mechanic_match",
        "reward_grammar_match",
        "matched_theme_terms",
        "matched_mechanic_terms",
        "matched_reward_terms",
        "title",
        "description",
        "instruction",
        "seo_description",
        "categories_names",
        "category_ids",
        "tag_ids",
        "evidence_snippets",
        "raw_snapshot_id",
        "source_object_path",
    ]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = path.open("x", encoding="utf-8", newline="")
    except FileExistsError as exc:
        raise AnalystSemanticError(f"semantic CSV already exists: {path}") from exc
    except OSError as exc:
        raise AnalystSemanticError(str(exc)) from exc

    with handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in report.listings:
            snippets = (
                row.theme_match.evidence_snippets
                + row.mechanic_match.evidence_snippets
                + row.reward_grammar_match.evidence_snippets
            )
            writer.writerow(
                {
                    "platform_listing_id": row.platform_listing_id,
                    "external_app_id": row.external_app_id,
                    "canonical_url": row.canonical_url,
                    "comparable_set_ids": "|".join(row.comparable_set_ids),
                    "directness": row.directness,
                    "theme_match": row.theme_match.status,
                    "mechanic_match": row.mechanic_match.status,
                    "reward_grammar_match": row.reward_grammar_match.status,
                    "matched_theme_terms": "|".join(row.theme_match.matched_terms),
                    "matched_mechanic_terms": "|".join(row.mechanic_match.matched_terms),
                    "matched_reward_terms": "|".join(row.reward_grammar_match.matched_terms),
                    "title": row.corpus.title,
                    "description": row.corpus.description,
                    "instruction": row.corpus.instruction,
                    "seo_description": row.corpus.seo_description,
                    "categories_names": _json_csv(row.corpus.categories_names),
                    "category_ids": _json_csv(row.corpus.category_ids),
                    "tag_ids": _json_csv(row.corpus.tag_ids),
                    "evidence_snippets": _json_csv(
                        tuple(item.model_dump(mode="json") for item in snippets)
                    ),
                    "raw_snapshot_id": None if row.source is None else row.source.raw_snapshot_id,
                    "source_object_path": (
                        None if row.source is None else row.source.source_object_path
                    ),
                }
            )


def _target_listings(
    snapshot: AnalystSnapshotReport,
    target_set_ids: tuple[str, ...],
) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    available = {item.set_id for item in snapshot.comparable_sets}
    if target_set_ids:
        missing = [set_id for set_id in target_set_ids if set_id not in available]
        if missing:
            raise AnalystSemanticError(
                "semantic thesis references comparable sets outside the snapshot: "
                + ", ".join(missing)
            )
        selected = set(target_set_ids)
    else:
        selected = available

    listing_order: list[str] = []
    memberships: dict[str, list[str]] = {}
    for comparable in snapshot.comparable_sets:
        if comparable.set_id not in selected:
            continue
        for listing_id in comparable.member_listing_ids:
            if listing_id not in memberships:
                listing_order.append(listing_id)
                memberships[listing_id] = []
            memberships[listing_id].append(comparable.set_id)
    if not listing_order:
        raise AnalystSemanticError("semantic thesis resolved to no comparable listings")
    return tuple(listing_order), {
        listing_id: tuple(set_ids) for listing_id, set_ids in memberships.items()
    }


def _searchable_fields(corpus: AnalystSemanticCorpus) -> dict[SemanticTextField, str]:
    values: dict[SemanticTextField, str] = {}
    for field in _TEXT_FIELDS:
        if field == "categories_names":
            value = " | ".join(corpus.categories_names)
        else:
            raw = getattr(corpus, field)
            value = raw if isinstance(raw, str) else ""
        cleaned = _clean_display_text(value)
        if cleaned:
            values[field] = cleaned
    return values


def _evaluate_dimension(
    fields: dict[SemanticTextField, str],
    rule: AnalystSemanticRule,
) -> AnalystSemanticDimensionResult:
    if not fields:
        return AnalystSemanticDimensionResult(status="unknown")

    matched_terms: list[str] = []
    snippets: list[AnalystSemanticEvidenceSnippet] = []
    for term in rule.terms:
        normalized_term = _normalize_text(term)
        for field, display_text in fields.items():
            normalized_field = display_text.casefold()
            position = normalized_field.find(normalized_term)
            if position < 0:
                continue
            matched_terms.append(term)
            snippets.append(
                AnalystSemanticEvidenceSnippet(
                    field=field,
                    term=term,
                    snippet=_snippet(display_text, position, len(normalized_term)),
                )
            )
            break

    if not matched_terms:
        return AnalystSemanticDimensionResult(status="no_match")
    return AnalystSemanticDimensionResult(
        status="match",
        matched_terms=_ordered_unique(matched_terms),
        evidence_snippets=tuple(snippets[:8]),
    )


def _directness(
    theme: SemanticMatchStatus,
    mechanic: SemanticMatchStatus,
) -> SemanticDirectness:
    if theme == "unknown" or mechanic == "unknown":
        return "insufficient_evidence"
    if theme == "match" and mechanic == "match":
        return "direct_candidate"
    if theme == "match" or mechanic == "match":
        return "adjacent_candidate"
    return "noise_candidate"


def _clean_display_text(value: str) -> str:
    unescaped = html_lib.unescape(value)
    without_tags = _TAG_RE.sub(" ", unescaped)
    return _WHITESPACE_RE.sub(" ", without_tags).strip()


def _normalize_text(value: str) -> str:
    return _clean_display_text(value).casefold()


def _snippet(value: str, position: int, term_length: int) -> str:
    start = max(0, position - 80)
    end = min(len(value), position + term_length + 120)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(value) else ""
    return prefix + value[start:end].strip() + suffix


def _external_app_id(listing_id: str) -> str:
    if not listing_id.startswith(_YANDEX_LISTING_PREFIX):
        raise AnalystSemanticError(f"unsupported comparable listing identity: {listing_id}")
    external = listing_id.removeprefix(_YANDEX_LISTING_PREFIX)
    if not external:
        raise AnalystSemanticError("Yandex listing identity has empty external app ID")
    return external


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return tuple(result)


def _iso(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AnalystSemanticError("semantic provenance timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _payload_hash(payload: AnalystSemanticEnrichmentPayload) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _json_csv(value: Sequence[object]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
