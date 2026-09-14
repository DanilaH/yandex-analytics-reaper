from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from pydantic import ValidationError

from yandex_analytics_reaper.ingestion import RichMetadataCollectionResult
from yandex_analytics_reaper.point_observation import (
    ListingObservationArtifactCollector,
    ListingObservationError,
    ListingObservationSetDeclaration,
    build_listing_observation_report,
    verify_listing_observation_artifact,
    write_listing_observation_artifact,
)
from yandex_analytics_reaper.sources.capabilities import CollectedResponse
from yandex_analytics_reaper.storage import FilesystemRawSnapshotStore, RawSnapshotMetadata


def _body(*app_ids: int) -> bytes:
    games = []
    for index, app_id in enumerate(app_ids):
        games.append(
            {
                "appID": app_id,
                "title": f"Game {app_id}",
                "developer": {"id": index + 10, "name": f"Dev {index}"},
                "categoryIDs": [1, 2],
                "categoriesNames": ["Arcade"],
                "tagIDs": [5],
                "rating": 4.5,
                "ratingCount": 20 + index,
                "gqRating": 73 + index,
                "firstPublished": 1_789_000_000 + index,
                "minLoadTime": 1.25,
                "description": "Description",
                "instruction": "Tap",
                "seoDescription": "SEO",
                "features": {
                    "languages": ["ru"],
                    "platforms": ["desktop", "mobile"],
                    "orientation": "landscape",
                    "cloud_save": True,
                },
                "extraFeatures": {
                    "leaderboards": False,
                    "purchases": True,
                    "hasProducts": True,
                },
            }
        )
    return json.dumps({"games": games}, separators=(",", ":")).encode()


def _declaration(*app_ids: int) -> ListingObservationSetDeclaration:
    return ListingObservationSetDeclaration(
        observation_set_id="keycap-known-direct",
        observation_set_version=1,
        app_ids=app_ids,
    )


def _metadata(body: bytes, app_ids: tuple[int, ...]) -> RawSnapshotMetadata:
    return RawSnapshotMetadata(
        id="20260914T120000000000Z-aaaaaaaaaa",
        source_id="yandex_public",
        retrieved_at=datetime(2026, 9, 14, 12, 0, tzinfo=UTC),
        request_key="catalogue.get_games",
        method="POST",
        url="https://yandex.ru/games/api/catalogue/v2/get_games",
        request_context={"app_ids": list(app_ids), "format": "long"},
        content_path="raw/body.json",
        metadata_path="raw/metadata.json",
        content_hash=hashlib.sha256(body).hexdigest(),
        http_status=200,
        content_type="application/json",
    )


def test_declaration_rejects_duplicate_nonpositive_and_more_than_100_ids() -> None:
    with pytest.raises(ValidationError):
        _declaration(1, 1)
    with pytest.raises(ValidationError):
        _declaration(0)
    with pytest.raises(ValidationError):
        _declaration(*range(1, 102))


def test_report_preserves_declaration_order_and_explicit_missing_ids() -> None:
    declaration = _declaration(540402, 559445, 553722)
    body = _body(553722, 540402)
    report = build_listing_observation_report(
        declaration,
        _metadata(body, declaration.app_ids),
        body,
    )

    assert report.provenance_channel == "point_observed"
    assert report.requested_app_ids == (540402, 559445, 553722)
    assert report.returned_app_ids == (540402, 553722)
    assert report.missing_app_ids == (559445,)
    assert report.unexpected_app_ids == ()
    assert [item.app_id for item in report.listings] == [540402, 553722]
    assert report.listings[0].rating_count == 21
    assert report.listings[1].rating_count == 20


def test_report_fails_closed_on_unexpected_source_id() -> None:
    declaration = _declaration(540402)
    body = _body(540402, 999999)
    metadata = _metadata(body, declaration.app_ids)
    with pytest.raises(ListingObservationError, match="undeclared app IDs"):
        build_listing_observation_report(declaration, metadata, body)


def test_report_requires_exact_request_context_order() -> None:
    declaration = _declaration(540402, 553722)
    body = _body(540402, 553722)
    metadata = _metadata(body, (553722, 540402))
    with pytest.raises(ListingObservationError, match="exactly match declaration order"):
        build_listing_observation_report(declaration, metadata, body)


def test_artifact_roundtrip_is_offline_verifiable_and_create_only(tmp_path: Path) -> None:
    declaration = _declaration(540402, 559445, 553722)
    body = _body(540402, 553722)
    metadata = _metadata(body, declaration.app_ids)
    report = build_listing_observation_report(declaration, metadata, body)
    artifact = tmp_path / "keycap.zip"

    manifest = write_listing_observation_artifact(
        artifact,
        declaration=declaration,
        report=report,
        raw_metadata_bytes=metadata.model_dump_json(indent=2).encode(),
        raw_body=body,
    )
    verification = verify_listing_observation_artifact(artifact)

    assert manifest.observation_set_id == "keycap-known-direct"
    assert verification.status == "pass"
    assert verification.requested_count == 3
    assert verification.returned_count == 2
    assert verification.missing_count == 1
    assert len(verification.artifact_sha256) == 64

    with pytest.raises(ListingObservationError, match="refusing to overwrite"):
        write_listing_observation_artifact(
            artifact,
            declaration=declaration,
            report=report,
            raw_metadata_bytes=metadata.model_dump_json(indent=2).encode(),
            raw_body=body,
        )


def test_verifier_rejects_tampered_raw_body(tmp_path: Path) -> None:
    declaration = _declaration(540402)
    body = _body(540402)
    metadata = _metadata(body, declaration.app_ids)
    report = build_listing_observation_report(declaration, metadata, body)
    original = tmp_path / "original.zip"
    tampered = tmp_path / "tampered.zip"
    write_listing_observation_artifact(
        original,
        declaration=declaration,
        report=report,
        raw_metadata_bytes=metadata.model_dump_json(indent=2).encode(),
        raw_body=body,
    )

    with ZipFile(original, "r") as source, ZipFile(
        tampered, "w", compression=ZIP_DEFLATED
    ) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename == "raw/body.bin":
                payload += b"\n"
            target.writestr(info.filename, payload)

    with pytest.raises(ListingObservationError, match="hash/size mismatch"):
        verify_listing_observation_artifact(tampered)


class _PersistingFakeCollector:
    def __init__(self, store: FilesystemRawSnapshotStore, response: CollectedResponse) -> None:
        self.store = store
        self.response = response

    def collect(self, app_ids: tuple[int, ...]) -> RichMetadataCollectionResult:
        assert tuple(self.response.request_context["app_ids"]) == app_ids
        metadata = self.store.persist(self.response)
        return RichMetadataCollectionResult(
            raw_snapshot=metadata,
            parsed_listing_ids=tuple(f"yandex_games:{app_id}" for app_id in app_ids),
        )


def test_collector_packages_exact_persisted_raw_snapshot(tmp_path: Path) -> None:
    declaration = _declaration(540402, 553722)
    body = _body(540402, 553722)
    response = CollectedResponse(
        source_id="yandex_public",
        request_key="catalogue.get_games",
        method="POST",
        url="https://yandex.ru/games/api/catalogue/v2/get_games",
        status_code=200,
        headers={"content-type": "application/json"},
        body=body,
        retrieved_at=datetime(2026, 9, 14, 12, 30, tzinfo=UTC),
        request_context={"app_ids": list(declaration.app_ids), "format": "long"},
    )
    raw_store = FilesystemRawSnapshotStore(tmp_path / "raw")
    artifact = tmp_path / "observation.zip"

    verification = ListingObservationArtifactCollector(
        rich_collector=_PersistingFakeCollector(raw_store, response),
        raw_store=raw_store,
    ).collect(declaration, artifact)

    assert verification.status == "pass"
    assert verification.returned_count == 2
    with ZipFile(artifact, "r") as archive:
        assert archive.read("raw/body.bin") == body
        packaged_metadata = RawSnapshotMetadata.model_validate_json(
            archive.read("raw/metadata.json")
        )
    assert packaged_metadata.content_hash == hashlib.sha256(body).hexdigest()
