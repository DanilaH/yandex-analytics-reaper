from __future__ import annotations

import hashlib
import io
import json
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol, Self
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from yandex_analytics_reaper.ingestion import RichMetadataCollectionResult
from yandex_analytics_reaper.sources.yandex import GameDetails, YandexGetGamesParser
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, RawSnapshotMetadata

LISTING_OBSERVATION_SET_SPEC_VERSION: Literal["listing-observation-set-v1"] = (
    "listing-observation-set-v1"
)
LISTING_OBSERVATION_REPORT_SPEC_VERSION: Literal["listing-observation-report-v1"] = (
    "listing-observation-report-v1"
)
LISTING_OBSERVATION_ARTIFACT_SPEC_VERSION: Literal["listing-observation-artifact-v1"] = (
    "listing-observation-artifact-v1"
)

_ID_PATTERN = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
_REQUIRED_MEMBERS = (
    "input/declaration.json",
    "reports/observation.json",
    "raw/metadata.json",
    "raw/body.bin",
    "artifact-manifest.json",
)
_PAYLOAD_MEMBERS = _REQUIRED_MEMBERS[:-1]
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


class ListingObservationError(ValueError):
    """Exact-ID evidence could not be accepted without weakening provenance semantics."""


class ListingObservationSetDeclaration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["listing-observation-set-v1"] = LISTING_OBSERVATION_SET_SPEC_VERSION
    observation_set_id: str = Field(pattern=_ID_PATTERN, max_length=80)
    observation_set_version: int = Field(ge=1)
    app_ids: tuple[int, ...] = Field(min_length=1, max_length=100)
    source_surface: Literal["catalogue.get_games"] = "catalogue.get_games"

    @field_validator("app_ids")
    @classmethod
    def validate_app_ids(cls, values: tuple[int, ...]) -> tuple[int, ...]:
        if any(value <= 0 for value in values):
            raise ValueError("app_ids must contain only positive integers")
        if len(set(values)) != len(values):
            raise ValueError("app_ids must be unique and declaration order must be explicit")
        return values


class PointListingObservation(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    app_id: int = Field(gt=0)
    title: str | None = None
    developer_id: str | int | None = None
    developer_name: str | None = None
    category_ids: tuple[int, ...] = ()
    category_names: tuple[str, ...] = ()
    tag_ids: tuple[int, ...] = ()
    player_rating: float | None = None
    rating_count: int | None = Field(default=None, ge=0)
    yandex_rating: int | None = None
    first_published: int | None = None
    min_load_time: float | None = None
    description: str | None = None
    instruction: str | None = None
    seo_description: str | None = None
    languages: tuple[str, ...] | None = None
    platforms: tuple[str, ...] | None = None
    orientation: str | None = None
    cloud_save: bool | None = None
    leaderboards: bool | None = None
    purchases_enabled: bool | None = None
    has_products: bool | None = None


class ListingObservationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["listing-observation-report-v1"] = LISTING_OBSERVATION_REPORT_SPEC_VERSION
    provenance_channel: Literal["point_observed"] = "point_observed"
    observation_set_id: str = Field(pattern=_ID_PATTERN, max_length=80)
    observation_set_version: int = Field(ge=1)
    declaration_content_hash: str
    requested_app_ids: tuple[int, ...]
    returned_app_ids: tuple[int, ...]
    missing_app_ids: tuple[int, ...]
    unexpected_app_ids: tuple[int, ...]
    source_id: str
    source_request_key: Literal["catalogue.get_games"]
    source_snapshot_id: str
    source_content_hash: str
    observed_at: AwareDatetime
    parser_name: Literal["YandexGetGamesParser"] = "YandexGetGamesParser"
    parser_version: str
    listings: tuple[PointListingObservation, ...]

    @field_validator("declaration_content_hash", "source_content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value

    @model_validator(mode="after")
    def validate_identity_sets(self) -> Self:
        requested = self.requested_app_ids
        returned = self.returned_app_ids
        missing = self.missing_app_ids
        unexpected = self.unexpected_app_ids
        if len(set(requested)) != len(requested):
            raise ValueError("requested_app_ids must be unique")
        if len(set(returned)) != len(returned):
            raise ValueError("returned_app_ids must be unique")
        if tuple(item.app_id for item in self.listings) != returned:
            raise ValueError("listing order must equal returned_app_ids order")
        requested_set = set(requested)
        returned_set = set(returned)
        if tuple(item for item in requested if item not in returned_set) != missing:
            raise ValueError(
                "missing_app_ids must be declaration-ordered requested IDs not returned"
            )
        if tuple(item for item in returned if item not in requested_set) != unexpected:
            raise ValueError("unexpected_app_ids must be returned IDs outside the declaration")
        return self


class ObservationArtifactMember(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    size: int = Field(ge=0)
    sha256: str

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or "\\" in value or value != path.as_posix():
            raise ValueError("artifact member path must be a normalized safe relative POSIX path")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value


class ListingObservationArtifactManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    spec_version: Literal["listing-observation-artifact-v1"] = (
        LISTING_OBSERVATION_ARTIFACT_SPEC_VERSION
    )
    observation_set_id: str = Field(pattern=_ID_PATTERN, max_length=80)
    observation_set_version: int = Field(ge=1)
    declaration_content_hash: str
    source_snapshot_id: str
    source_content_hash: str
    members: tuple[ObservationArtifactMember, ...]
    content_hash: str

    @field_validator("declaration_content_hash", "source_content_hash", "content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value

    @model_validator(mode="after")
    def validate_manifest(self) -> Self:
        paths = tuple(item.path for item in self.members)
        if paths != _PAYLOAD_MEMBERS:
            raise ValueError("artifact manifest members must use the canonical member order")
        expected = _hash_json_value(self.model_dump(mode="json", exclude={"content_hash"}))
        if self.content_hash != expected:
            raise ValueError("artifact manifest content_hash does not match manifest content")
        return self


class ListingObservationArtifactVerification(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["pass"] = "pass"
    artifact_sha256: str
    manifest_content_hash: str
    observation_set_id: str
    observation_set_version: int
    source_snapshot_id: str
    requested_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)

    @field_validator("artifact_sha256", "manifest_content_hash")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        _require_sha256(value)
        return value


class RichMetadataCollectorProtocol(Protocol):
    def collect(self, app_ids: Sequence[int]) -> RichMetadataCollectionResult: ...


class ListingObservationArtifactCollector:
    """Collect one explicit known-ID cohort and freeze it into a self-contained artifact."""

    def __init__(
        self,
        *,
        rich_collector: RichMetadataCollectorProtocol,
        raw_store: FilesystemRawSnapshotStore,
    ) -> None:
        self.rich_collector = rich_collector
        self.raw_store = raw_store

    def collect(
        self,
        declaration: ListingObservationSetDeclaration,
        artifact_path: Path,
    ) -> ListingObservationArtifactVerification:
        declaration = ListingObservationSetDeclaration.model_validate(declaration.model_dump())
        if artifact_path.exists():
            raise ListingObservationError(
                f"refusing to overwrite existing observation artifact: {artifact_path}"
            )
        result = self.rich_collector.collect(declaration.app_ids)
        metadata = result.raw_snapshot
        body = self.raw_store.get_body(metadata.source_id, metadata.id)
        metadata_bytes = _read_raw_metadata_bytes(self.raw_store, metadata)
        report = build_listing_observation_report(declaration, metadata, body)
        write_listing_observation_artifact(
            artifact_path,
            declaration=declaration,
            report=report,
            raw_metadata_bytes=metadata_bytes,
            raw_body=body,
        )
        return verify_listing_observation_artifact(artifact_path)


def build_listing_observation_report(
    declaration: ListingObservationSetDeclaration,
    metadata: RawSnapshotMetadata,
    body: bytes,
) -> ListingObservationReport:
    declaration = ListingObservationSetDeclaration.model_validate(declaration.model_dump())
    metadata = RawSnapshotMetadata.model_validate(metadata.model_dump())
    if metadata.source_id != "yandex_public":
        raise ListingObservationError("point observation requires source_id=yandex_public")
    if metadata.request_key != declaration.source_surface:
        raise ListingObservationError("raw request_key does not match declared source surface")
    if metadata.method.upper() != "POST":
        raise ListingObservationError("catalogue.get_games point evidence must come from POST")
    if not 200 <= metadata.http_status < 300:
        raise ListingObservationError("non-success source response cannot become point evidence")
    if hashlib.sha256(body).hexdigest() != metadata.content_hash:
        raise ListingObservationError("raw body hash does not match raw snapshot metadata")
    _validate_request_context(declaration, metadata)

    parser = YandexGetGamesParser()
    try:
        parsed = parser.parse(body)
    except ValueError as exc:
        raise ListingObservationError(f"get_games replay failed: {exc}") from exc

    parsed_ids = tuple(game.app_id for game in parsed.games)
    if len(set(parsed_ids)) != len(parsed_ids):
        raise ListingObservationError("get_games response contains duplicate app IDs")

    requested_set = set(declaration.app_ids)
    unexpected = tuple(app_id for app_id in parsed_ids if app_id not in requested_set)
    if unexpected:
        joined = ", ".join(str(value) for value in unexpected)
        raise ListingObservationError(f"get_games returned undeclared app IDs: {joined}")

    by_id = {game.app_id: game for game in parsed.games}
    returned = tuple(app_id for app_id in declaration.app_ids if app_id in by_id)
    missing = tuple(app_id for app_id in declaration.app_ids if app_id not in by_id)
    listings = tuple(_listing_observation(by_id[app_id]) for app_id in returned)

    return ListingObservationReport(
        observation_set_id=declaration.observation_set_id,
        observation_set_version=declaration.observation_set_version,
        declaration_content_hash=_sha256_bytes(_canonical_model_bytes(declaration)),
        requested_app_ids=declaration.app_ids,
        returned_app_ids=returned,
        missing_app_ids=missing,
        unexpected_app_ids=(),
        source_id=metadata.source_id,
        source_request_key="catalogue.get_games",
        source_snapshot_id=metadata.id,
        source_content_hash=metadata.content_hash,
        observed_at=metadata.retrieved_at,
        parser_version=parser.version,
        listings=listings,
    )


def write_listing_observation_artifact(
    artifact_path: Path,
    *,
    declaration: ListingObservationSetDeclaration,
    report: ListingObservationReport,
    raw_metadata_bytes: bytes,
    raw_body: bytes,
) -> ListingObservationArtifactManifest:
    declaration_bytes = _canonical_model_bytes(declaration)
    report_bytes = _canonical_model_bytes(report)
    metadata = _load_raw_metadata(raw_metadata_bytes)

    if report.declaration_content_hash != _sha256_bytes(declaration_bytes):
        raise ListingObservationError("report declaration hash does not match declaration bytes")
    if metadata.id != report.source_snapshot_id:
        raise ListingObservationError("raw metadata snapshot ID does not match observation report")
    if metadata.content_hash != report.source_content_hash:
        raise ListingObservationError("raw metadata content hash does not match observation report")
    if _sha256_bytes(raw_body) != metadata.content_hash:
        raise ListingObservationError("raw body does not match packaged raw metadata")

    payloads: dict[str, bytes] = {
        "input/declaration.json": declaration_bytes,
        "reports/observation.json": report_bytes,
        "raw/metadata.json": raw_metadata_bytes,
        "raw/body.bin": raw_body,
    }
    members = tuple(
        ObservationArtifactMember(
            path=path,
            size=len(payloads[path]),
            sha256=_sha256_bytes(payloads[path]),
        )
        for path in _PAYLOAD_MEMBERS
    )
    manifest_payload: dict[str, object] = {
        "spec_version": LISTING_OBSERVATION_ARTIFACT_SPEC_VERSION,
        "observation_set_id": declaration.observation_set_id,
        "observation_set_version": declaration.observation_set_version,
        "declaration_content_hash": report.declaration_content_hash,
        "source_snapshot_id": report.source_snapshot_id,
        "source_content_hash": report.source_content_hash,
        "members": [item.model_dump(mode="json") for item in members],
    }
    manifest = ListingObservationArtifactManifest.model_validate(
        {**manifest_payload, "content_hash": _hash_json_value(manifest_payload)}
    )
    manifest_bytes = _canonical_model_bytes(manifest)

    archive_bytes = _zip_bytes((*payloads.items(), ("artifact-manifest.json", manifest_bytes)))
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with artifact_path.open("xb") as handle:
            handle.write(archive_bytes)
    except FileExistsError as exc:
        raise ListingObservationError(
            f"refusing to overwrite existing observation artifact: {artifact_path}"
        ) from exc
    except OSError as exc:
        raise ListingObservationError(str(exc)) from exc
    return manifest


def verify_listing_observation_artifact(
    artifact_path: Path,
) -> ListingObservationArtifactVerification:
    try:
        with ZipFile(artifact_path, mode="r") as archive:
            infos = archive.infolist()
            names = tuple(info.filename for info in infos)
            if len(names) != len(set(names)):
                raise ListingObservationError("observation artifact contains duplicate ZIP members")
            if names != _REQUIRED_MEMBERS:
                raise ListingObservationError(
                    "observation artifact must contain only the canonical members "
                    "in canonical order"
                )
            for name in names:
                _validate_member_path(name)
            declaration_bytes = archive.read("input/declaration.json")
            report_bytes = archive.read("reports/observation.json")
            metadata_bytes = archive.read("raw/metadata.json")
            body = archive.read("raw/body.bin")
            manifest_bytes = archive.read("artifact-manifest.json")
    except ListingObservationError:
        raise
    except (BadZipFile, OSError, KeyError) as exc:
        raise ListingObservationError(f"cannot read observation artifact: {exc}") from exc

    try:
        declaration = ListingObservationSetDeclaration.model_validate_json(declaration_bytes)
        report = ListingObservationReport.model_validate_json(report_bytes)
        metadata = RawSnapshotMetadata.model_validate_json(metadata_bytes)
        manifest = ListingObservationArtifactManifest.model_validate_json(manifest_bytes)
    except ValidationError as exc:
        raise ListingObservationError(
            f"observation artifact model validation failed: {exc}"
        ) from exc

    payloads = {
        "input/declaration.json": declaration_bytes,
        "reports/observation.json": report_bytes,
        "raw/metadata.json": metadata_bytes,
        "raw/body.bin": body,
    }
    for member in manifest.members:
        payload = payloads[member.path]
        if len(payload) != member.size or _sha256_bytes(payload) != member.sha256:
            raise ListingObservationError(f"artifact member hash/size mismatch: {member.path}")

    declaration_hash = _sha256_bytes(_canonical_model_bytes(declaration))
    if manifest.declaration_content_hash != declaration_hash:
        raise ListingObservationError("manifest declaration hash does not match declaration")
    if report.declaration_content_hash != declaration_hash:
        raise ListingObservationError("report declaration hash does not match declaration")
    declaration_identity = (
        declaration.observation_set_id,
        declaration.observation_set_version,
    )
    if (
        manifest.observation_set_id,
        manifest.observation_set_version,
    ) != declaration_identity:
        raise ListingObservationError(
            "manifest observation-set identity does not match declaration"
        )
    if (
        report.observation_set_id,
        report.observation_set_version,
    ) != declaration_identity:
        raise ListingObservationError("report observation-set identity does not match declaration")
    if manifest.source_snapshot_id != metadata.id:
        raise ListingObservationError("manifest source snapshot does not match raw metadata")
    if manifest.source_content_hash != metadata.content_hash:
        raise ListingObservationError("manifest source content hash does not match raw metadata")
    if _sha256_bytes(body) != metadata.content_hash:
        raise ListingObservationError("packaged raw body does not match raw metadata content hash")

    rebuilt = build_listing_observation_report(declaration, metadata, body)
    if rebuilt != report:
        raise ListingObservationError(
            "offline replay does not reproduce packaged observation report"
        )

    return ListingObservationArtifactVerification(
        artifact_sha256=_sha256_file(artifact_path),
        manifest_content_hash=manifest.content_hash,
        observation_set_id=declaration.observation_set_id,
        observation_set_version=declaration.observation_set_version,
        source_snapshot_id=metadata.id,
        requested_count=len(report.requested_app_ids),
        returned_count=len(report.returned_app_ids),
        missing_count=len(report.missing_app_ids),
    )


def _listing_observation(game: GameDetails) -> PointListingObservation:
    developer_id = game.developer.id if game.developer is not None else None
    developer_name = game.developer.name if game.developer is not None else None
    return PointListingObservation(
        app_id=game.app_id,
        title=game.title,
        developer_id=developer_id,
        developer_name=developer_name,
        category_ids=game.category_ids,
        category_names=game.categories_names,
        tag_ids=game.tag_ids,
        player_rating=game.player_rating,
        rating_count=game.rating_count,
        yandex_rating=game.yandex_rating,
        first_published=game.first_published,
        min_load_time=game.min_load_time,
        description=game.description,
        instruction=game.instruction,
        seo_description=game.seo_description,
        languages=game.languages,
        platforms=game.platforms,
        orientation=game.orientation,
        cloud_save=game.cloud_save,
        leaderboards=game.leaderboards,
        purchases_enabled=game.purchases_enabled,
        has_products=game.has_products,
    )


def _validate_request_context(
    declaration: ListingObservationSetDeclaration,
    metadata: RawSnapshotMetadata,
) -> None:
    raw_ids = metadata.request_context.get("app_ids")
    if not isinstance(raw_ids, list) or any(
        not isinstance(value, int) or isinstance(value, bool) for value in raw_ids
    ):
        raise ListingObservationError("raw request context does not contain valid app_ids")
    if tuple(raw_ids) != declaration.app_ids:
        raise ListingObservationError("raw request app_ids do not exactly match declaration order")
    if metadata.request_context.get("format") != "long":
        raise ListingObservationError("raw request context must prove format=long")


def _read_raw_metadata_bytes(
    raw_store: FilesystemRawSnapshotStore,
    metadata: RawSnapshotMetadata,
) -> bytes:
    root = raw_store.root.resolve()
    path = (raw_store.root / metadata.metadata_path).resolve()
    if not path.is_relative_to(root):
        raise ListingObservationError("raw metadata path escapes configured raw root")
    try:
        value = path.read_bytes()
    except OSError as exc:
        raise ListingObservationError(str(exc)) from exc
    replayed = _load_raw_metadata(value)
    if replayed != raw_store.get_metadata(metadata.source_id, metadata.id):
        raise ListingObservationError("raw metadata bytes do not match replayed snapshot metadata")
    return value


def _load_raw_metadata(value: bytes) -> RawSnapshotMetadata:
    try:
        return RawSnapshotMetadata.model_validate_json(value)
    except ValidationError as exc:
        raise ListingObservationError(f"raw metadata is invalid: {exc}") from exc


def _canonical_model_bytes(model: BaseModel) -> bytes:
    return _canonical_json_bytes(model.model_dump(mode="json"))


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _hash_json_value(value: object) -> str:
    return _sha256_bytes(_canonical_json_bytes(value))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise ListingObservationError(str(exc)) from exc
    return digest.hexdigest()


def _require_sha256(value: str) -> None:
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ValueError("expected lowercase SHA-256 hex digest")


def _validate_member_path(value: str) -> None:
    try:
        ObservationArtifactMember(path=value, size=0, sha256="0" * 64)
    except ValidationError as exc:
        raise ListingObservationError(f"unsafe artifact member path: {value}") from exc


def _zip_bytes(entries: Sequence[tuple[str, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
        for path, payload in entries:
            _validate_member_path(path)
            info = ZipInfo(path, date_time=_ZIP_TIMESTAMP)
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o600 << 16
            archive.writestr(info, payload, compress_type=ZIP_DEFLATED, compresslevel=9)
    return buffer.getvalue()
