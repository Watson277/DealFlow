"""Supervise independent requirement consumers inside a single container."""

import os
import signal
import subprocess
import sys
import threading
import time
from contextlib import suppress
from dataclasses import dataclass

import structlog

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging

logger = structlog.get_logger(__name__)
RESTART_RESET_SECONDS = 300.0
CLEANUP_SECONDS = 10.0


@dataclass
class WorkerSlot:
    number: int
    process: subprocess.Popen[bytes] | None = None
    started_at: float = 0.0
    restart_at: float = 0.0
    failures: int = 0


class RequirementPool:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.slots = [WorkerSlot(i + 1) for i in range(settings.requirement_worker_processes)]
        self.stopping = threading.Event()

    def request_stop(self) -> None:
        self.stopping.set()

    def _start(self, slot: WorkerSlot, now: float) -> None:
        env = {**os.environ, "REQUIREMENT_WORKER_SLOT": str(slot.number)}
        # A fresh interpreter creates its own event loop and all network clients.
        slot.process = subprocess.Popen(
            [sys.executable, "-m", "app.workers.requirement_worker"],
            env=env,
        )
        slot.started_at = now
        logger.info("requirement_child_started", slot=slot.number, pid=slot.process.pid)

    def _schedule_restart(self, slot: WorkerSlot, now: float) -> None:
        slot.failures += 1
        if slot.failures > self.settings.requirement_worker_max_restarts:
            raise RuntimeError(f"requirement worker slot {slot.number} exhausted restart budget")
        delay = min(2 ** min(slot.failures - 1, 5), 30)
        slot.restart_at = now + delay
        logger.warning(
            "requirement_child_restart_scheduled",
            slot=slot.number,
            failures=slot.failures,
            delay_seconds=delay,
        )

    def _tick(self, now: float) -> None:
        for slot in self.slots:
            if self.stopping.is_set():
                return
            if slot.process is not None:
                code = slot.process.poll()
                if code is None:
                    continue
                logger.warning(
                    "requirement_child_exited",
                    slot=slot.number,
                    pid=slot.process.pid,
                    exit_code=code,
                )
                if now - slot.started_at >= RESTART_RESET_SECONDS:
                    slot.failures = 0
                slot.process = None
                self._schedule_restart(slot, now)
            if slot.process is None and now >= slot.restart_at:
                try:
                    self._start(slot, now)
                except OSError as exc:
                    logger.error(
                        "requirement_child_spawn_failed",
                        slot=slot.number,
                        error_type=type(exc).__name__,
                    )
                    self._schedule_restart(slot, now)

    def run(self) -> int:
        logger.info("requirement_pool_started", processes=len(self.slots))
        try:
            while not self.stopping.is_set():
                self._tick(time.monotonic())
                self.stopping.wait(0.2)
            return 0
        except Exception as exc:
            logger.error("requirement_pool_failed", error_type=type(exc).__name__, reason=str(exc))
            return 1
        finally:
            self.stopping.set()
            self._shutdown()

    def _shutdown(self) -> None:
        children = [slot.process for slot in self.slots if slot.process is not None]
        # Send TERM to every child before waiting: one shared shutdown budget.
        for child in children:
            if child.poll() is None:
                with suppress(ProcessLookupError):
                    child.terminate()
        deadline = (
            time.monotonic()
            + self.settings.requirement_worker_shutdown_timeout_seconds
            + CLEANUP_SECONDS
        )
        while any(child.poll() is None for child in children) and time.monotonic() < deadline:
            time.sleep(0.1)
        for child in children:
            if child.poll() is None:
                logger.warning("requirement_child_killed", pid=child.pid)
                with suppress(ProcessLookupError):
                    child.kill()
            child.wait()
        logger.info("requirement_pool_stopped")


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, json_logs=settings.app_env != "development")
    # Write message + newline together; print() interleaves them across children.
    structlog.configure(logger_factory=structlog.WriteLoggerFactory())
    pool = RequirementPool(settings)
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda _signum, _frame: pool.request_stop())
    sys.exit(pool.run())


if __name__ == "__main__":
    main()
