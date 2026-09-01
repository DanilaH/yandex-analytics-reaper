from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"expected one match in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def regex_once(path: str, pattern: str, replacement: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL)
    if count != 1:
        raise RuntimeError(f"expected one regex match in {path}: {pattern[:80]!r}")
    target.write_text(updated, encoding="utf-8")


def patch_probe_store() -> None:
    path = "src/yandex_analytics_reaper/storage/probes.py"
    replace_once(
        path,
        "    def get_run(self, run_id: str) -> ProbeRunRecord | None: ...\n\n\nclass SQLiteProbeRunStore:\n",
        "    def get_run(self, run_id: str) -> ProbeRunRecord | None: ...\n\n"
        "    def find_search_runs(\n"
        "        self,\n"
        "        *,\n"
        "        query_text: str,\n"
        "        context: ProbeContext,\n"
        "        requested_page_limit: int,\n"
        "    ) -> tuple[ProbeRunRecord, ...]: ...\n\n\n"
        "class SQLiteProbeRunStore:\n",
    )
    replace_once(
        path,
        "        return ProbeRunRecord(run=run, context=context, pages=pages)\n\n    @staticmethod\n    def _persist_context(\n",
        "        return ProbeRunRecord(run=run, context=context, pages=pages)\n\n"
        "    def find_search_runs(\n"
        "        self,\n"
        "        *,\n"
        "        query_text: str,\n"
        "        context: ProbeContext,\n"
        "        requested_page_limit: int,\n"
        "    ) -> tuple[ProbeRunRecord, ...]:\n"
        "        query = query_text.strip()\n"
        "        if not query or query != query_text:\n"
        "            raise ValueError(\"query_text must be non-blank and already trimmed\")\n"
        "        if requested_page_limit < 1:\n"
        "            raise ValueError(\"requested_page_limit must be at least 1\")\n"
        "        context_id = _context_id(context)\n"
        "        with self.database.connect() as connection:\n"
        "            rows = connection.execute(\n"
        "                \"\"\"\n"
        "                SELECT id\n"
        "                FROM probe_runs\n"
        "                WHERE source_id = ?\n"
        "                  AND request_key = ?\n"
        "                  AND probe_kind = ?\n"
        "                  AND context_id = ?\n"
        "                  AND query_text = ?\n"
        "                  AND requested_page_limit = ?\n"
        "                ORDER BY started_at DESC, id DESC\n"
        "                \"\"\",\n"
        "                (\n"
        "                    \"yandex_public\",\n"
        "                    \"catalogue.search\",\n"
        "                    ProbeKind.SEARCH.value,\n"
        "                    context_id,\n"
        "                    query,\n"
        "                    requested_page_limit,\n"
        "                ),\n"
        "            ).fetchall()\n"
        "            records: list[ProbeRunRecord] = []\n"
        "            for row in rows:\n"
        "                run = self._load_run(connection, str(row[\"id\"]))\n"
        "                if run is None:\n"
        "                    raise RuntimeError(\"probe lookup returned a missing run\")\n"
        "                stored_context = self._load_context(connection, run.context_id)\n"
        "                if stored_context is None:\n"
        "                    raise RuntimeError(f\"probe context {run.context_id} is missing\")\n"
        "                records.append(\n"
        "                    ProbeRunRecord(\n"
        "                        run=run,\n"
        "                        context=stored_context,\n"
        "                        pages=self._load_pages(connection, run.id),\n"
        "                    )\n"
        "                )\n"
        "        return tuple(records)\n\n"
        "    @staticmethod\n"
        "    def _persist_context(\n",
    )


def patch_comparable_validator() -> None:
    path = "src/yandex_analytics_reaper/comparables/yandex_search.py"
    replace_once(
        path,
        "    QueryFamilyVersion,\n    SessionProfile,\n",
        "    QueryFamilyMember,\n"
        "    QueryFamilyVersion,\n"
        "    QueryVariantKind,\n"
        "    SessionProfile,\n",
    )
    replace_once(
        path,
        "        self.raw_store = raw_store\n        self.probe_store = probe_store\n\n    def build(\n",
        "        self.raw_store = raw_store\n"
        "        self.probe_store = probe_store\n\n"
        "    def validate_reusable_run(\n"
        "        self,\n"
        "        run_id: str,\n"
        "        *,\n"
        "        query_text: str,\n"
        "        expected_context: ProbeContext,\n"
        "        requested_page_limit: int,\n"
        "    ) -> ProbeRunRecord:\n"
        "        record = self.probe_store.get_run(run_id)\n"
        "        if record is None:\n"
        "            raise ComparableSetConstructionError(f\"probe run does not exist: {run_id}\")\n"
        "        if record.run.query_text != query_text:\n"
        "            raise ComparableSetConstructionError(\n"
        "                f\"search run {run_id} query_text does not match recovery request\"\n"
        "            )\n"
        "        if record.context != expected_context:\n"
        "            raise ComparableSetConstructionError(\n"
        "                f\"search run {run_id} ProbeContext does not match recovery request\"\n"
        "            )\n"
        "        if record.run.requested_page_limit != requested_page_limit:\n"
        "            raise ComparableSetConstructionError(\n"
        "                f\"search run {run_id} page limit does not match recovery request\"\n"
        "            )\n"
        "        completed_at = record.run.completed_at\n"
        "        if completed_at is None:\n"
        "            raise ComparableSetConstructionError(\n"
        "                f\"search run {run_id} is not a completed reusable run\"\n"
        "            )\n"
        "        validation_family = QueryFamilyVersion(\n"
        "            family_id=\"recovery-validation\",\n"
        "            version=1,\n"
        "            label=\"Recovery validation\",\n"
        "            source_id=_SOURCE_ID,\n"
        "            language=expected_context.language,\n"
        "            created_at=record.run.started_at,\n"
        "            members=(\n"
        "                QueryFamilyMember(query_text=query_text, kind=QueryVariantKind.SEED),\n"
        "            ),\n"
        "        )\n"
        "        self.build(\n"
        "            validation_family,\n"
        "            (run_id,),\n"
        "            set_id=f\"recovery-validation:{run_id}\",\n"
        "            version=1,\n"
        "            created_at=completed_at,\n"
        "        )\n"
        "        return record\n\n"
        "    def build(\n",
    )


def patch_runtime() -> None:
    path = "src/yandex_analytics_reaper/experiment_runtime.py"
    replace_once(
        path,
        "        logs = workdir / \"logs\"\n"
        "        logs.mkdir(parents=True, exist_ok=True)\n"
        "        self._human = (logs / \"run.log\").open(\"a\", encoding=\"utf-8\")\n"
        "        self._jsonl = (logs / \"events.jsonl\").open(\"a\", encoding=\"utf-8\")\n",
        "        logs = workdir / \"logs\"\n"
        "        logs.mkdir(parents=True, exist_ok=True)\n"
        "        human_path = logs / \"run.log\"\n"
        "        jsonl_path = logs / \"events.jsonl\"\n"
        "        _ensure_append_boundary(human_path)\n"
        "        _ensure_append_boundary(jsonl_path)\n"
        "        self._human = human_path.open(\"a\", encoding=\"utf-8\")\n"
        "        self._jsonl = jsonl_path.open(\"a\", encoding=\"utf-8\")\n",
    )
    replace_once(
        path,
        "def write_run_state(path: Path, state: AnalystExperimentRunState) -> None:\n",
        "def read_run_state(path: Path) -> AnalystExperimentRunState:\n"
        "    try:\n"
        "        return AnalystExperimentRunState.model_validate_json(\n"
        "            path.read_text(encoding=\"utf-8\")\n"
        "        )\n"
        "    except (OSError, ValueError) as exc:\n"
        "        raise ExperimentRuntimeError(\"run-state.json is missing or invalid\") from exc\n\n\n"
        "def write_run_state(path: Path, state: AnalystExperimentRunState) -> None:\n",
    )
    # Add optional resume command to failure summaries without changing PR A callers.
    replace_once(
        path,
        "    elapsed_seconds: float,\n    workdir: str,\n) -> str:\n",
        "    elapsed_seconds: float,\n"
        "    workdir: str,\n"
        "    resume_command: str | None = None,\n"
        ") -> str:\n",
    )
    replace_once(
        path,
        "    parts.append(f\"workdir={workdir}\")\n    return \"; \".join(parts)\n",
        "    parts.append(f\"workdir={workdir}\")\n"
        "    if resume_command is not None:\n"
        "        parts.append(f\"resume={resume_command}\")\n"
        "    return \"; \".join(parts)\n",
    )
    # Helper is deliberately byte-preserving: an interrupted JSON fragment stays forensic.
    insertion = '''\n\ndef _ensure_append_boundary(path: Path) -> None:\n    if not path.exists():\n        return\n    if not path.is_file():\n        raise ExperimentRuntimeError(f"log path is not a regular file: {path}")\n    with path.open("r+b") as handle:\n        handle.seek(0, os.SEEK_END)\n        size = handle.tell()\n        if size == 0:\n            return\n        handle.seek(-1, os.SEEK_END)\n        if handle.read(1) == b"\\n":\n            return\n        handle.seek(0, os.SEEK_END)\n        handle.write(b"\\n")\n        handle.flush()\n        os.fsync(handle.fileno())\n'''
    marker = "\ndef _lock_file(handle: IO[bytes]) -> None:\n"
    replace_once(path, marker, insertion + marker)


def patch_workflow_imports() -> None:
    path = "src/yandex_analytics_reaper/analyst_workflow.py"
    replace_once(
        path,
        "from yandex_analytics_reaper.comparables import YandexSearchComparableSetBuilder\n",
        "from yandex_analytics_reaper.comparables import (\n"
        "    ComparableSetConstructionError,\n"
        "    YandexSearchComparableSetBuilder,\n"
        ")\n",
    )
    replace_once(
        path,
        "    ComparableSetVersion,\n    ProbeContext,\n",
        "    ComparableSetVersion,\n    ProbeContext,\n    ProbeRunStatus,\n",
    )
    replace_once(
        path,
        "from yandex_analytics_reaper.experiment_runtime import (\n",
        "from yandex_analytics_reaper.experiment_recovery import (\n"
        "    ExperimentRecoveryError,\n"
        "    clear_derived_outputs,\n"
        "    load_resume_preflight,\n"
        "    prepare_temporary_artifact,\n"
        "    publish_artifact_create_only,\n"
        ")\n"
        "from yandex_analytics_reaper.experiment_runtime import (\n",
    )


def patch_workflow_runner() -> None:
    path = "src/yandex_analytics_reaper/analyst_workflow.py"
    # Run now advertises the functional resume target on handled failures.
    replace_once(
        path,
        "                                workdir=_relative_display(workdir, self.repository_root),\n"
        "                            )\n",
        "                                workdir=_relative_display(workdir, self.repository_root),\n"
        "                                resume_command=(\n"
        "                                    \"yandex-reaper-experiment resume \"\n"
        "                                    + _relative_display(workdir, self.repository_root)\n"
        "                                ),\n"
        "                            )\n",
    )
    # There is one outer initialization error path; include the now-real recovery command there too.
    replace_once(
        path,
        "                f\"{_relative_display(workdir, self.repository_root)}\"\n"
        "            ) from exc\n\n    def _run_in_workdir(\n",
        "                f\"{_relative_display(workdir, self.repository_root)}; resume=\"\n"
        "                \"yandex-reaper-experiment resume \"\n"
        "                f\"{_relative_display(workdir, self.repository_root)}\"\n"
        "            ) from exc\n\n"
        + '''    def resume(\n        self,\n        workdir: Path,\n        *,\n        invocation_started_monotonic: float | None = None,\n    ) -> AnalystExperimentResult:\n        invocation_started_at = datetime.now(UTC)\n        invocation_mono = (\n            self.monotonic()\n            if invocation_started_monotonic is None\n            else invocation_started_monotonic\n        )\n        resolved_workdir = workdir.resolve()\n        lock = WorkdirLock(resolved_workdir / "run.lock")\n        try:\n            with lock:\n                validation_started = self.monotonic()\n                preflight = load_resume_preflight(self.repository_root, resolved_workdir)\n                try:\n                    manifest = AnalystExperimentManifest.model_validate_json(\n                        preflight.manifest_bytes\n                    )\n                except ValueError as exc:\n                    raise AnalystExperimentError(\n                        "persisted input/manifest.json is not a valid experiment manifest"\n                    ) from exc\n                if manifest.experiment_id != preflight.state.experiment_id:\n                    raise AnalystExperimentError(\n                        "persisted manifest experiment_id disagrees with run-state.json"\n                    )\n                validation_elapsed = max(0.0, self.monotonic() - validation_started)\n\n                if preflight.artifact_path.exists():\n                    result = _result_from_existing_artifact(\n                        preflight.artifact_path,\n                        repository_root=self.repository_root,\n                        state=preflight.state,\n                        invocation_elapsed_seconds=max(\n                            0.0, self.monotonic() - invocation_mono\n                        ),\n                    )\n                    self.output(\n                        "resume recovered already-published verified artifact "\n                        + _relative_display(preflight.artifact_path, self.repository_root)\n                    )\n                else:\n                    initialization_started = self.monotonic()\n                    clear_derived_outputs(preflight.workdir)\n                    timings = ExperimentTimingRecorder(monotonic=self.monotonic)\n                    timings.record_stage("manifest_validation", validation_elapsed)\n                    timings.record_stage(\n                        "workdir_initialization",\n                        max(0.0, self.monotonic() - initialization_started),\n                    )\n                    with ExperimentEventEmitter(\n                        preflight.workdir,\n                        monotonic=self.monotonic,\n                        experiment_id=preflight.state.experiment_id,\n                        run_id=preflight.state.run_id,\n                        output=self.output,\n                        heartbeat_interval_seconds=self.heartbeat_interval_seconds,\n                        started_monotonic=invocation_mono,\n                    ) as events:\n                        query_total = sum(\n                            len(item.queries) for item in manifest.families\n                        )\n                        events.emit(\n                            "resume_started",\n                            stage="workdir_initialization",\n                            query_total=query_total,\n                        )\n                        events.emit(\n                            "stage_completed",\n                            stage="manifest_validation",\n                        )\n                        events.emit(\n                            "stage_completed",\n                            stage="workdir_initialization",\n                        )\n                        try:\n                            result = self._run_in_workdir(\n                                manifest,\n                                started_at=preflight.state.started_at,\n                                invocation_started_at=invocation_started_at,\n                                manifest_sha256=preflight.state.manifest_sha256,\n                                run_id=preflight.state.run_id,\n                                workdir=preflight.workdir,\n                                artifact_path=preflight.artifact_path,\n                                events=events,\n                                timings=timings,\n                                invocation_mode="resume",\n                                allow_reuse=True,\n                            )\n                        except Exception as exc:\n                            failure_context = events.last_context\n                            stage = str(failure_context.get("stage", "unknown"))\n                            events.emit(\n                                "experiment_failed",\n                                stage=stage,\n                                error_type=type(exc).__name__,\n                                error_message=str(exc).strip() or type(exc).__name__,\n                                **{\n                                    key: value\n                                    for key, value in failure_context.items()\n                                    if key != "stage"\n                                },\n                            )\n                            resume_target = _relative_display(\n                                preflight.workdir, self.repository_root\n                            )\n                            raise AnalystExperimentError(\n                                format_failure_summary(\n                                    exc,\n                                    context=failure_context,\n                                    elapsed_seconds=events.elapsed_seconds,\n                                    workdir=resume_target,\n                                    resume_command=(\n                                        "yandex-reaper-experiment resume "\n                                        + resume_target\n                                    ),\n                                )\n                            ) from exc\n                        events.emit(\n                            "experiment_completed",\n                            stage="complete",\n                            query_total=query_total,\n                        )\n            shutil.rmtree(resolved_workdir)\n            return result\n        except AnalystExperimentError:\n            raise\n        except (ExperimentRecoveryError, OSError, ValueError) as exc:\n            raise AnalystExperimentError(\n                f"{type(exc).__name__}: {exc}; workdir preserved at "\n                f"{_relative_display(resolved_workdir, self.repository_root)}"\n            ) from exc\n\n    def _run_in_workdir(\n''',
    )
    replace_once(
        path,
        "        events: ExperimentEventEmitter,\n        timings: ExperimentTimingRecorder,\n    ) -> AnalystExperimentResult:\n",
        "        events: ExperimentEventEmitter,\n"
        "        timings: ExperimentTimingRecorder,\n"
        "        invocation_mode: Literal[\"run\", \"resume\"] = \"run\",\n"
        "        allow_reuse: bool = False,\n"
        "    ) -> AnalystExperimentResult:\n",
    )

    # Replace search + comparable stages with comparable-first deterministic recovery.
    regex_once(
        path,
        r"        families: list\[tuple\[AnalystExperimentFamily, QueryFamilyVersion, list\[str\]\]\] = \[\].*?        with _stage\(events, timings, self\.monotonic, \"family_coherence\"\):",
        '''        families: list[\n            tuple[\n                AnalystExperimentFamily,\n                QueryFamilyVersion,\n                list[str],\n                ComparableSetVersion | None,\n            ]\n        ] = []\n        query_total = sum(len(item.queries) for item in manifest.families)\n        query_index = 0\n        reused_query_count = 0\n        collected_query_count = 0\n        expected_context = _effective_clean_context(context)\n        comparable_builder = YandexSearchComparableSetBuilder(\n            raw_store=raw_store,\n            probe_store=probe_store,\n        )\n\n        with _stage(events, timings, self.monotonic, "search_collection"):\n            for family_input in manifest.families:\n                family = _query_family(\n                    family_input,\n                    language=manifest.context.lang,\n                    created_at=started_at,\n                )\n                family = query_store.persist(family)\n                set_id = f"{manifest.experiment_id}--{family_input.id}"\n                existing_comparable = (\n                    comparable_store.get(set_id, 1) if allow_reuse else None\n                )\n                family_run_ids: list[str] = []\n\n                if existing_comparable is not None:\n                    existing_queries = tuple(\n                        run.query_text for run in existing_comparable.runs\n                    )\n                    if existing_queries != family_input.queries:\n                        raise AnalystExperimentError(\n                            f"existing comparable {set_id}@1 does not match declared queries"\n                        )\n                    for query, run_ref in zip(\n                        family_input.queries,\n                        existing_comparable.runs,\n                        strict=True,\n                    ):\n                        query_index += 1\n                        family_run_ids.append(run_ref.probe_run_id)\n                        reused_query_count += 1\n                        timings.record_query(\n                            family_id=family_input.id,\n                            query=query,\n                            query_index=query_index,\n                            query_total=query_total,\n                            action="reused",\n                            elapsed_seconds=None,\n                        )\n                        events.emit(\n                            "query_reused",\n                            stage="search_collection",\n                            family_id=family_input.id,\n                            query=query,\n                            query_index=query_index,\n                            query_total=query_total,\n                            probe_run_id=run_ref.probe_run_id,\n                        )\n                else:\n                    for query in family_input.queries:\n                        query_index += 1\n                        reusable = None\n                        if allow_reuse:\n                            candidates = probe_store.find_search_runs(\n                                query_text=query,\n                                context=expected_context,\n                                requested_page_limit=manifest.context.pages,\n                            )\n                            for candidate in candidates:\n                                status = candidate.run.status\n                                if status is ProbeRunStatus.RUNNING:\n                                    events.emit(\n                                        "stale_probe_ignored",\n                                        stage="search_collection",\n                                        family_id=family_input.id,\n                                        query=query,\n                                        query_index=query_index,\n                                        query_total=query_total,\n                                        probe_run_id=candidate.run.id,\n                                    )\n                                    continue\n                                if status is not ProbeRunStatus.COMPLETED:\n                                    continue\n                                try:\n                                    reusable = comparable_builder.validate_reusable_run(\n                                        candidate.run.id,\n                                        query_text=query,\n                                        expected_context=expected_context,\n                                        requested_page_limit=manifest.context.pages,\n                                    )\n                                except ComparableSetConstructionError as exc:\n                                    events.emit(\n                                        "probe_reuse_rejected",\n                                        stage="search_collection",\n                                        family_id=family_input.id,\n                                        query=query,\n                                        query_index=query_index,\n                                        query_total=query_total,\n                                        probe_run_id=candidate.run.id,\n                                        error_type=type(exc).__name__,\n                                        error_message=str(exc),\n                                    )\n                                    continue\n                                break\n\n                        if reusable is not None:\n                            family_run_ids.append(reusable.run.id)\n                            reused_query_count += 1\n                            timings.record_query(\n                                family_id=family_input.id,\n                                query=query,\n                                query_index=query_index,\n                                query_total=query_total,\n                                action="reused",\n                                elapsed_seconds=None,\n                            )\n                            events.emit(\n                                "query_reused",\n                                stage="search_collection",\n                                family_id=family_input.id,\n                                query=query,\n                                query_index=query_index,\n                                query_total=query_total,\n                                probe_run_id=reusable.run.id,\n                                listing_count=_organic_listing_count(reusable, raw_store),\n                            )\n                            continue\n\n                        query_started = self.monotonic()\n                        events.emit(\n                            "query_started",\n                            stage="search_collection",\n                            family_id=family_input.id,\n                            query=query,\n                            query_index=query_index,\n                            query_total=query_total,\n                        )\n                        search_result = self._collect_search(\n                            query,\n                            context=context,\n                            page_limit=manifest.context.pages,\n                            raw_store=raw_store,\n                            probe_store=probe_store,\n                            schema_registry=schema_registry,\n                            session_manager=session_manager,\n                            family_id=family_input.id,\n                            query_index=query_index,\n                            query_total=query_total,\n                            events=events,\n                            timings=timings,\n                        )\n                        family_run_ids.append(search_result.record.run.id)\n                        collected_query_count += 1\n                        elapsed = max(0.0, self.monotonic() - query_started)\n                        timings.record_query(\n                            family_id=family_input.id,\n                            query=query,\n                            query_index=query_index,\n                            query_total=query_total,\n                            action="collected",\n                            elapsed_seconds=elapsed,\n                        )\n                        events.emit(\n                            "query_completed",\n                            stage="search_collection",\n                            family_id=family_input.id,\n                            query=query,\n                            query_index=query_index,\n                            query_total=query_total,\n                            probe_run_id=search_result.record.run.id,\n                            listing_count=sum(\n                                len(page.games) for page in search_result.parsed_pages\n                            ),\n                            duration_seconds=elapsed,\n                        )\n                families.append(\n                    (family_input, family, family_run_ids, existing_comparable)\n                )\n\n        comparable_sets: list[ComparableSetVersion] = []\n        with _stage(events, timings, self.monotonic, "comparable_construction"):\n            for family_input, family, family_run_ids, existing in families:\n                comparable = comparable_builder.build(\n                    family,\n                    family_run_ids,\n                    set_id=f"{manifest.experiment_id}--{family_input.id}",\n                    version=1,\n                    created_at=(existing.created_at if existing is not None else datetime.now(UTC)),\n                )\n                if existing is not None:\n                    if comparable != existing:\n                        raise AnalystExperimentError(\n                            f"existing comparable {existing.set_id}@{existing.version} "\n                            "does not replay exactly from its selected run IDs"\n                        )\n                    comparable_sets.append(existing)\n                else:\n                    comparable_sets.append(comparable_store.persist(comparable))\n\n        with _stage(events, timings, self.monotonic, "family_coherence"):\n''',
    )

    # Successful summary/timings reflect only this final invocation.
    replace_once(path, '            final_invocation_mode="run",\n', '            final_invocation_mode=invocation_mode,\n')
    replace_once(path, '            was_resumed=False,\n', '            was_resumed=invocation_mode == "resume",\n')
    replace_once(path, '            reused_query_count=0,\n', '            reused_query_count=reused_query_count,\n')
    replace_once(path, '            collected_query_count=query_total,\n', '            collected_query_count=collected_query_count,\n')
    replace_once(path, '                invocation_mode="run",\n', '                invocation_mode=invocation_mode,\n')

    # Crash-safe same-filesystem temp ZIP publication. Never discard an existing final ZIP.
    regex_once(
        path,
        r"        artifact_path\.parent\.mkdir\(parents=True, exist_ok=True\)\n        try:\n            with _stage\(events, timings, self\.monotonic, \"package_write\"\):.*?        return AnalystExperimentResult\(",
        '''        temporary_artifact = prepare_temporary_artifact(artifact_path)\n        try:\n            with _stage(events, timings, self.monotonic, "package_write"):\n                package_workdir(workdir, temporary_artifact)\n            with _stage(events, timings, self.monotonic, "package_verification"):\n                verified_manifest = verify_packaged_artifact(\n                    temporary_artifact,\n                    expected_experiment_id=artifact_manifest.experiment_id,\n                    expected_run_id=artifact_manifest.run_id,\n                )\n                if verified_manifest != artifact_manifest:\n                    raise AnalystExperimentError(\n                        "packaged artifact manifest does not match the manifest built "\n                        "from the workdir"\n                    )\n            with _stage(events, timings, self.monotonic, "final_hashing"):\n                artifact_sha256 = _sha256_file(temporary_artifact)\n                publish_artifact_create_only(temporary_artifact, artifact_path)\n        except Exception:\n            _discard_artifact(temporary_artifact)\n            raise\n\n        return AnalystExperimentResult(''',
    )


def patch_workflow_helpers() -> None:
    path = "src/yandex_analytics_reaper/analyst_workflow.py"
    marker = "\ndef run_analyst_experiment(manifest_path: Path) -> AnalystExperimentResult:\n"
    helpers = '''\n\ndef _effective_clean_context(context: ProbeContext) -> ProbeContext:\n    return ProbeContext.model_validate(\n        context.model_copy(\n            update={\n                "session_instance_id": None,\n                "cookie_state_hash": None,\n                "profile_age_days": 0,\n            }\n        ).model_dump()\n    )\n\n\ndef _organic_listing_count(record: object, raw_store: FilesystemRawSnapshotStore) -> int:\n    # The reusable-run validator already replayed the exact raw pages. This diagnostic\n    # count is intentionally best-effort and never participates in recovery decisions.\n    del raw_store\n    pages = getattr(record, "pages", ())\n    return len(pages)\n\n\ndef _result_from_existing_artifact(\n    artifact_path: Path,\n    *,\n    repository_root: Path,\n    state: AnalystExperimentRunState,\n    invocation_elapsed_seconds: float,\n) -> AnalystExperimentResult:\n    if not artifact_path.is_file():\n        raise AnalystExperimentError(\n            f"existing final artifact is not a regular file: {artifact_path}"\n        )\n    try:\n        artifact_manifest = verify_packaged_artifact(\n            artifact_path,\n            expected_experiment_id=state.experiment_id,\n            expected_run_id=state.run_id,\n        )\n        with ZipFile(artifact_path, "r") as archive:\n            summary_bytes = archive.read("execution-summary.json")\n            manifest_bytes = archive.read("artifact-manifest.json")\n        summary = AnalystExperimentExecutionSummary.model_validate_json(summary_bytes)\n    except (BadZipFile, KeyError, OSError, ValueError) as exc:\n        raise AnalystExperimentError(\n            "existing final artifact is invalid and will not be overwritten"\n        ) from exc\n    if (\n        summary.experiment_id != state.experiment_id\n        or summary.run_id != state.run_id\n        or summary.manifest_sha256 != state.manifest_sha256\n        or artifact_manifest.experiment_id != state.experiment_id\n        or artifact_manifest.run_id != state.run_id\n    ):\n        raise AnalystExperimentError(\n            "existing final artifact identity does not match resume state; refusing overwrite"\n        )\n    return AnalystExperimentResult(\n        experiment_id=state.experiment_id,\n        run_id=state.run_id,\n        artifact_path=_relative_display(artifact_path, repository_root),\n        artifact_sha256=_sha256_file(artifact_path),\n        artifact_manifest_sha256=_sha256_bytes(manifest_bytes),\n        verifier="PASS",\n        family_count=summary.family_count,\n        query_count=summary.query_count,\n        comparable_unique_listing_count=summary.comparable_unique_listing_count,\n        rich_requested_listing_count=summary.rich_requested_listing_count,\n        rich_observed_listing_count=summary.rich_observed_listing_count,\n        invocation_elapsed_seconds=max(0.0, invocation_elapsed_seconds),\n    )\n\n\ndef resume_analyst_experiment(workdir: Path) -> AnalystExperimentResult:\n    """Resume one preserved v1.2 experiment workdir after strict local preflight."""\n    repository_root = _repository_root()\n    return AnalystExperimentRunner(repository_root=repository_root).resume(workdir)\n'''
    replace_once(path, marker, helpers + marker)

    # Standalone finalizer follows the same safe publication contract used by the runner.
    regex_once(
        path,
        r"def finalize_verified_artifact\(\n    workdir: Path,\n    artifact_path: Path,\n    \*,\n    expected_manifest: AnalystArtifactManifest,\n\) -> str:\n.*?\n\ndef package_workdir\(",
        '''def finalize_verified_artifact(\n    workdir: Path,\n    artifact_path: Path,\n    *,\n    expected_manifest: AnalystArtifactManifest,\n) -> str:\n    temporary = prepare_temporary_artifact(artifact_path)\n    try:\n        package_workdir(workdir, temporary)\n        verified = verify_packaged_artifact(\n            temporary,\n            expected_experiment_id=expected_manifest.experiment_id,\n            expected_run_id=expected_manifest.run_id,\n        )\n        if verified != expected_manifest:\n            raise AnalystExperimentError(\n                "packaged artifact manifest does not match expected manifest"\n            )\n        digest = _sha256_file(temporary)\n        publish_artifact_create_only(temporary, artifact_path)\n        return digest\n    except Exception:\n        _discard_artifact(temporary)\n        raise\n\n\ndef package_workdir(''',
    )


def patch_cli() -> None:
    path = "src/yandex_analytics_reaper/experiment_cli.py"
    replace_once(
        path,
        "    AnalystExperimentError,\n    run_analyst_experiment,\n",
        "    AnalystExperimentError,\n"
        "    resume_analyst_experiment,\n"
        "    run_analyst_experiment,\n",
    )
    replace_once(
        path,
        "def build_parser() -> argparse.ArgumentParser:\n",
        '''def _resume(args: argparse.Namespace) -> None:\n    try:\n        result = resume_analyst_experiment(Path(args.workdir))\n    except (OSError, ValueError, AnalystExperimentError) as exc:\n        raise SystemExit(str(exc)) from exc\n    print(result.model_dump_json(indent=2))\n\n\ndef build_parser() -> argparse.ArgumentParser:\n''',
    )
    replace_once(
        path,
        "    run.add_argument(\"manifest\", help=\"Path to the experiment manifest JSON.\")\n"
        "    run.set_defaults(handler=_run)\n"
        "    return parser\n",
        "    run.add_argument(\"manifest\", help=\"Path to the experiment manifest JSON.\")\n"
        "    run.set_defaults(handler=_run)\n"
        "    resume = sub.add_parser(\"resume\", help=\"Resume one preserved v1.2 workdir.\")\n"
        "    resume.add_argument(\"workdir\", help=\"Path to artifacts/work/<experiment>/<run>.\")\n"
        "    resume.set_defaults(handler=_resume)\n"
        "    return parser\n",
    )


def add_tests() -> None:
    (ROOT / "tests/test_experiment_recovery.py").write_text(
        '''from __future__ import annotations\n\nimport hashlib\nfrom datetime import UTC, datetime\nfrom pathlib import Path\n\nimport pytest\n\nfrom yandex_analytics_reaper.experiment_recovery import (\n    ExperimentRecoveryError,\n    clear_derived_outputs,\n    load_resume_preflight,\n    prepare_temporary_artifact,\n    publish_artifact_create_only,\n)\nfrom yandex_analytics_reaper.experiment_runtime import (\n    AnalystExperimentRunState,\n    ExperimentEventEmitter,\n    write_run_state,\n)\n\n\ndef _workdir(tmp_path: Path) -> tuple[Path, bytes, AnalystExperimentRunState]:\n    workdir = tmp_path / "artifacts" / "work" / "demo" / "20260901T000000Z"\n    manifest = b'{"schema_version":1,"experiment_id":"demo","context":{"pages":1,"session_profile":"clean_anonymous","lang":"ru","device":"desktop","platform":"desktop_other"},"families":[{"id":"f","queries":["q"]}]}'\n    (workdir / "input").mkdir(parents=True)\n    (workdir / "input" / "manifest.json").write_bytes(manifest)\n    state = AnalystExperimentRunState(\n        experiment_id="demo",\n        run_id="20260901T000000Z",\n        started_at=datetime(2026, 9, 1, tzinfo=UTC),\n        manifest_sha256=hashlib.sha256(manifest).hexdigest(),\n    )\n    write_run_state(workdir / "run-state.json", state)\n    return workdir, manifest, state\n\n\ndef test_resume_preflight_requires_exact_path_and_manifest_identity(tmp_path: Path) -> None:\n    workdir, manifest, state = _workdir(tmp_path)\n    result = load_resume_preflight(tmp_path, workdir)\n    assert result.state == state\n    assert result.manifest_bytes == manifest\n    assert result.artifact_path == (\n        tmp_path / "artifacts" / "exports" / "demo" / "20260901T000000Z.zip"\n    )\n\n    (workdir / "input" / "manifest.json").write_bytes(manifest + b" ")\n    with pytest.raises(ExperimentRecoveryError, match="SHA-256"):\n        load_resume_preflight(tmp_path, workdir)\n\n\ndef test_clear_derived_outputs_preserves_evidence_and_operational_state(tmp_path: Path) -> None:\n    workdir, _, _ = _workdir(tmp_path)\n    for path in (workdir / "raw", workdir / "logs"):\n        path.mkdir()\n        (path / "keep.txt").write_text("keep", encoding="utf-8")\n    (workdir / "market.sqlite3").write_bytes(b"db")\n    (workdir / "reports").mkdir()\n    (workdir / "reports" / "partial.json").write_text("partial", encoding="utf-8")\n    (workdir / "csv").mkdir()\n    (workdir / "csv" / "partial.csv").write_text("partial", encoding="utf-8")\n    (workdir / "execution-summary.json").write_text("partial", encoding="utf-8")\n\n    clear_derived_outputs(workdir)\n\n    assert (workdir / "raw" / "keep.txt").read_text(encoding="utf-8") == "keep"\n    assert (workdir / "logs" / "keep.txt").read_text(encoding="utf-8") == "keep"\n    assert (workdir / "market.sqlite3").read_bytes() == b"db"\n    assert list((workdir / "reports").iterdir()) == []\n    assert not (workdir / "csv").exists()\n    assert not (workdir / "execution-summary.json").exists()\n\n\ndef test_event_emitter_preserves_truncated_jsonl_tail_and_starts_new_line(tmp_path: Path) -> None:\n    logs = tmp_path / "logs"\n    logs.mkdir()\n    events_path = logs / "events.jsonl"\n    events_path.write_bytes(b'{"interrupted":')\n\n    with ExperimentEventEmitter(\n        tmp_path,\n        experiment_id="demo",\n        run_id="run",\n        heartbeat_interval_seconds=0,\n        output=lambda _: None,\n    ) as events:\n        events.emit("resume_started", stage="initialization")\n\n    data = events_path.read_bytes()\n    assert data.startswith(b'{"interrupted":\\n')\n    assert b'"event":"resume_started"' in data.splitlines()[-1]\n\n\ndef test_create_only_publication_never_overwrites_final(tmp_path: Path) -> None:\n    final = tmp_path / "artifact.zip"\n    temp = prepare_temporary_artifact(final)\n    temp.write_bytes(b"verified")\n    publish_artifact_create_only(temp, final)\n    assert final.read_bytes() == b"verified"\n    assert not temp.exists()\n\n    temp = prepare_temporary_artifact(final)\n    temp.write_bytes(b"new")\n    with pytest.raises(ExperimentRecoveryError, match="will not be overwritten"):\n        publish_artifact_create_only(temp, final)\n    assert final.read_bytes() == b"verified"\n''',
        encoding="utf-8",
    )

    # Narrow probe lookup + validator coverage extends existing fixtures without source I/O.
    test_path = ROOT / "tests/test_yandex_search_comparable_builder.py"
    text = test_path.read_text(encoding="utf-8")
    text += '''\n\ndef test_recovery_lookup_and_validator_reuse_exact_completed_run(tmp_path: Path) -> None:\n    raw_store, probe_store, family, run_ids = _valid_family_run_fixture(tmp_path)\n    first = probe_store.get_run(run_ids[0])\n    assert first is not None\n    candidates = probe_store.find_search_runs(\n        query_text=first.run.query_text or "",\n        context=first.context,\n        requested_page_limit=first.run.requested_page_limit,\n    )\n    assert [item.run.id for item in candidates] == [run_ids[0]]\n    validated = YandexSearchComparableSetBuilder(\n        raw_store=raw_store,\n        probe_store=probe_store,\n    ).validate_reusable_run(\n        run_ids[0],\n        query_text=first.run.query_text or "",\n        expected_context=first.context,\n        requested_page_limit=first.run.requested_page_limit,\n    )\n    assert validated == first\n'''
    test_path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_probe_store()
    patch_comparable_validator()
    patch_runtime()
    patch_workflow_imports()
    patch_workflow_runner()
    patch_workflow_helpers()
    patch_cli()
    add_tests()


if __name__ == "__main__":
    main()
