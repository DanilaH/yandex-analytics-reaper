from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"expected one match in {path}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def regex_once(path: str, pattern: str, replacement: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE | re.DOTALL)
    if count != 1:
        raise RuntimeError(f"expected one regex match in {path}: {pattern[:100]!r}")
    target.write_text(updated, encoding="utf-8")


def patch_probe_persistence_gate() -> None:
    path = "src/yandex_analytics_reaper/ingestion/yandex_probes.py"
    replace_once(
        path,
        "from collections.abc import Callable\nfrom dataclasses import dataclass\n",
        "from collections.abc import Callable, Iterator\n"
        "from contextlib import contextmanager\n"
        "from dataclasses import dataclass\n"
        "from threading import RLock\n",
    )
    replace_once(
        path,
        "class ProbeCollectionError(RuntimeError):\n"
        "    \"\"\"A paginated probe could not be completed without compromising run semantics.\"\"\"\n\n\n",
        "class ProbeCollectionError(RuntimeError):\n"
        "    \"\"\"A paginated probe could not be completed without compromising run semantics.\"\"\"\n\n\n"
        "class ProbePersistenceGate:\n"
        "    \"\"\"Serialize SQLite/schema mutations while leaving source I/O concurrent.\"\"\"\n\n"
        "    def __init__(self) -> None:\n"
        "        self._lock = RLock()\n\n"
        "    @contextmanager\n"
        "    def hold(self) -> Iterator[None]:\n"
        "        with self._lock:\n"
        "            yield\n\n\n",
    )
    replace_once(
        path,
        "        page_observer: Callable[[PaginatedProbePageEvent], None] | None = None,\n"
        "    ) -> None:\n",
        "        page_observer: Callable[[PaginatedProbePageEvent], None] | None = None,\n"
        "        persistence_gate: ProbePersistenceGate | None = None,\n"
        "    ) -> None:\n",
    )
    replace_once(
        path,
        "        self.page_observer = page_observer\n\n    def run_feed(\n",
        "        self.page_observer = page_observer\n"
        "        self.persistence_gate = persistence_gate\n\n"
        "    @contextmanager\n"
        "    def _persistence(self) -> Iterator[None]:\n"
        "        if self.persistence_gate is None:\n"
        "            yield\n"
        "            return\n"
        "        with self.persistence_gate.hold():\n"
        "            yield\n\n"
        "    def run_feed(\n",
    )
    replace_once(
        path,
        "        run = self.probe_store.create_run(\n"
        "            source_id=self.client.source_id,\n"
        "            request_key=request_key,\n"
        "            kind=kind,\n"
        "            context=context,\n"
        "            requested_page_limit=page_limit,\n"
        "            started_at=_aware(self.clock(), \"clock result\"),\n"
        "            query_text=query_text,\n"
        "        )\n",
        "        with self._persistence():\n"
        "            run = self.probe_store.create_run(\n"
        "                source_id=self.client.source_id,\n"
        "                request_key=request_key,\n"
        "                kind=kind,\n"
        "                context=context,\n"
        "                requested_page_limit=page_limit,\n"
        "                started_at=_aware(self.clock(), \"clock result\"),\n"
        "                query_text=query_text,\n"
        "            )\n",
    )
    replace_once(
        path,
        "                analysis = self.schema_registry.observe_json(\n"
        "                    metadata,\n"
        "                    response.body,\n"
        "                    comparison_scope_id=schema_comparison_scope_for_snapshot(metadata),\n"
        "                    contract=schema_contract_for_request(metadata.request_key),\n"
        "                )\n",
        "                with self._persistence():\n"
        "                    analysis = self.schema_registry.observe_json(\n"
        "                        metadata,\n"
        "                        response.body,\n"
        "                        comparison_scope_id=schema_comparison_scope_for_snapshot(metadata),\n"
        "                        contract=schema_contract_for_request(metadata.request_key),\n"
        "                    )\n",
    )
    replace_once(
        path,
        "                    self.schema_registry.record_parser_failure(\n"
        "                        metadata,\n"
        "                        comparison_scope_id=schema_comparison_scope_for_snapshot(metadata),\n"
        "                        parser_name=type(parser).__name__,\n"
        "                        parser_version=parser.version,\n"
        "                        error=str(exc),\n"
        "                    )\n",
        "                    with self._persistence():\n"
        "                        self.schema_registry.record_parser_failure(\n"
        "                            metadata,\n"
        "                            comparison_scope_id=schema_comparison_scope_for_snapshot(metadata),\n"
        "                            parser_name=type(parser).__name__,\n"
        "                            parser_version=parser.version,\n"
        "                            error=str(exc),\n"
        "                        )\n",
    )
    replace_once(
        path,
        "                self.probe_store.append_page(page)\n",
        "                with self._persistence():\n"
        "                    self.probe_store.append_page(page)\n",
    )
    replace_once(
        path,
        "            self.probe_store.finish_run(\n"
        "                run.id,\n"
        "                status=ProbeRunStatus.COMPLETED,\n"
        "                completed_at=_completion_time(self.clock(), run, last_retrieved_at),\n"
        "            )\n",
        "            with self._persistence():\n"
        "                self.probe_store.finish_run(\n"
        "                    run.id,\n"
        "                    status=ProbeRunStatus.COMPLETED,\n"
        "                    completed_at=_completion_time(self.clock(), run, last_retrieved_at),\n"
        "                )\n",
    )
    replace_once(
        path,
        "                record = self.probe_store.get_run(run.id)\n"
        "                if record is None:\n"
        "                    raise RuntimeError(\"probe run disappeared during collection\")\n"
        "                if record.run.status is ProbeRunStatus.RUNNING:\n"
        "                    status = ProbeRunStatus.PARTIAL if record.pages else ProbeRunStatus.FAILED\n"
        "                    self.probe_store.finish_run(\n"
        "                        run.id,\n"
        "                        status=status,\n"
        "                        completed_at=_completion_time(self.clock(), run, last_retrieved_at),\n"
        "                        error=_error_text(exc),\n"
        "                        error_raw_snapshot_id=error_raw_snapshot_id,\n"
        "                    )\n",
        "                with self._persistence():\n"
        "                    record = self.probe_store.get_run(run.id)\n"
        "                    if record is None:\n"
        "                        raise RuntimeError(\"probe run disappeared during collection\")\n"
        "                    if record.run.status is ProbeRunStatus.RUNNING:\n"
        "                        status = (\n"
        "                            ProbeRunStatus.PARTIAL if record.pages else ProbeRunStatus.FAILED\n"
        "                        )\n"
        "                        self.probe_store.finish_run(\n"
        "                            run.id,\n"
        "                            status=status,\n"
        "                            completed_at=_completion_time(\n"
        "                                self.clock(), run, last_retrieved_at\n"
        "                            ),\n"
        "                            error=_error_text(exc),\n"
        "                            error_raw_snapshot_id=error_raw_snapshot_id,\n"
        "                        )\n",
    )
    replace_once(
        path,
        "        record = self.probe_store.get_run(run.id)\n"
        "        if record is None:\n"
        "            raise RuntimeError(\"completed probe run could not be reloaded\")\n",
        "        with self._persistence():\n"
        "            record = self.probe_store.get_run(run.id)\n"
        "            if record is None:\n"
        "                raise RuntimeError(\"completed probe run could not be reloaded\")\n",
    )

    init_path = "src/yandex_analytics_reaper/ingestion/__init__.py"
    replace_once(
        init_path,
        "    PaginatedProbeResult,\n    ProbeCollectionError,\n",
        "    PaginatedProbeResult,\n    ProbeCollectionError,\n    ProbePersistenceGate,\n",
    )
    replace_once(
        init_path,
        '    "ProbeCollectionError",\n',
        '    "ProbeCollectionError",\n    "ProbePersistenceGate",\n',
    )


def patch_timing_determinism() -> None:
    path = "src/yandex_analytics_reaper/experiment_runtime.py"
    old = (
        "            stages = tuple(self._stages)\n"
        "            queries = tuple(sorted(self._queries, key=lambda item: item.query_index))\n"
        "            pages = tuple(self._pages)\n"
        "            retries = tuple(self._retries)\n"
        "            rich_batches = tuple(self._rich_batches)\n"
    )
    new = (
        "            stages = tuple(self._stages)\n"
        "            queries = tuple(sorted(self._queries, key=lambda item: item.query_index))\n"
        "            query_order = {item.query: item.query_index for item in queries}\n"
        "            pages = tuple(\n"
        "                sorted(\n"
        "                    self._pages,\n"
        "                    key=lambda item: (query_order.get(item.query, 10**9), item.page),\n"
        "                )\n"
        "            )\n"
        "            retries = tuple(\n"
        "                sorted(\n"
        "                    self._retries,\n"
        "                    key=lambda item: (\n"
        "                        0 if item.query is not None else 1,\n"
        "                        query_order.get(item.query or \"\", 10**9),\n"
        "                        item.batch_index or 0,\n"
        "                        item.attempt,\n"
        "                    ),\n"
        "                )\n"
        "            )\n"
        "            rich_batches = tuple(self._rich_batches)\n"
    )
    replace_once(path, old, new)


def patch_workflow() -> None:
    path = "src/yandex_analytics_reaper/analyst_workflow.py"
    replace_once(
        path,
        "from pathlib import Path, PurePosixPath\nfrom typing import Literal, Self\n",
        "from pathlib import Path, PurePosixPath\n"
        "from threading import current_thread\n"
        "from typing import Literal, Self\n",
    )
    replace_once(
        path,
        "from yandex_analytics_reaper.experiment_runtime import (\n",
        "from yandex_analytics_reaper.experiment_runtime import (\n",
    )
    marker = "from yandex_analytics_reaper.ingestion import (\n"
    worker_import = (
        "from yandex_analytics_reaper.experiment_workers import (\n"
        "    DEFAULT_QUERY_WORKERS,\n"
        "    ExactQueryWorkItem,\n"
        "    ExactQueryWorkResult,\n"
        "    run_bounded_query_workers,\n"
        "    validate_query_workers,\n"
        ")\n"
    )
    replace_once(path, marker, worker_import + marker)
    replace_once(
        path,
        "    ProbeRunStatus,\n",
        "    ProbeRunStatus,\n",
    )
    replace_once(
        path,
        "    PaginatedProbeResult,\n    RichMetadataCollectionResult,\n",
        "    PaginatedProbeResult,\n    ProbePersistenceGate,\n    RichMetadataCollectionResult,\n",
    )
    replace_once(
        path,
        "class AnalystExperimentError(RuntimeError):\n"
        "    \"\"\"A declarative analyst experiment could not complete without weakening its contract.\"\"\"\n\n\n",
        "class AnalystExperimentError(RuntimeError):\n"
        "    \"\"\"A declarative analyst experiment could not complete without weakening its contract.\"\"\"\n\n\n"
        "class _ExactQueryExecutionError(RuntimeError):\n"
        "    def __init__(\n"
        "        self,\n"
        "        *,\n"
        "        item: ExactQueryWorkItem,\n"
        "        worker: str,\n"
        "        cause: Exception,\n"
        "    ) -> None:\n"
        "        super().__init__(str(cause).strip() or type(cause).__name__)\n"
        "        self.item = item\n"
        "        self.worker = worker\n"
        "        self.cause = cause\n\n\n",
    )

    replace_once(
        path,
        "        invocation_started_monotonic: float | None = None,\n"
        "    ) -> AnalystExperimentResult:\n"
        "        invocation_started_at = datetime.now(UTC)\n",
        "        invocation_started_monotonic: float | None = None,\n"
        "        query_workers: int = DEFAULT_QUERY_WORKERS,\n"
        "    ) -> AnalystExperimentResult:\n"
        "        query_workers = validate_query_workers(query_workers)\n"
        "        invocation_started_at = datetime.now(UTC)\n",
    )
    # There are two invocation_started_monotonic signatures: run patched above, resume remains.
    replace_once(
        path,
        "    def resume(\n"
        "        self,\n"
        "        workdir: Path,\n"
        "        *,\n"
        "        invocation_started_monotonic: float | None = None,\n"
        "    ) -> AnalystExperimentResult:\n"
        "        invocation_started_at = datetime.now(UTC)\n",
        "    def resume(\n"
        "        self,\n"
        "        workdir: Path,\n"
        "        *,\n"
        "        invocation_started_monotonic: float | None = None,\n"
        "        query_workers: int = DEFAULT_QUERY_WORKERS,\n"
        "    ) -> AnalystExperimentResult:\n"
        "        query_workers = validate_query_workers(query_workers)\n"
        "        invocation_started_at = datetime.now(UTC)\n",
    )
    # run -> _run_in_workdir
    replace_once(
        path,
        "                            events=events,\n"
        "                            timings=timings,\n"
        "                        )\n",
        "                            events=events,\n"
        "                            timings=timings,\n"
        "                            query_workers=query_workers,\n"
        "                        )\n",
    )
    # resume -> _run_in_workdir
    replace_once(
        path,
        "                                invocation_mode=\"resume\",\n"
        "                                allow_reuse=True,\n"
        "                            )\n",
        "                                invocation_mode=\"resume\",\n"
        "                                allow_reuse=True,\n"
        "                                query_workers=query_workers,\n"
        "                            )\n",
    )
    replace_once(
        path,
        "        invocation_mode: Literal[\"run\", \"resume\"] = \"run\",\n"
        "        allow_reuse: bool = False,\n"
        "    ) -> AnalystExperimentResult:\n",
        "        invocation_mode: Literal[\"run\", \"resume\"] = \"run\",\n"
        "        allow_reuse: bool = False,\n"
        "        query_workers: int = DEFAULT_QUERY_WORKERS,\n"
        "    ) -> AnalystExperimentResult:\n"
        "        query_workers = validate_query_workers(query_workers)\n",
    )

    # Replace only the search-selection stage. Downstream comparable construction stays intact.
    regex_once(
        path,
        r"        families: list\[.*?\n        comparable_sets: list\[ComparableSetVersion\] = \[\]\n",
        '''        families: list[\n            tuple[\n                AnalystExperimentFamily,\n                QueryFamilyVersion,\n                tuple[int, ...],\n                ComparableSetVersion | None,\n            ]\n        ] = []\n        query_total = sum(len(item.queries) for item in manifest.families)\n        query_index = 0\n        reused_query_count = 0\n        collected_query_count = 0\n        expected_context = _effective_clean_context(context)\n        comparable_builder = YandexSearchComparableSetBuilder(\n            raw_store=raw_store,\n            probe_store=probe_store,\n        )\n        persistence_gate = ProbePersistenceGate()\n        selected_run_ids: dict[int, str] = {}\n        pending_queries: list[ExactQueryWorkItem] = []\n\n        with _stage(events, timings, self.monotonic, "search_collection"):\n            for family_input in manifest.families:\n                family = _query_family(\n                    family_input,\n                    language=manifest.context.lang,\n                    created_at=started_at,\n                )\n                family = query_store.persist(family)\n                set_id = f"{manifest.experiment_id}--{family_input.id}"\n                existing_comparable = comparable_store.get(set_id, 1) if allow_reuse else None\n                family_query_indices: list[int] = []\n\n                if existing_comparable is not None:\n                    existing_queries = tuple(run.query_text for run in existing_comparable.runs)\n                    if existing_queries != family_input.queries:\n                        raise AnalystExperimentError(\n                            f"existing comparable {set_id}@1 does not match declared queries"\n                        )\n                    for query, run_ref in zip(\n                        family_input.queries,\n                        existing_comparable.runs,\n                        strict=True,\n                    ):\n                        query_index += 1\n                        family_query_indices.append(query_index)\n                        comparable_builder.validate_reusable_run(\n                            run_ref.probe_run_id,\n                            query_text=query,\n                            expected_context=expected_context,\n                            requested_page_limit=manifest.context.pages,\n                        )\n                        selected_run_ids[query_index] = run_ref.probe_run_id\n                        reused_query_count += 1\n                        timings.record_query(\n                            family_id=family_input.id,\n                            query=query,\n                            query_index=query_index,\n                            query_total=query_total,\n                            action="reused",\n                            elapsed_seconds=None,\n                        )\n                        events.emit(\n                            "query_reused",\n                            stage="search_collection",\n                            family_id=family_input.id,\n                            query=query,\n                            query_index=query_index,\n                            query_total=query_total,\n                            probe_run_id=run_ref.probe_run_id,\n                        )\n                else:\n                    for query in family_input.queries:\n                        query_index += 1\n                        family_query_indices.append(query_index)\n                        reusable = None\n                        if allow_reuse:\n                            candidates = probe_store.find_search_runs(\n                                query_text=query,\n                                context=expected_context,\n                                requested_page_limit=manifest.context.pages,\n                            )\n                            for candidate in candidates:\n                                status = candidate.run.status\n                                if status is ProbeRunStatus.RUNNING:\n                                    events.emit(\n                                        "stale_probe_ignored",\n                                        stage="search_collection",\n                                        family_id=family_input.id,\n                                        query=query,\n                                        query_index=query_index,\n                                        query_total=query_total,\n                                        probe_run_id=candidate.run.id,\n                                    )\n                                    continue\n                                if status is not ProbeRunStatus.COMPLETED:\n                                    continue\n                                try:\n                                    reusable = comparable_builder.validate_reusable_run(\n                                        candidate.run.id,\n                                        query_text=query,\n                                        expected_context=expected_context,\n                                        requested_page_limit=manifest.context.pages,\n                                    )\n                                except ComparableSetConstructionError as exc:\n                                    events.emit(\n                                        "probe_reuse_rejected",\n                                        stage="search_collection",\n                                        family_id=family_input.id,\n                                        query=query,\n                                        query_index=query_index,\n                                        query_total=query_total,\n                                        probe_run_id=candidate.run.id,\n                                        error_type=type(exc).__name__,\n                                        error_message=str(exc),\n                                    )\n                                    continue\n                                break\n\n                        if reusable is not None:\n                            selected_run_ids[query_index] = reusable.run.id\n                            reused_query_count += 1\n                            timings.record_query(\n                                family_id=family_input.id,\n                                query=query,\n                                query_index=query_index,\n                                query_total=query_total,\n                                action="reused",\n                                elapsed_seconds=None,\n                            )\n                            events.emit(\n                                "query_reused",\n                                stage="search_collection",\n                                family_id=family_input.id,\n                                query=query,\n                                query_index=query_index,\n                                query_total=query_total,\n                                probe_run_id=reusable.run.id,\n                            )\n                        else:\n                            pending_queries.append(\n                                ExactQueryWorkItem(\n                                    family_id=family_input.id,\n                                    query=query,\n                                    query_index=query_index,\n                                    query_total=query_total,\n                                )\n                            )\n                families.append(\n                    (\n                        family_input,\n                        family,\n                        tuple(family_query_indices),\n                        existing_comparable,\n                    )\n                )\n\n            try:\n                collected_results = run_bounded_query_workers(\n                    pending_queries,\n                    workers=query_workers,\n                    collect=lambda item: self._collect_query_work_item(\n                        item,\n                        context=context,\n                        page_limit=manifest.context.pages,\n                        raw_store=raw_store,\n                        probe_store=probe_store,\n                        schema_registry=schema_registry,\n                        persistence_gate=persistence_gate,\n                        workdir=workdir,\n                        events=events,\n                        timings=timings,\n                    ),\n                )\n            except _ExactQueryExecutionError as exc:\n                events.emit(\n                    "query_failure_selected",\n                    stage="search_collection",\n                    worker=exc.worker,\n                    family_id=exc.item.family_id,\n                    query=exc.item.query,\n                    query_index=exc.item.query_index,\n                    query_total=exc.item.query_total,\n                    error_type=type(exc.cause).__name__,\n                    error_message=str(exc.cause).strip() or type(exc.cause).__name__,\n                )\n                raise exc.cause from exc\n\n            for result in collected_results:\n                selected_run_ids[result.query_index] = result.run_id\n            collected_query_count = len(collected_results)\n\n        comparable_sets: list[ComparableSetVersion] = []\n''',
    )
    replace_once(
        path,
        "            for family_input, family, family_run_ids, existing in families:\n"
        "                comparable = comparable_builder.build(\n"
        "                    family,\n"
        "                    family_run_ids,\n",
        "            for family_input, family, query_indices, existing in families:\n"
        "                family_run_ids = [selected_run_ids[index] for index in query_indices]\n"
        "                comparable = comparable_builder.build(\n"
        "                    family,\n"
        "                    family_run_ids,\n",
    )
    replace_once(path, "            final_invocation_workers=1,\n", "            final_invocation_workers=query_workers,\n")
    replace_once(path, "            query_workers=1,\n", "            query_workers=query_workers,\n")

    # Add a worker-owned fresh-query boundary before _collect_search.
    marker = "    def _collect_search(\n"
    method = '''    def _collect_query_work_item(\n        self,\n        item: ExactQueryWorkItem,\n        *,\n        context: ProbeContext,\n        page_limit: int,\n        raw_store: FilesystemRawSnapshotStore,\n        probe_store: SQLiteProbeRunStore,\n        schema_registry: SQLiteSchemaDriftRegistry,\n        persistence_gate: ProbePersistenceGate,\n        workdir: Path,\n        events: ExperimentEventEmitter,\n        timings: ExperimentTimingRecorder,\n    ) -> ExactQueryWorkResult:\n        worker = current_thread().name\n        query_started = self.monotonic()\n        events.emit(\n            "query_started",\n            stage="search_collection",\n            worker=worker,\n            family_id=item.family_id,\n            query=item.query,\n            query_index=item.query_index,\n            query_total=item.query_total,\n        )\n        session_manager = YandexSessionManager(\n            state_root=workdir / "sessions",\n            base_url=self.settings.yandex_base_url,\n            timeout_seconds=self.settings.http_timeout_seconds,\n            user_agent=self.settings.user_agent,\n        )\n        try:\n            result = self._collect_search(\n                item.query,\n                context=context,\n                page_limit=page_limit,\n                raw_store=raw_store,\n                probe_store=probe_store,\n                schema_registry=schema_registry,\n                session_manager=session_manager,\n                persistence_gate=persistence_gate,\n                family_id=item.family_id,\n                query_index=item.query_index,\n                query_total=item.query_total,\n                worker=worker,\n                events=events,\n                timings=timings,\n            )\n        except Exception as exc:\n            raise _ExactQueryExecutionError(item=item, worker=worker, cause=exc) from exc\n\n        elapsed = max(0.0, self.monotonic() - query_started)\n        timings.record_query(\n            family_id=item.family_id,\n            query=item.query,\n            query_index=item.query_index,\n            query_total=item.query_total,\n            action="collected",\n            elapsed_seconds=elapsed,\n        )\n        events.emit(\n            "query_completed",\n            stage="search_collection",\n            worker=worker,\n            family_id=item.family_id,\n            query=item.query,\n            query_index=item.query_index,\n            query_total=item.query_total,\n            probe_run_id=result.record.run.id,\n            listing_count=sum(len(page.games) for page in result.parsed_pages),\n            duration_seconds=elapsed,\n        )\n        return ExactQueryWorkResult(\n            query_index=item.query_index,\n            run_id=result.record.run.id,\n        )\n\n'''
    replace_once(path, marker, method + marker)
    replace_once(
        path,
        "        schema_registry: SQLiteSchemaDriftRegistry,\n"
        "        session_manager: YandexSessionManager,\n"
        "        family_id: str,\n",
        "        schema_registry: SQLiteSchemaDriftRegistry,\n"
        "        session_manager: YandexSessionManager,\n"
        "        persistence_gate: ProbePersistenceGate,\n"
        "        family_id: str,\n",
    )
    replace_once(
        path,
        "        query_total: int,\n"
        "        events: ExperimentEventEmitter,\n",
        "        query_total: int,\n"
        "        worker: str,\n"
        "        events: ExperimentEventEmitter,\n",
    )
    replace_once(
        path,
        "                        page_observer=page_observer,\n"
        "                    ).run_search(\n",
        "                        page_observer=page_observer,\n"
        "                        persistence_gate=persistence_gate,\n"
        "                    ).run_search(\n",
    )
    # Worker context on page and query terminal/retry events.
    replace_once(
        path,
        "                stage=\"search_collection\",\n"
        "                family_id=family_id,\n"
        "                query=query,\n",
        "                stage=\"search_collection\",\n"
        "                worker=worker,\n"
        "                family_id=family_id,\n"
        "                query=query,\n",
    )
    # There are three query_retry/query_failed event blocks with identical family/query prefix.
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    needle = (
        "                        stage=\"search_collection\",\n"
        "                        family_id=family_id,\n"
        "                        query=query,\n"
    )
    replacement = (
        "                        stage=\"search_collection\",\n"
        "                        worker=worker,\n"
        "                        family_id=family_id,\n"
        "                        query=query,\n"
    )
    count = text.count(needle)
    if count != 3:
        raise RuntimeError(f"expected three query retry/failure event blocks, found {count}")
    target.write_text(text.replace(needle, replacement), encoding="utf-8")

    # Public wrappers carry workers but manifest bytes/identity do not.
    replace_once(
        path,
        "def resume_analyst_experiment(workdir: Path) -> AnalystExperimentResult:\n"
        "    \"\"\"Resume one preserved v1.2 experiment workdir after strict local preflight.\"\"\"\n"
        "    repository_root = find_repository_root(workdir)\n"
        "    return AnalystExperimentRunner(repository_root=repository_root).resume(workdir)\n",
        "def resume_analyst_experiment(\n"
        "    workdir: Path,\n"
        "    *,\n"
        "    query_workers: int = DEFAULT_QUERY_WORKERS,\n"
        ") -> AnalystExperimentResult:\n"
        "    \"\"\"Resume one preserved v1.2 experiment workdir after strict local preflight.\"\"\"\n"
        "    repository_root = find_repository_root(workdir)\n"
        "    return AnalystExperimentRunner(repository_root=repository_root).resume(\n"
        "        workdir, query_workers=query_workers\n"
        "    )\n",
    )
    replace_once(
        path,
        "def run_analyst_experiment(manifest_path: Path) -> AnalystExperimentResult:\n",
        "def run_analyst_experiment(\n"
        "    manifest_path: Path,\n"
        "    *,\n"
        "    query_workers: int = DEFAULT_QUERY_WORKERS,\n"
        ") -> AnalystExperimentResult:\n",
    )
    replace_once(
        path,
        "        invocation_started_monotonic=invocation_started_monotonic,\n"
        "    )\n\n\ndef find_repository_root",
        "        invocation_started_monotonic=invocation_started_monotonic,\n"
        "        query_workers=query_workers,\n"
        "    )\n\n\ndef find_repository_root",
    )


def patch_cli() -> None:
    path = "src/yandex_analytics_reaper/experiment_cli.py"
    replace_once(
        path,
        "from pathlib import Path\n\nfrom yandex_analytics_reaper.analyst_workflow import (\n",
        "from pathlib import Path\n\n"
        "from yandex_analytics_reaper.experiment_workers import DEFAULT_QUERY_WORKERS\n"
        "from yandex_analytics_reaper.analyst_workflow import (\n",
    )
    replace_once(
        path,
        "        result = run_analyst_experiment(Path(args.manifest))\n",
        "        result = run_analyst_experiment(\n"
        "            Path(args.manifest), query_workers=args.workers\n"
        "        )\n",
    )
    replace_once(
        path,
        "        result = resume_analyst_experiment(Path(args.workdir))\n",
        "        result = resume_analyst_experiment(\n"
        "            Path(args.workdir), query_workers=args.workers\n"
        "        )\n",
    )
    replace_once(
        path,
        "    run.add_argument(\"manifest\", help=\"Path to the experiment manifest JSON.\")\n"
        "    run.set_defaults(handler=_run)\n",
        "    run.add_argument(\"manifest\", help=\"Path to the experiment manifest JSON.\")\n"
        "    run.add_argument(\n"
        "        \"--workers\",\n"
        "        type=int,\n"
        "        choices=range(1, 5),\n"
        "        default=DEFAULT_QUERY_WORKERS,\n"
        "        help=\"Concurrent exact-query workers (1-4; default: 4).\",\n"
        "    )\n"
        "    run.set_defaults(handler=_run)\n",
    )
    replace_once(
        path,
        "    resume.add_argument(\"workdir\", help=\"Path to artifacts/work/<experiment>/<run>.\")\n"
        "    resume.set_defaults(handler=_resume)\n",
        "    resume.add_argument(\"workdir\", help=\"Path to artifacts/work/<experiment>/<run>.\")\n"
        "    resume.add_argument(\n"
        "        \"--workers\",\n"
        "        type=int,\n"
        "        choices=range(1, 5),\n"
        "        default=DEFAULT_QUERY_WORKERS,\n"
        "        help=\"Concurrent exact-query workers (1-4; default: 4).\",\n"
        "    )\n"
        "    resume.set_defaults(handler=_resume)\n",
    )


def add_tests() -> None:
    (ROOT / "tests/test_probe_persistence_gate.py").write_text(
        '''from __future__ import annotations\n\nimport threading\nimport time\n\nfrom yandex_analytics_reaper.ingestion import ProbePersistenceGate\n\n\ndef test_probe_persistence_gate_serializes_critical_sections() -> None:\n    gate = ProbePersistenceGate()\n    lock = threading.Lock()\n    active = 0\n    maximum = 0\n\n    def persist() -> None:\n        nonlocal active, maximum\n        with gate.hold():\n            with lock:\n                active += 1\n                maximum = max(maximum, active)\n            try:\n                time.sleep(0.01)\n            finally:\n                with lock:\n                    active -= 1\n\n    threads = [threading.Thread(target=persist) for _ in range(4)]\n    for thread in threads:\n        thread.start()\n    for thread in threads:\n        thread.join()\n\n    assert maximum == 1\n''',
        encoding="utf-8",
    )
    (ROOT / "tests/test_experiment_cli_workers.py").write_text(
        '''from __future__ import annotations\n\nimport pytest\n\nfrom yandex_analytics_reaper.experiment_cli import build_parser\n\n\ndef test_run_and_resume_default_to_four_workers() -> None:\n    parser = build_parser()\n    assert parser.parse_args(["run", "manifest.json"]).workers == 4\n    assert parser.parse_args(["resume", "workdir"]).workers == 4\n\n\ndef test_worker_override_is_available_to_run_and_resume() -> None:\n    parser = build_parser()\n    assert parser.parse_args(["run", "manifest.json", "--workers", "1"]).workers == 1\n    assert parser.parse_args(["resume", "workdir", "--workers", "3"]).workers == 3\n\n\n@pytest.mark.parametrize("workers", ["0", "5"])\ndef test_cli_rejects_out_of_range_workers(workers: str) -> None:\n    with pytest.raises(SystemExit):\n        build_parser().parse_args(["run", "manifest.json", "--workers", workers])\n''',
        encoding="utf-8",
    )

    workers_test = ROOT / "tests/test_experiment_workers.py"
    text = workers_test.read_text(encoding="utf-8").rstrip()
    text += '''\n\n\ndef test_one_and_four_workers_have_identical_semantic_results() -> None:\n    items = _items(6)\n\n    def collect(item: ExactQueryWorkItem) -> ExactQueryWorkResult:\n        if threading.current_thread().name.startswith("query-worker"):\n            time.sleep((item.query_index % 3) * 0.002)\n        return ExactQueryWorkResult(\n            query_index=item.query_index,\n            run_id=f"run-{item.query_index}",\n        )\n\n    serial = run_bounded_query_workers(items, workers=1, collect=collect)\n    parallel = run_bounded_query_workers(items, workers=4, collect=collect)\n\n    assert parallel == serial\n'''
    workers_test.write_text(text + "\n", encoding="utf-8")

    workflow_test = ROOT / "tests/test_analyst_workflow.py"
    text = workflow_test.read_text(encoding="utf-8")
    replace = (
        "    result = runner.resume(workdir)\n\n"
        "    assert observed\n"
    )
    replacement = (
        "    result = runner.resume(workdir, query_workers=3)\n\n"
        "    assert observed\n"
        "    assert observed[\"query_workers\"] == 3\n"
    )
    if text.count(replace) != 1:
        raise RuntimeError("expected one resume lifecycle success invocation")
    workflow_test.write_text(text.replace(replace, replacement, 1), encoding="utf-8")


def bump_version() -> None:
    replace_once("pyproject.toml", 'version = "0.1.1"\n', 'version = "0.2.0"\n')
    replace_once(
        "src/yandex_analytics_reaper/__init__.py",
        '__version__ = "0.1.1"\n',
        '__version__ = "0.2.0"\n',
    )


def main() -> None:
    patch_probe_persistence_gate()
    patch_timing_determinism()
    patch_workflow()
    patch_cli()
    add_tests()
    bump_version()


if __name__ == "__main__":
    main()
