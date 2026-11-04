"""Memory gauges from /proc/meminfo.

Values in /proc/meminfo are in kB (1024 bytes). We convert to bytes and report:
  * total_bytes     = MemTotal * 1024
  * available_bytes = MemAvailable * 1024
  * used_percent    = 100 * (total - available) / total

used_percent is defined against MemAvailable (the kernel's estimate of memory
usable without swapping), NOT MemFree. A host with a low MemFree but a high
MemAvailable is, by this definition, mostly free — which is the point of the
gauge. If MemAvailable is missing, used_percent (and available_bytes) are
unavailable, not silently 0.
"""
from __future__ import annotations

from typing import Dict, Optional

from linuxdiag.model import MemorySample, Value

DEFAULT_MEMINFO_PATH = "/proc/meminfo"
KIB = 1024


def parse_meminfo(text: str) -> Dict[str, int]:
    """Return ``{field: value_in_kib}`` for numeric /proc/meminfo lines."""
    result: Dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        key = parts[0].rstrip(":")
        try:
            result[key] = int(parts[1])
        except ValueError:
            continue
    return result


def read_meminfo(path: str = DEFAULT_MEMINFO_PATH) -> str:
    with open(path, "r", encoding="ascii") as handle:
        return handle.read()


def compute_memory(mem: Dict[str, int]) -> Optional[MemorySample]:
    """Build a MemorySample, or None if even MemTotal is missing."""
    total_kib = mem.get("MemTotal")
    if total_kib is None:
        return None
    total_bytes = total_kib * KIB

    avail_kib = mem.get("MemAvailable")
    if avail_kib is None:
        return MemorySample(
            total_bytes=total_bytes,
            available_bytes=None,
            used_percent=Value.unavailable("MemAvailable not present in /proc/meminfo"),
        )

    available_bytes = avail_kib * KIB
    if total_bytes <= 0:
        used = Value.unavailable("MemTotal was zero")
    else:
        used = Value.number(100.0 * (total_bytes - available_bytes) / total_bytes)
    return MemorySample(
        total_bytes=total_bytes,
        available_bytes=available_bytes,
        used_percent=used,
    )
