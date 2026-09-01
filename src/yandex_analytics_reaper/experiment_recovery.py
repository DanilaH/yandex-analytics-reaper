from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from yandex_analytics_reaper.experiment_runtime import AnalystExperimentRunState

_WORKFLOW_VERSION: Literal["analyst-experiment-v1.2"] = "analyst-experiment-v1.2"


class ExperimentRecoveryError(RuntimeError):
    """Persisted experiment state cannot be resumed without weakening identity."""


@dataclass(frozen=True, slots=True)
class ResumePreflight:
    repository_root: Path
    workdir: Path
    artifact_path: Path
    state: AnalystExperimentRunState
    manifest_bytes: bytes


def load_resume_preflight(repository_root: Path, workdir: Path) -> ResumePreflight:
    """Validate durable path/state/manifest identity without performing source I/O."""
    root = repository_root.resolve()
    resolved = workdir.resolve()
    expected_root = (root / "artifacts" / "work").resolve()
    try:
        relative = resolved.relative_to(expected_root)
    except ValueError as exc:
        raise ExperimentRecoveryError(
            "resume workdir must live directly under artifacts/work/<experiment>/<run>"
        ) from exc
    if len(relative.parts) != 2:
        raise ExperimentRecoveryError(
            "resume workdir must be artifacts/work/<experiment>/<run>"
        )
    if not resolved.is_dir():
        raise ExperimentRecoveryError(f"resume workdir does not exist: {resolved}")

    state_path = resolved / "run-state.json"
    manifest_path = resolved / "input" / "manifest.json"
    try:
        state = AnalystExperimentRunState.model_validate_json(
            state_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise ExperimentRecoveryError("run-state.json is missing or invalid") from exc
    if state.workflow_version != _WORKFLOW_VERSION:
        raise ExperimentRecoveryError(
            f"resume workflow mismatch: expected {_WORKFLOW_VERSION}, "
            f"got {state.workflow_version}"
        )
    path_experiment_id, path_run_id = relative.parts
    if state.experiment_id != path_experiment_id or state.run_id != path_run_id:
        raise ExperimentRecoveryError(
            "resume workdir path identity does not match immutable run-state.json"
        )

    try:
        manifest_bytes = manifest_path.read_bytes()
    except OSError as exc:
        raise ExperimentRecoveryError("input/manifest.json is missing") from exc
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    if manifest_sha256 != state.manifest_sha256:
        raise ExperimentRecoveryError(
            "input/manifest.json SHA-256 does not match immutable run-state.json"
        )

    artifact_path = root / "artifacts" / "exports" / state.experiment_id / f"{state.run_id}.zip"
    return ResumePreflight(
        repository_root=root,
        workdir=resolved,
        artifact_path=artifact_path,
        state=state,
        manifest_bytes=manifest_bytes,
    )


def clear_derived_outputs(workdir: Path) -> None:
    """Discard only regenerable downstream state before a resume rebuild."""
    for directory_name in ("reports", "csv"):
        path = workdir / directory_name
        if path.exists():
            if not path.is_dir():
                raise ExperimentRecoveryError(
                    f"derived output path is not a directory: {path}"
                )
            shutil.rmtree(path)
    for file_name in ("execution-summary.json", "artifact-manifest.json"):
        path = workdir / file_name
        if path.exists():
            if not path.is_file():
                raise ExperimentRecoveryError(f"derived output path is not a file: {path}")
            path.unlink()
    (workdir / "reports").mkdir(parents=True, exist_ok=True)


def temporary_artifact_path(artifact_path: Path) -> Path:
    return artifact_path.with_name(f".{artifact_path.name}.tmp")


def prepare_temporary_artifact(artifact_path: Path) -> Path:
    """Return one deterministic sibling temp path, clearing only stale temp state."""
    temporary = temporary_artifact_path(artifact_path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    if temporary.exists():
        if not temporary.is_file():
            raise ExperimentRecoveryError(
                f"temporary artifact path is not a regular file: {temporary}"
            )
        temporary.unlink()
    return temporary


def publish_artifact_create_only(temporary: Path, artifact_path: Path) -> None:
    """Atomically publish a verified same-filesystem temp ZIP without overwriting final."""
    if not temporary.is_file():
        raise ExperimentRecoveryError(f"verified temporary artifact is missing: {temporary}")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(temporary, artifact_path)
    except FileExistsError as exc:
        raise ExperimentRecoveryError(
            f"final artifact already exists and will not be overwritten: {artifact_path}"
        ) from exc
    except OSError as exc:
        raise ExperimentRecoveryError(
            "atomic create-only artifact publication failed; final artifact was not published"
        ) from exc
    try:
        temporary.unlink()
    except OSError as exc:
        raise ExperimentRecoveryError(
            "final artifact was published but temporary artifact cleanup failed"
        ) from exc
