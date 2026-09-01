from __future__ import annotations

import re
from pathlib import Path

path = Path(__file__).with_name("pr_c_bootstrap.py")
text = path.read_text(encoding="utf-8")

pattern = re.compile(
    r'''    replace_once\(\n        path,\n        "        invocation_started_monotonic: float \| None = None,\\n"\n        "    \) -> AnalystExperimentResult:\\n"\n        "        invocation_started_at = datetime\.now\(UTC\)\\n",\n        "        invocation_started_monotonic: float \| None = None,\\n"\n        "        query_workers: int = DEFAULT_QUERY_WORKERS,\\n"\n        "    \) -> AnalystExperimentResult:\\n"\n        "        query_workers = validate_query_workers\(query_workers\)\\n"\n        "        invocation_started_at = datetime\.now\(UTC\)\\n",\n    \)\n'''
)
replacement = '''    replace_once(\n        path,\n        "    def run(\\n"\n        "        self,\\n"\n        "        manifest: AnalystExperimentManifest,\\n"\n        "        *,\\n"\n        "        manifest_bytes: bytes,\\n"\n        "        manifest_validation_elapsed_seconds: float = 0.0,\\n"\n        "        invocation_started_monotonic: float | None = None,\\n"\n        "    ) -> AnalystExperimentResult:\\n"\n        "        invocation_started_at = datetime.now(UTC)\\n",\n        "    def run(\\n"\n        "        self,\\n"\n        "        manifest: AnalystExperimentManifest,\\n"\n        "        *,\\n"\n        "        manifest_bytes: bytes,\\n"\n        "        manifest_validation_elapsed_seconds: float = 0.0,\\n"\n        "        invocation_started_monotonic: float | None = None,\\n"\n        "        query_workers: int = DEFAULT_QUERY_WORKERS,\\n"\n        "    ) -> AnalystExperimentResult:\\n"\n        "        query_workers = validate_query_workers(query_workers)\\n"\n        "        invocation_started_at = datetime.now(UTC)\\n",\n    )\n'''
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise RuntimeError("expected one ambiguous run-signature patch in bootstrap")
path.write_text(text, encoding="utf-8")
