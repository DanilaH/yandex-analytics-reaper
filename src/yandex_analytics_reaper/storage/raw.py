from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from yandex_analytics_reaper.sources.capabilities import CollectedResponse

SENSITIVE_KEYS = {
    "authorization",
    "cookie",
    "set-cookie",
    "session_id",
    "csrf",
    "csrf-token",
    "x-csrf-token",
}
_SAFE_SOURCE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
_SNAPSHOT_ID = re.compile(r"^(\d{8})T\d{12}Z-[0-9a-f]{10}$")


class RawSnapshotMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    source_id: str
    retrieved_at: datetime
    request_key: str
    method: str
    url: str
    request_context: dict[str, Any]
    content_path: str
    metadata_path: str
    content_hash: str
    http_status: int
    content_type: str | None = None
    schema_hash: str | None = None


def _redact_value(value: object) -> Any:
    if isinstance(value, Mapping):
        return _redact_mapping(value)
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return [_redact_value(item) for item in value]
    return value


def _redact_mapping(value: Mapping[str, object]) -> dict[str, Any]:
    redacted: dict[str, Any] = {}
    for key, raw_value in value.items():
        lowered = key.lower()
        if lowered in SENSITIVE_KEYS or "token" in lowered or "secret" in lowered:
            redacted[key] = "<redacted>"
        else:
            redacted[key] = _redact_value(raw_value)
    return redacted


def _json_keypaths(value: object, prefix: str = "$") -> set[str]:
    paths: set[str] = set()
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}"
            paths.add(path)
            paths.update(_json_keypaths(child, path))
    elif isinstance(value, list):
        for child in value[:50]:
            paths.update(_json_keypaths(child, f"{prefix}[]"))
    return paths


def _schema_hash(body: bytes, content_type: str | None) -> str | None:
    if content_type is None or "json" not in content_type.lower():
        return None
    try:
        value = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    encoded = "\n".join(sorted(_json_keypaths(value))).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_source_id(source_id: str) -> str:
    if _SAFE_SOURCE_ID.fullmatch(source_id) is None:
        raise ValueError("source_id must contain only letters, digits, '.', '_' or '-'")
    return source_id


class FilesystemRawSnapshotStore:
    """Append-only raw response store with deterministic metadata/body replay."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def persist(self, response: CollectedResponse) -> RawSnapshotMetadata:
        source_id = _validate_source_id(response.source_id)
        retrieved = response.retrieved_at.astimezone(UTC)
        snapshot_id = f"{retrieved:%Y%m%dT%H%M%S%fZ}-{uuid4().hex[:10]}"
        folder = self.root / source_id / f"{retrieved:%Y/%m/%d}" / snapshot_id
        folder.mkdir(parents=True, exist_ok=False)

        content_type = response.headers.get("content-type")
        suffix = self._suffix(content_type)
        content_path = folder / f"body{suffix}"
        metadata_path = folder / "metadata.json"

        content_path.write_bytes(response.body)
        content_hash = hashlib.sha256(response.body).hexdigest()
        schema_hash = _schema_hash(response.body, content_type)

        metadata = RawSnapshotMetadata(
            id=snapshot_id,
            source_id=source_id,
            retrieved_at=retrieved,
            request_key=response.request_key,
            method=response.method,
            url=response.url,
            request_context=_redact_mapping(response.request_context),
            content_path=str(content_path.relative_to(self.root)),
            metadata_path=str(metadata_path.relative_to(self.root)),
            content_hash=content_hash,
            http_status=response.status_code,
            content_type=content_type,
            schema_hash=schema_hash,
        )
        metadata_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
        return metadata

    def get_metadata(self, source_id: str, snapshot_id: str) -> RawSnapshotMetadata:
        """Resolve a snapshot ID back to its immutable metadata without a database index."""

        source_id = _validate_source_id(source_id)
        date = self._snapshot_date(snapshot_id)
        metadata_path = (
            self.root
            / source_id
            / f"{date.year:04d}"
            / f"{date.month:02d}"
            / f"{date.day:02d}"
            / snapshot_id
            / "metadata.json"
        )
        if not metadata_path.is_file():
            raise FileNotFoundError(f"raw snapshot metadata not found: {source_id}/{snapshot_id}")

        metadata = RawSnapshotMetadata.model_validate_json(
            metadata_path.read_text(encoding="utf-8")
        )
        if metadata.id != snapshot_id or metadata.source_id != source_id:
            raise ValueError("raw snapshot metadata identity does not match requested snapshot")
        return metadata

    def get_body(self, source_id: str, snapshot_id: str) -> bytes:
        """Replay the exact stored body while rechecking path and content identity."""

        metadata = self.get_metadata(source_id, snapshot_id)
        root = self.root.resolve()
        content_path = (self.root / metadata.content_path).resolve()
        if not content_path.is_relative_to(root):
            raise ValueError("raw snapshot content path escapes the configured raw root")
        if not content_path.is_file():
            raise FileNotFoundError(f"raw snapshot body not found: {source_id}/{snapshot_id}")

        body = content_path.read_bytes()
        if hashlib.sha256(body).hexdigest() != metadata.content_hash:
            raise ValueError("raw snapshot body hash does not match persisted metadata")
        return body

    @staticmethod
    def _snapshot_date(snapshot_id: str) -> datetime:
        match = _SNAPSHOT_ID.fullmatch(snapshot_id)
        if match is None:
            raise ValueError("snapshot_id does not match the expected generated format")
        try:
            return datetime.strptime(match.group(1), "%Y%m%d").replace(tzinfo=UTC)
        except ValueError as exc:
            raise ValueError("snapshot_id contains an invalid UTC date") from exc

    @staticmethod
    def _suffix(content_type: str | None) -> str:
        if content_type and "json" in content_type.lower():
            return ".json"
        if content_type and "html" in content_type.lower():
            return ".html"
        return ".bin"
