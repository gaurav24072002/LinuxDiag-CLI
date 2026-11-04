"""The only place that touches the real filesystem or sleeps.

Sequence (per the spec):
  1. read the interval-based sources (CPU, disk, NIC) -> snapshot A
  2. sleep once for the configured interval
  3. read them again -> snapshot B
  4. read the gauges (memory, filesystems) once, near the end
  5. elapsed = monotonic(B) - monotonic(A)

Every interval-based collector shares that one window. Each source is read
independently and wrapped, so a single failing source records a collection
issue (severity "error") while the other sections still report.
"""
from __future__ import annotations

import sys
import time
from typing import Callable, List, Optional

from linuxdiag.config import Config
from linuxdiag.cpu import compute_cpu, parse_stat_text, read_stat
from linuxdiag.disk import (
    compute_disk,
    list_sysfs_whole_devices,
    parse_diskstats,
    read_diskstats,
    select_whole_devices,
)
from linuxdiag.filesystem import compute_filesystem, read_statvfs
from linuxdiag.memory import compute_memory, parse_meminfo, read_meminfo
from linuxdiag.model import CollectionIssue
from linuxdiag.nic import compute_nic, parse_netdev, read_netdev


def _read(fn: Callable[[], object], resource: str, issues: List[CollectionIssue]) -> Optional[object]:
    """Run a source reader; on any failure record an error issue and return None."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - keep the other sections alive
        issues.append(CollectionIssue(
            resource=resource,
            issue="read_failed",
            detail="%s: %s" % (type(exc).__name__, exc),
            severity="error",
        ))
        return None


def _not_linux() -> dict:
    return {
        "cpus": [], "memory": None, "disks": [], "filesystems": [], "nics": [],
        "issues": [CollectionIssue(
            resource="platform",
            issue="not_linux",
            detail="linuxdiag reads /proc, /sys and statvfs; run it on a Linux host "
                   "(e.g. RHEL 9) with Python 3.9+. On macOS there is nothing to sample.",
            severity="error",
        )],
        "elapsed_seconds": 0.0,
    }


def collect(config: Config, sleep: Callable[[float], None] = time.sleep) -> dict:
    """Collect one sample and return the pieces needed to build a Report."""
    if sys.platform != "linux":
        return _not_linux()

    issues: List[CollectionIssue] = []

    # --- snapshot A ---
    t0 = time.monotonic()
    cpu_a = _read(lambda: parse_stat_text(read_stat()), "/proc/stat", issues)
    disk_a = _read(lambda: parse_diskstats(read_diskstats()), "/proc/diskstats", issues)
    nic_a = _read(lambda: parse_netdev(read_netdev()), "/proc/net/dev", issues)

    # --- wait once ---
    sleep(config.interval)

    # --- snapshot B ---
    cpu_b = _read(lambda: parse_stat_text(read_stat()), "/proc/stat", issues)
    disk_b = _read(lambda: parse_diskstats(read_diskstats()), "/proc/diskstats", issues)
    nic_b = _read(lambda: parse_netdev(read_netdev()), "/proc/net/dev", issues)
    t1 = time.monotonic()
    elapsed = t1 - t0

    # --- gauges, once, near the end ---
    memory = None
    mem_text = _read(read_meminfo, "/proc/meminfo", issues)
    if mem_text is not None:
        memory = compute_memory(parse_meminfo(mem_text))
        if memory is None:
            issues.append(CollectionIssue("memory", "meminfo_incomplete",
                                          "MemTotal missing from /proc/meminfo", "error"))

    filesystems = []
    for path in config.mounts:
        try:
            filesystems.append(compute_filesystem(read_statvfs(path)))
        except OSError as exc:
            issues.append(CollectionIssue(path, "statvfs_failed", str(exc), "error"))

    # --- CPU ---
    cpus = compute_cpu(cpu_a, cpu_b) if (cpu_a is not None and cpu_b is not None) else []

    # --- Disk ---
    disks = []
    if disk_a is not None and disk_b is not None:
        try:
            whole = list_sysfs_whole_devices()
        except OSError:
            whole = set()
        names = select_whole_devices(set(disk_a) | set(disk_b), whole, config.skip_prefixes)
        disks = compute_disk(disk_a, disk_b, elapsed, names)
        if not names:
            issues.append(CollectionIssue(
                "block devices", "none_eligible",
                "no whole block devices to report (loop/RAM/CD skipped, or none present)",
                "info",
            ))

    # --- NIC ---
    nics = compute_nic(nic_a, nic_b) if (nic_a is not None and nic_b is not None) else []
    if nic_a is not None and nic_b is not None and not nics:
        issues.append(CollectionIssue("interfaces", "none",
                                      "no non-loopback interfaces reported by /proc/net/dev",
                                      "info"))

    return {
        "cpus": cpus, "memory": memory, "disks": disks, "filesystems": filesystems,
        "nics": nics, "issues": issues, "elapsed_seconds": elapsed,
    }
