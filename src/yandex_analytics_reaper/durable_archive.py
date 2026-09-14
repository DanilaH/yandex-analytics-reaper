from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Literal
from zipfile import BadZipFile, ZipFile

from pydantic import BaseModel, ConfigDict, Field, field_validator

_MANIFEST_SPEC_VERSION = "durable-evidence-archive-v1"
_SHA256_LENGTH = 64
_COPY_CHUNK_SIZE = 1024 * 1024


class DurableArchiveError(ValueError):
    """Raised when durable evidence archive identity or integrity is invalid."""


class WorkflowArtifactSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_run_id: int = Field(gt=0)
    workflow_artifact_id: int = Field(gt=0)
    workflow_artifact_name: str = Field(min_length=1)
    artifact_created_at: datetime
    artifact_expires_at: datetime
    source_commit_sha: str = Field(min_length=40, max_length=40)
    source_branch: str = Field(min_length=1)

    @field_validator("artifact_created_at", "artifact_expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("artifact timestamps must be timezone-aware")
        return value

    @field_validator("source_commit_sha")
    @classmethod
    def validate_commit_sha(cls, value: str) -> str:
        normalized = value.lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("source_commit_sha must be a 40-character hexadecimal SHA")
        return normalized


class ExpectedArtifactIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    sha256: str = Field(min_length=_SHA256_LENGTH, max_length=_SHA256_LENGTH)
    size_bytes: int = Field(gt=0)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        return normalized


class ReleaseBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tag: str = Field(min_length=1)
    asset_name: str = Field(min_length=1)
    manifest_asset_name: str = Field(min_length=1)
    checksum_asset_name: str = Field(min_length=1)


class DurableArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    spec_version: Literal["durable-evidence-archive-request-v1"] = (
        "durable-evidence-archive-request-v1"
    )
    archive_id: str = Field(min_length=1)
    source: WorkflowArtifactSource
    expected: ExpectedArtifactIdentity
    release: ReleaseBinding


class ArchivedMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=_SHA256_LENGTH, max_length=_SHA256_LENGTH)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        normalized = value.lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("member sha256 must be a 64-character hexadecimal digest")
        return normalized


class DurableArchiveManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    spec_version: Literal["durable-evidence-archive-v1"] = "durable-evidence-archive-v1"
    archive_id: str
    source: WorkflowArtifactSource
    release: ReleaseBinding
    artifact: ExpectedArtifactIdentity
    members: tuple[ArchivedMember, ...]
    content_hash: str = Field(min_length=_SHA256_LENGTH, max_length=_SHA256_LENGTH)

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str) -> str:
        normalized = value.lower()
        if any(character not in "0123456789abcdef" for character in normalized):
            raise ValueError("content_hash must be a 64-character hexadecimal digest")
        return normalized


class DurableArchiveVerification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    archive_id: str
    artifact_sha256: str
    size_bytes: int
    member_count: int
    content_hash: str
    status: Literal["pass"] = "pass"


def load_archive_request(path: Path) -> DurableArchiveRequest:
    try:
        return DurableArchiveRequest.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise DurableArchiveError(f"cannot load durable archive request {path}: {exc}") from exc


def load_archive_manifest(path: Path) -> DurableArchiveManifest:
    try:
        return DurableArchiveManifest.model_validate_json(path.read_bytes())
    except (OSError, ValueError) as exc:
        raise DurableArchiveError(f"cannot load durable archive manifest {path}: {exc}") from exc


def build_archive_manifest(
    request: DurableArchiveRequest,
    artifact_path: Path,
) -> DurableArchiveManifest:
    artifact = _artifact_identity(artifact_path)
    if artifact != request.expected:
        raise DurableArchiveError(
            "downloaded artifact identity disagrees with request: "
            f"expected sha256={request.expected.sha256} size={request.expected.size_bytes}, "
            f"got sha256={artifact.sha256} size={artifact.size_bytes}"
        )

    members = _inventory_zip(artifact_path)
    without_hash = {
        "spec_version": _MANIFEST_SPEC_VERSION,
        "archive_id": request.archive_id,
        "source": request.source.model_dump(mode="json"),
        "release": request.release.model_dump(mode="json"),
        "artifact": artifact.model_dump(mode="json"),
        "members": [member.model_dump(mode="json") for member in members],
    }
    content_hash = _canonical_sha256(without_hash)
    return DurableArchiveManifest(
        archive_id=request.archive_id,
        source=request.source,
        release=request.release,
        artifact=artifact,
        members=members,
        content_hash=content_hash,
    )


def require_manifest_matches_request(
    request: DurableArchiveRequest,
    manifest: DurableArchiveManifest,
) -> None:
    if manifest.archive_id != request.archive_id:
        raise DurableArchiveError("manifest archive_id disagrees with committed request")
    if manifest.source != request.source:
        raise DurableArchiveError("manifest source provenance disagrees with committed request")
    if manifest.release != request.release:
        raise DurableArchiveError("manifest release binding disagrees with committed request")
    if manifest.artifact != request.expected:
        raise DurableArchiveError("manifest artifact identity disagrees with committed request")


def verify_archive(
    manifest: DurableArchiveManifest,
    artifact_path: Path,
    *,
    request: DurableArchiveRequest | None = None,
) -> DurableArchiveVerification:
    if request is not None:
        require_manifest_matches_request(request, manifest)
    rebuild_request = DurableArchiveRequest(
        archive_id=manifest.archive_id,
        source=manifest.source,
        expected=manifest.artifact,
        release=manifest.release,
    )
    rebuilt = build_archive_manifest(rebuild_request, artifact_path)
    if rebuilt != manifest:
        raise DurableArchiveError(
            "durable archive manifest disagrees with the artifact or canonical manifest identity"
        )
    return DurableArchiveVerification(
        archive_id=manifest.archive_id,
        artifact_sha256=manifest.artifact.sha256,
        size_bytes=manifest.artifact.size_bytes,
        member_count=len(manifest.members),
        content_hash=manifest.content_hash,
    )


def extract_verified_member(
    manifest: DurableArchiveManifest,
    artifact_path: Path,
    *,
    member_path: str,
    output_path: Path,
) -> ArchivedMember:
    verify_archive(manifest, artifact_path)
    member = next((item for item in manifest.members if item.path == member_path), None)
    if member is None:
        raise DurableArchiveError(f"member is not bound by manifest: {member_path}")
    _validate_member_path(member_path)

    try:
        with ZipFile(artifact_path, mode="r") as archive:
            info = archive.getinfo(member_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                dir=output_path.parent,
            )
            temporary_path = Path(temporary_name)
            try:
                digest = hashlib.sha256()
                written = 0
                with os.fdopen(fd, "wb") as target, archive.open(info, mode="r") as source:
                    while chunk := source.read(_COPY_CHUNK_SIZE):
                        target.write(chunk)
                        digest.update(chunk)
                        written += len(chunk)
                actual_sha256 = digest.hexdigest()
                if written != member.size_bytes or actual_sha256 != member.sha256:
                    raise DurableArchiveError(
                        f"member integrity mismatch for {member_path}: "
                        f"expected sha256={member.sha256} size={member.size_bytes}, "
                        f"got sha256={actual_sha256} size={written}"
                    )
                temporary_path.replace(output_path)
            except Exception:
                temporary_path.unlink(missing_ok=True)
                raise
    except (BadZipFile, KeyError, OSError) as exc:
        raise DurableArchiveError(f"cannot extract archived member {member_path}: {exc}") from exc
    return member


def write_manifest_create_only(manifest: DurableArchiveManifest, output_path: Path) -> None:
    payload = manifest.model_dump_json(indent=2) + "\n"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output_path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
    except FileExistsError:
        existing = load_archive_manifest(output_path)
        if existing != manifest:
            raise DurableArchiveError(
                f"refusing to replace different durable archive manifest: {output_path}"
            )
    except OSError as exc:
        raise DurableArchiveError(f"cannot write durable archive manifest {output_path}: {exc}") from exc


def checksum_line(manifest: DurableArchiveManifest) -> str:
    return f"{manifest.artifact.sha256}  {manifest.release.asset_name}\n"


def _artifact_identity(path: Path) -> ExpectedArtifactIdentity:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_COPY_CHUNK_SIZE):
                digest.update(chunk)
                size += len(chunk)
    except OSError as exc:
        raise DurableArchiveError(f"cannot read artifact {path}: {exc}") from exc
    if size <= 0:
        raise DurableArchiveError(f"artifact must not be empty: {path}")
    return ExpectedArtifactIdentity(sha256=digest.hexdigest(), size_bytes=size)


def _inventory_zip(path: Path) -> tuple[ArchivedMember, ...]:
    members: list[ArchivedMember] = []
    names: set[str] = set()
    try:
        with ZipFile(path, mode="r") as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                _validate_member_path(info.filename)
                if info.filename in names:
                    raise DurableArchiveError(
                        f"ZIP contains duplicate member path: {info.filename}"
                    )
                names.add(info.filename)
                digest = hashlib.sha256()
                size = 0
                with archive.open(info, mode="r") as source:
                    while chunk := source.read(_COPY_CHUNK_SIZE):
                        digest.update(chunk)
                        size += len(chunk)
                if size != info.file_size:
                    raise DurableArchiveError(
                        f"ZIP member size changed during replay: {info.filename}"
                    )
                members.append(
                    ArchivedMember(
                        path=info.filename,
                        size_bytes=size,
                        sha256=digest.hexdigest(),
                    )
                )
    except DurableArchiveError:
        raise
    except (BadZipFile, OSError) as exc:
        raise DurableArchiveError(f"artifact must be a readable ZIP: {path}: {exc}") from exc
    return tuple(sorted(members, key=lambda member: member.path))


def _validate_member_path(value: str) -> None:
    if "\\" in value:
        raise DurableArchiveError(f"ZIP member uses ambiguous backslash path: {value}")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise DurableArchiveError(f"unsafe ZIP member path: {value}")


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
