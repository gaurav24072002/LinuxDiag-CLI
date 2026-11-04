"""Disk throughput from /proc/diskstats, whole-device selection via /sys/block.

/proc/diskstats row (absolute field indices):
    0 major   1 minor   2 name   3 reads   4 reads_merged
    5 sectors_read   6 ms_read   7 writes  8 writes_merged  9 sectors_written  ...

Throughput:  MiB/s = delta(sectors) * 512 / elapsed_seconds / 1048576

The sectors here are *accounting* sectors of 512 bytes, even on a device whose
physical sector size is 4 KiB — so 512 is the correct multiplier for both.

Whole devices are identified from /sys/block (partitions appear in
/sys/class/block but not /sys/block). Loopback, RAM, and CD-ROM devices are
skipped by default. Stacked devices (dm-*, nvme*) are kept individually labeled
and never summed across layers.
"""
from __future__ import annotations

import os
from typing import Dict, List, Set, Tuple

from linuxdiag.model import DiskSample, Value

SECTOR_BYTES = 512
MIB = 1024 * 1024

DEFAULT_DISKSTATS_PATH = "/proc/diskstats"
DEFAULT_SYSFS_BLOCK = "/sys/block"
DEFAULT_SKIP_PREFIXES: Tuple[str, ...] = ("loop", "ram", "zram", "sr", "scd")


def parse_diskstats(text: str) -> Dict[str, Tuple[int, int]]:
    """Return ``{name: (sectors_read, sectors_written)}`` from /proc/diskstats text."""
    result: Dict[str, Tuple[int, int]] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 10:
            continue
        name = parts[2]
        try:
            sectors_read = int(parts[5])
            sectors_written = int(parts[9])
        except ValueError:
            continue
        result[name] = (sectors_read, sectors_written)
    return result


def read_diskstats(path: str = DEFAULT_DISKSTATS_PATH) -> str:
    with open(path, "r", encoding="ascii") as handle:
        return handle.read()


def list_sysfs_whole_devices(sysfs_block: str = DEFAULT_SYSFS_BLOCK) -> Set[str]:
    """Whole block devices = the entries in /sys/block. Empty if unavailable."""
    try:
        return set(os.listdir(sysfs_block))
    except OSError:
        return set()


def select_whole_devices(
    diskstats_names: Set[str],
    sysfs_whole: Set[str],
    skip_prefixes: Tuple[str, ...] = DEFAULT_SKIP_PREFIXES,
) -> List[str]:
    """Pick the whole block devices to report.

    A name qualifies only if it is (a) present in /sys/block — i.e. a whole
    device, not a partition — and (b) not in the skip list. Stacked devices
    (dm-*, nvme*) qualify and are reported on their own.
    """
    keep = []
    for name in sorted(diskstats_names):
        if name not in sysfs_whole:
            continue                       # partition or unknown: not a whole device
        if any(name.startswith(prefix) for prefix in skip_prefixes):
            continue                       # loopback / RAM / CD-ROM
        keep.append(name)
    return keep


def _rate(before_sectors: int, after_sectors: int, elapsed: float) -> Value:
    if elapsed is None or elapsed <= 0:
        return Value.unavailable("elapsed was zero (no time between samples)")
    delta = after_sectors - before_sectors
    if delta < 0:
        return Value.unavailable("counter reset (delta negative)")
    return Value.number(delta * SECTOR_BYTES / elapsed / MIB)


def compute_disk(
    a: Dict[str, Tuple[int, int]],
    b: Dict[str, Tuple[int, int]],
    elapsed: float,
    names: List[str],
) -> List[DiskSample]:
    """Per-device read/write MiB/s. A device missing from either snapshot is
    reported as unavailable rather than producing a bogus delta."""
    samples: List[DiskSample] = []
    for name in names:
        if name not in a or name not in b:
            samples.append(DiskSample(
                name=name,
                read_mib_s=Value.unavailable("device absent in one snapshot"),
                write_mib_s=Value.unavailable("device absent in one snapshot"),
            ))
            continue
        read_a, write_a = a[name]
        read_b, write_b = b[name]
        samples.append(DiskSample(
            name=name,
            read_mib_s=_rate(read_a, read_b, elapsed),
            write_mib_s=_rate(write_a, write_b, elapsed),
        ))
    return samples
