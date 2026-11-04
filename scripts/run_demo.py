#!/usr/bin/env python3
"""Deterministic demo of the linuxdiag pipeline on synthetic fixtures.

This is a *development* aid, not a production command. It runs the exact same
parse -> compute -> evaluate -> render code path the CLI uses, but fed from
files under ``tests/fixtures/demo/`` instead of ``/proc``, and with the sample
window fixed at 2.0 seconds. It touches no live counters and applies no load.

The point is to make the numbers reproducible and easy to audit:
  * cpu3 crosses --warn-cpu-busy (94% >= 90) while the aggregate stays below it
    (26% < 90) -- showing per-CPU detection, not just the average;
  * memory, a filesystem (bytes and inodes), and a NIC drop-delta all alert;
  * disk throughput is reported but *not* thresholded (context only);
  * the NIC alert fires on the *delta* (100 -> 101), not the historical total.

Run it with the project on the path, e.g.:
    .venv/bin/python scripts/run_demo.py
    python3 scripts/run_demo.py
"""
from __future__ import annotations

import json
import os
import sys
from typing import Dict

# Make the project root importable when run as a plain script.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from linuxdiag import SCHEMA_VERSION  # noqa: E402
from linuxdiag.config import Config, validate  # noqa: E402
from linuxdiag.cpu import parse_stat_text, compute_cpu  # noqa: E402
from linuxdiag.disk import (  # noqa: E402
    parse_diskstats,
    select_whole_devices,
    compute_disk,
)
from linuxdiag.memory import parse_meminfo, compute_memory  # noqa: E402
from linuxdiag.filesystem import compute_filesystem  # noqa: E402
from linuxdiag.nic import parse_netdev, compute_nic  # noqa: E402
from linuxdiag.evaluate import evaluate  # noqa: E402
from linuxdiag.report import build_report, exit_code  # noqa: E402
from linuxdiag.render_text import render_text  # noqa: E402
from linuxdiag.render_json import render_json  # noqa: E402

# The sample window, held constant so the result is fully deterministic.
ELAPSED_SECONDS = 2.0
FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "tests", "fixtures", "demo")


def _read(name: str) -> str:
    with open(os.path.join(FIXTURES, name), "r", encoding="ascii") as handle:
        return handle.read()


def build_demo_report(config: Config):
    """Run the real pipeline over the demo fixtures and return a Report."""
    # CPU: two /proc/stat snapshots (aggregate + 4 logical CPUs).
    stat_a = parse_stat_text(_read("stat_a.txt"))
    stat_b = parse_stat_text(_read("stat_b.txt"))
    cpus = compute_cpu(stat_a, stat_b)

    # Disk: two /proc/diskstats snapshots, whole-device selection by name.
    disk_a = parse_diskstats(_read("diskstats_a.txt"))
    disk_b = parse_diskstats(_read("diskstats_b.txt"))
    names = select_whole_devices(set(disk_a) | set(disk_b), {"sdb"}, config.skip_prefixes)
    disks = compute_disk(disk_a, disk_b, ELAPSED_SECONDS, names)

    # Memory: a single /proc/meminfo snapshot.
    memory = compute_memory(parse_meminfo(_read("meminfo.txt")))

    # Filesystem: one fabricated statvfs dict (as read_statvfs would return).
    with open(os.path.join(FIXTURES, "statvfs.json"), "r", encoding="ascii") as handle:
        fs_data: Dict = json.load(handle)
    filesystems = [compute_filesystem(fs_data)]

    # NIC: two /proc/net/dev snapshots (loopback excluded).
    netdev_a = parse_netdev(_read("netdev_a.txt"))
    netdev_b = parse_netdev(_read("netdev_b.txt"))
    nics = compute_nic(netdev_a, netdev_b)

    report = build_report(
        generated_at_utc="SYNTHETIC (fixed by the demo)",
        hostname="demo-host",
        elapsed_seconds=ELAPSED_SECONDS,
        cpus=cpus,
        memory=memory,
        disks=disks,
        filesystems=filesystems,
        nics=nics,
        issues=[],
        alerts=[],
    )
    report.alerts = evaluate(report, config)
    return report


def main() -> int:
    config = validate(Config(mounts=["/var"]))
    report = build_demo_report(config)
    code = exit_code(report.complete, report.alerts)

    banner = "=" * 72
    print(banner)
    print("SYNTHETIC DEMO -- not live data, no load applied")
    print("pipeline: parse -> compute -> evaluate -> render  (elapsed fixed at 2.0 s)")
    print("fixtures: tests/fixtures/demo/   schema_version=%d" % SCHEMA_VERSION)
    print(banner)
    print()

    # Human-readable view first (leads with status + findings).
    print(render_text(report))
    print()

    print("-" * 72)
    print("machine-readable JSON (same report):")
    print("-" * 72)
    print(render_json(report))
    print()

    print(banner)
    print("RESULT: status=%s  alerts=%d  exit_code=%d" % (
        report.status, len(report.alerts), code))
    print(banner)
    return code


if __name__ == "__main__":
    sys.exit(main())
