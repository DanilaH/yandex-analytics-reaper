from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from typing import cast

from yandex_analytics_reaper.storage import RawSnapshotMetadata

from .models import FieldProfile, JsonValueType, SchemaProfile, SchemaProfileStatus


def profile_json_snapshot(metadata: RawSnapshotMetadata, body: bytes) -> SchemaProfile:
    """Profile exact JSON types/presence without source-specific coercion."""

    if hashlib.sha256(body).hexdigest() != metadata.content_hash:
        raise ValueError("raw body hash does not match snapshot metadata")

    try:
        value: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return SchemaProfile(
            raw_snapshot_id=metadata.id,
            source_id=metadata.source_id,
            request_key=metadata.request_key,
            retrieved_at=metadata.retrieved_at,
            schema_hash=metadata.schema_hash,
            status=SchemaProfileStatus.PARSE_FAILED,
            error=str(exc),
        )

    observed_types: dict[str, set[JsonValueType]] = defaultdict(set)
    object_instances: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    _visit(value, "$", observed_types, object_instances)

    profiles: list[FieldProfile] = []
    profiled_paths: set[str] = set()
    for parent_path, instances in object_instances.items():
        keys = sorted({key for instance in instances for key in instance})
        for key in keys:
            path = f"{parent_path}.{key}"
            present = sum(key in instance for instance in instances)
            parent_count = len(instances)
            profiles.append(
                FieldProfile(
                    path=path,
                    value_types=tuple(sorted(observed_types[path], key=str)),
                    present_count=present,
                    parent_count=parent_count,
                    presence_ratio=present / parent_count,
                )
            )
            profiled_paths.add(path)

    for path, types in sorted(observed_types.items()):
        if path == "$" or path in profiled_paths:
            continue
        profiles.append(
            FieldProfile(
                path=path,
                value_types=tuple(sorted(types, key=str)),
                present_count=1,
                parent_count=1,
                presence_ratio=1.0,
            )
        )

    profiles.sort(key=lambda item: item.path)
    return SchemaProfile(
        raw_snapshot_id=metadata.id,
        source_id=metadata.source_id,
        request_key=metadata.request_key,
        retrieved_at=metadata.retrieved_at,
        schema_hash=metadata.schema_hash,
        status=SchemaProfileStatus.PROFILED,
        root_type=_json_type(value),
        fields=tuple(profiles),
    )


def _visit(
    value: object,
    path: str,
    observed_types: dict[str, set[JsonValueType]],
    object_instances: dict[str, list[Mapping[str, object]]],
) -> None:
    observed_types[path].add(_json_type(value))
    if isinstance(value, dict):
        mapping = cast(dict[str, object], value)
        object_instances[path].append(mapping)
        for key, child in mapping.items():
            _visit(child, f"{path}.{key}", observed_types, object_instances)
    elif isinstance(value, list):
        for child in value:
            _visit(child, f"{path}[]", observed_types, object_instances)


def _json_type(value: object) -> JsonValueType:
    if value is None:
        return JsonValueType.NULL
    if isinstance(value, bool):
        return JsonValueType.BOOLEAN
    if isinstance(value, int):
        return JsonValueType.INTEGER
    if isinstance(value, float):
        return JsonValueType.NUMBER
    if isinstance(value, str):
        return JsonValueType.STRING
    if isinstance(value, dict):
        return JsonValueType.OBJECT
    if isinstance(value, list):
        return JsonValueType.ARRAY
    raise TypeError(f"unsupported JSON value type: {type(value).__name__}")
