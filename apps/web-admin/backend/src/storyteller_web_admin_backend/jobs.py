"""In-process job registry for the admin web.

Slow admin operations (world generation, world-piece suggestions, RAG
reindex) used to block the browser tab for 60-180 s and could time out
before the user saw any feedback. Each such POST now schedules a Job on
a tiny ThreadPoolExecutor and redirects to `/jobs/{id}`, which polls
every 3 s via meta-refresh until the job finishes; then it redirects
to the result URL.

Deliberately minimal: in-process only, no persistence, no Redis. Jobs
are lost on admin restart — acceptable for a single-user admin tool.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

_log = logging.getLogger("storyteller.jobs")


@dataclass
class Job:
    id: str
    kind: str                           # short label, e.g. "world-gen"
    title: str = ""                     # human label for the status page
    status: str = "running"             # running | done | error
    started: float = field(default_factory=time.time)
    finished: float | None = None
    result_url: str | None = None    # where to redirect when done
    error: str | None = None         # short error text
    traceback: str | None = None     # full traceback (collapsible)
    detail: str = ""                    # free-form latest progress line

    @property
    def elapsed(self) -> float:
        end = self.finished if self.finished is not None else time.time()
        return max(0.0, end - self.started)

    def progress(self, msg: str) -> None:
        self.detail = msg[:300]
        _log.info("[%s/%s] %s", self.kind, self.id, self.detail)


class JobRegistry:
    """Tiny thread-pool-backed job registry."""

    def __init__(self, max_workers: int = 2):
        self.jobs: dict[str, Job] = {}
        self._exec = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="st-job")
        self._lock = threading.Lock()

    def submit(self, kind: str, title: str,
               fn: Callable[[Job], str]) -> Job:
        """Schedule `fn(job) -> result_url`.

        The function may update `job.detail` via `job.progress(...)`. It
        must return the URL the user should land on when the job is done;
        on exception the job is marked `error` and the traceback stored.
        """
        j = Job(id=uuid.uuid4().hex[:12], kind=kind, title=title)
        with self._lock:
            self.jobs[j.id] = j
        _log.info("[%s/%s] queued: %s", j.kind, j.id, j.title)

        def _run() -> None:
            try:
                url = fn(j)
                j.result_url = url or ""
                j.status = "done"
                _log.info("[%s/%s] done -> %s in %.1fs",
                          j.kind, j.id, j.result_url, j.elapsed)
            except Exception as exc:  # pragma: no cover - external paths
                j.status = "error"
                j.error = f"{exc!r}"
                j.traceback = traceback.format_exc()
                _log.warning("[%s/%s] error after %.1fs: %r",
                             j.kind, j.id, j.elapsed, exc)
            finally:
                j.finished = time.time()
                self._prune()

        self._exec.submit(_run)
        return j

    def get(self, jid: str) -> Job | None:
        return self.jobs.get(jid)

    def _prune(self, max_age: float = 3600.0, keep_min: int = 20) -> None:
        """Forget jobs older than `max_age` seconds, keep at least `keep_min`."""
        now = time.time()
        with self._lock:
            if len(self.jobs) <= keep_min:
                return
            old = [jid for jid, j in self.jobs.items()
                   if j.finished and now - j.finished > max_age]
            for jid in old:
                self.jobs.pop(jid, None)
