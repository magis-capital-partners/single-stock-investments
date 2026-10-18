#!/usr/bin/env python3
"""Resource guards for the always-on Mac Mini media lane.

Whisper beside the local LLM measured a 5.5x collapse in transcription rate.
These helpers exist so one supervisor can keep the box usable: low priority,
bounded threads, and a hard pause when free memory is thin.
"""
from __future__ import annotations

import fcntl
import os
import platform
import re
import subprocess
import time
from pathlib import Path


def deprioritise(nice: int = 15) -> str:
    """Yield the scheduler to interactive work. Same contract as the Whisper daemon."""
    if hasattr(os, "nice"):
        try:
            os.nice(int(nice))
            return f"nice+{int(nice)}"
        except OSError:
            return "unchanged"
    return "unchanged"


def available_mb() -> int | None:
    """Best-effort free physical memory in MiB.

    On Darwin, sysconf SC_AVPHYS_PAGES under-reports usable memory on unified-
    memory Macs (it counts free pages, not inactive / purgeable). Prefer
    ``vm_stat`` pages free+inactive+purgeable, which is what Activity Monitor
    roughly treats as reclaimable.
    """
    system = platform.system()
    if system == "Darwin":
        try:
            out = subprocess.check_output(["vm_stat"], text=True, timeout=5)
        except (OSError, subprocess.SubprocessError):
            out = ""
        page = 4096
        m = re.search(r"page size of\s+(\d+)\s+bytes", out)
        if m:
            page = int(m.group(1))
        buckets = 0
        for label in ("Pages free", "Pages inactive", "Pages purgeable"):
            hit = re.search(rf"{label}:\s+([\d.]+)", out)
            if hit:
                buckets += int(float(hit.group(1).rstrip(".")))
        if buckets:
            return int(buckets * page / 1048576)
    if hasattr(os, "sysconf") and "SC_AVPHYS_PAGES" in getattr(os, "sysconf_names", {}):
        try:
            return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1048576)
        except (ValueError, OSError):
            pass
    if system == "Linux":
        try:
            text = Path("/proc/meminfo").read_text(encoding="utf-8")
        except OSError:
            return None
        # MemAvailable already accounts for reclaimable cache.
        hit = re.search(r"MemAvailable:\s+(\d+)\s+kB", text)
        if hit:
            return int(hit.group(1)) // 1024
    return None


def wait_for_memory(
    floor_mb: int,
    *,
    poll_seconds: int = 60,
    log=print,
    stop_flag=None,
) -> None:
    """Block while free memory is below ``floor_mb``."""
    while True:
        if stop_flag is not None and stop_flag():
            return
        free = available_mb()
        if free is None or free >= floor_mb:
            return
        log(f"only {free} MB reclaimable (floor {floor_mb}); sleeping {poll_seconds}s")
        time.sleep(poll_seconds)


def cpu_count() -> int:
    return os.cpu_count() or 4


def default_whisper_threads(cap: int = 4) -> int:
    """Leave headroom on a small Mac Mini: at most ``cap``, and never all cores."""
    cores = cpu_count()
    return max(1, min(cap, max(1, cores // 2)))


class FileLock:
    """Exclusive flock so two supervisors cannot share one backlog."""

    def __init__(self, path: Path):
        self.path = path
        self._fh = None

    def acquire(self, blocking: bool = False) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a+", encoding="utf-8")
        flags = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(self._fh.fileno(), flags)
        except BlockingIOError:
            self._fh.close()
            self._fh = None
            return False
        self._fh.seek(0)
        self._fh.truncate()
        self._fh.write(f"pid={os.getpid()}\n")
        self._fh.flush()
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self):
        if not self.acquire(blocking=False):
            raise RuntimeError(f"lock held: {self.path}")
        return self

    def __exit__(self, *exc):
        self.release()
        return False
