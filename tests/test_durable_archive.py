from __future__ import annotations

import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from yandex_analytics_reaper.durable_archive import (
    DurableArchiveError,
    DurableArchiveRequest,
    ExpectedArtifactIdentity,
    ReleaseBinding,
    WorkflowArtifactSource,
    build_archive_manifest,
    extract_verified_member,
    load_archive_manifest,
    validate_request_catalog,
    verify_archive,
    write_manifest_create_only,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_zip(path: Path, members: dict[str, bytes]) -> None:
    with ZipFile(path, mode="w", compression=ZIP_DEFLATED) as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def _request(artifact: Path) -> DurableArchiveRequest:
    return DurableArchiveRequest.model_validate(
        {
            "archive_id": "trend-mechanics-round2-2026-09-13",
            "source": {
                "workflow_run_id": 34765905886,
                "workflow_artifact_id": 10320791721,
                "workflow_artifact_name": "trend-mechanics-sweep-2026-09-13",
                "artifact_created_at": "2026-09-13T15:36:12Z",
                "artifact_expires_at": "2026-10-13T15:36:11Z",
                "source_commit_sha": "4bf9ae8fa469b4a2c9895ad7c20d9c888ddca0c4",
                "source_branch": "research/trend-mechanics-sweep-2026-09-13",
            },
            "expected": {
                "sha256": _sha256(artifact),
                "size_bytes": artifact.stat().st_size,
            },
            "release": {
                "tag": "evidence-2026-09-13-trend-mechanics-r2",
                "asset_name": "trend-mechanics-round2-2026-09-13.actions.zip",
                "manifest_asset_name": "trend-mechanics-round2-2026-09-13.manifest.json",
                "checksum_asset_name": "trend-mechanics-round2-2026-09-13.sha256",
            },
        }
    )


def _write_request(path: Path, request: DurableArchiveRequest) -> None:
    path.write_text(request.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _second_request(request: DurableArchiveRequest) -> DurableArchiveRequest:
    return request.model_copy(
        update={
            "archive_id": "trend-mechanics-round3-2026-09-13",
            "source": WorkflowArtifactSource(
                workflow_run_id=request.source.workflow_run_id + 1,
                workflow_artifact_id=request.source.workflow_artifact_id + 1,
                workflow_artifact_name=request.source.workflow_artifact_name,
                artifact_created_at=request.source.artifact_created_at,
                artifact_expires_at=request.source.artifact_expires_at,
                source_commit_sha=request.source.source_commit_sha,
                source_branch=request.source.source_branch,
            ),
            "release": ReleaseBinding(
                tag="evidence-2026-09-13-trend-mechanics-r3",
                asset_name="trend-mechanics-round3-2026-09-13.actions.zip",
                manifest_asset_name="trend-mechanics-round3-2026-09-13.manifest.json",
                checksum_asset_name="trend-mechanics-round3-2026-09-13.sha256",
            ),
        }
    )


def test_build_and_verify_manifest_binds_wrapper_and_members(tmp_path: Path) -> None:
    artifact = tmp_path / "actions.zip"
    _write_zip(
        artifact,
        {
            "trend-mechanics-result.json": b'{"ok":true}\n',
            "artifacts/exports/experiment/run.zip": b"immutable experiment bytes",
        },
    )

    manifest = build_archive_manifest(_request(artifact), artifact)

    assert manifest.artifact.sha256 == _sha256(artifact)
    assert [member.path for member in manifest.members] == [
        "artifacts/exports/experiment/run.zip",
        "trend-mechanics-result.json",
    ]
    assert manifest.members[0].sha256 == hashlib.sha256(b"immutable experiment bytes").hexdigest()
    assert verify_archive(manifest, artifact).status == "pass"


def test_build_rejects_download_that_disagrees_with_actions_identity(tmp_path: Path) -> None:
    artifact = tmp_path / "actions.zip"
    _write_zip(artifact, {"result.json": b"original"})
    request = _request(artifact)
    artifact.write_bytes(artifact.read_bytes() + b"tamper")

    with pytest.raises(DurableArchiveError, match="identity disagrees"):
        build_archive_manifest(request, artifact)


def test_verify_rejects_manifest_member_drift(tmp_path: Path) -> None:
    artifact = tmp_path / "actions.zip"
    _write_zip(artifact, {"result.json": b"original"})
    manifest = build_archive_manifest(_request(artifact), artifact)
    changed_member = manifest.members[0].model_copy(update={"sha256": "0" * 64})
    changed = manifest.model_copy(update={"members": (changed_member,)})

    with pytest.raises(DurableArchiveError, match="manifest disagrees"):
        verify_archive(changed, artifact)


def test_verify_rejects_manifest_that_does_not_match_committed_request(tmp_path: Path) -> None:
    artifact = tmp_path / "actions.zip"
    _write_zip(artifact, {"result.json": b"original"})
    request = _request(artifact)
    manifest = build_archive_manifest(request, artifact)
    other_request = _second_request(request)

    with pytest.raises(DurableArchiveError, match="archive_id disagrees"):
        verify_archive(manifest, artifact, request=other_request)


def test_extract_verified_member_outputs_exact_bound_bytes(tmp_path: Path) -> None:
    artifact = tmp_path / "actions.zip"
    payload = b"prior experiment zip bytes"
    member_path = "artifacts/exports/example/prior.zip"
    _write_zip(artifact, {member_path: payload})
    manifest = build_archive_manifest(_request(artifact), artifact)
    output = tmp_path / "prior.zip"

    member = extract_verified_member(
        manifest,
        artifact,
        member_path=member_path,
        output_path=output,
    )

    assert output.read_bytes() == payload
    assert member.sha256 == hashlib.sha256(payload).hexdigest()


def test_build_rejects_unsafe_zip_member_path(tmp_path: Path) -> None:
    artifact = tmp_path / "actions.zip"
    _write_zip(artifact, {"../escape.json": b"bad"})

    with pytest.raises(DurableArchiveError, match="unsafe ZIP member path"):
        build_archive_manifest(_request(artifact), artifact)


def test_build_rejects_duplicate_zip_member_path(tmp_path: Path) -> None:
    artifact = tmp_path / "actions.zip"
    with ZipFile(artifact, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("result.json", b"first")
        with pytest.warns(UserWarning, match="Duplicate name"):
            archive.writestr("result.json", b"second")

    with pytest.raises(DurableArchiveError, match="duplicate member path"):
        build_archive_manifest(_request(artifact), artifact)


def test_catalog_accepts_unique_requests(tmp_path: Path) -> None:
    artifact = tmp_path / "actions.zip"
    _write_zip(artifact, {"result.json": b"original"})
    first = _request(artifact)
    second = _second_request(first)
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    _write_request(first_path, first)
    _write_request(second_path, second)

    result = validate_request_catalog((first_path, second_path))

    assert result.status == "pass"
    assert result.request_count == 2


@pytest.mark.parametrize("collision", ["archive_id", "release_tag", "artifact_id"])
def test_catalog_rejects_identity_collisions(tmp_path: Path, collision: str) -> None:
    artifact = tmp_path / "actions.zip"
    _write_zip(artifact, {"result.json": b"original"})
    first = _request(artifact)
    second = _second_request(first)

    if collision == "archive_id":
        second = second.model_copy(update={"archive_id": first.archive_id})
    elif collision == "release_tag":
        second = second.model_copy(
            update={
                "release": second.release.model_copy(update={"tag": first.release.tag}),
            }
        )
    else:
        second = second.model_copy(
            update={
                "source": second.source.model_copy(
                    update={"workflow_artifact_id": first.source.workflow_artifact_id}
                ),
            }
        )

    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    _write_request(first_path, first)
    _write_request(second_path, second)

    with pytest.raises(DurableArchiveError, match="duplicate"):
        validate_request_catalog((first_path, second_path))


def test_create_only_manifest_allows_same_identity_but_rejects_replacement(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "actions.zip"
    _write_zip(artifact, {"result.json": b"original"})
    manifest = build_archive_manifest(_request(artifact), artifact)
    output = tmp_path / "manifest.json"

    write_manifest_create_only(manifest, output)
    write_manifest_create_only(manifest, output)
    assert load_archive_manifest(output) == manifest

    changed = manifest.model_copy(
        update={
            "artifact": ExpectedArtifactIdentity(sha256="f" * 64, size_bytes=1),
        }
    )
    with pytest.raises(DurableArchiveError, match="refusing to replace"):
        write_manifest_create_only(changed, output)
