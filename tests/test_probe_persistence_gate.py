from __future__ import annotations

import threading
import time

from yandex_analytics_reaper.ingestion import ProbePersistenceGate


def test_probe_persistence_gate_serializes_critical_sections() -> None:
    gate = ProbePersistenceGate()
    lock = threading.Lock()
    active = 0
    maximum = 0

    def persist() -> None:
        nonlocal active, maximum
        with gate.hold():
            with lock:
                active += 1
                maximum = max(maximum, active)
            try:
                time.sleep(0.01)
            finally:
                with lock:
                    active -= 1

    threads = [threading.Thread(target=persist) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert maximum == 1
