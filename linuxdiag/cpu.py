"""CPU accounting from /proc/stat.

Field order in each ``cpu`` / ``cpuN`` row (Linux):
    user nice system idle iowait irq softirq steal [guest guest_nice]

Convention (documented so results compare cleanly against ``mpstat``):
  * ``total`` = user + nice + system + idle + iowait + irq + softirq + steal
    (the first eight fields). The guest / guest_nice columns are already
    counted in user / nice by the kernel, so they are *excluded* to avoid
    double counting.
  * ``busy``   = 100 * delta(user+nice+system+irq+softirq) / delta(total)
  * ``iowait`` = 100 * delta(iowait) / delta(total)
  * ``steal``  = 100 * delta(steal)  / delta(total)

``busy`` is "executing time" — it excludes idle, iowait, and steal, exactly as
mpstat's ``%usr + %sys + %irq + %soft`` (minus nice) does.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from linuxdiag.model import CpuSample, Value

# Indices into the 8-field tuple we keep (guest fields dropped at parse time).
_USER, _NICE, _SYSTEM, _IDLE, _IOWAIT, _IRQ, _SOFTIRQ, _STEAL = range(8)
_BUSY_IDX = (_USER, _NICE, _SYSTEM, _IRQ, _SOFTIRQ)

FieldTuple = Tuple[int, int, int, int, int, int, int, int]
StatSnapshot = Dict[str, FieldTuple]

DEFAULT_STAT_PATH = "/proc/stat"


def parse_stat_text(text: str) -> StatSnapshot:
    """Parse /proc/stat text into ``{name: (8 fields)}`` for ``cpu`` and each ``cpuN``.

    Non-CPU lines (intr, ctxt, btime, ...) are ignored. Guest fields are
    dropped so they can never be double counted.
    """
    result: StatSnapshot = {}
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        key = parts[0]
        is_aggregate = key == "cpu"
        is_logical = key.startswith("cpu") and len(key) > 3 and key[3:].isdigit()
        if not (is_aggregate or is_logical):
            continue
        try:
            fields = [int(x) for x in parts[1:]]
        except ValueError:
            continue
        if len(fields) < 8:
            continue
        result[key] = tuple(fields[:8])  # drop guest / guest_nice
    return result


def read_stat(path: str = DEFAULT_STAT_PATH) -> str:
    """Read the raw /proc/stat text (thin I/O; parsing stays pure)."""
    with open(path, "r", encoding="ascii") as handle:
        return handle.read()


def _safe_pct(numerator: int, denominator: int) -> Value:
    """100*num/den with explicit unavailability for zero/negative cases."""
    if denominator <= 0:
        if denominator == 0:
            return Value.unavailable("delta(total) was zero over the window")
        return Value.unavailable("delta(total) negative (counters reset?)")
    if numerator < 0:
        return Value.unavailable("delta negative (counter decreased or reset)")
    return Value.number(100.0 * numerator / denominator)


def _cpu_percents(before: FieldTuple, after: FieldTuple) -> Tuple[Value, Value, Value]:
    d = [after[i] - before[i] for i in range(8)]
    d_total = sum(d)
    d_busy = sum(d[i] for i in _BUSY_IDX)
    busy = _safe_pct(d_busy, d_total)
    iowait = _safe_pct(d[_IOWAIT], d_total)
    steal = _safe_pct(d[_STEAL], d_total)
    return busy, iowait, steal


def _ordered_names(a: StatSnapshot, b: StatSnapshot) -> List[str]:
    common = set(a) & set(b)
    ordered = ["cpu"] if "cpu" in common else []
    logical = [n for n in common if n != "cpu"]
    logical.sort(key=lambda n: int(n[3:]))
    return ordered + logical


def compute_cpu(a: StatSnapshot, b: StatSnapshot) -> List[CpuSample]:
    """Compute busy/iowait/steal per CPU. Only CPUs present in *both* snapshots
    are reported; a CPU that appears between samples is dropped (unreliable delta)."""
    samples: List[CpuSample] = []
    for name in _ordered_names(a, b):
        display = "aggregate" if name == "cpu" else name
        busy, iowait, steal = _cpu_percents(a[name], b[name])
        samples.append(CpuSample(name=display, busy=busy, iowait=iowait, steal=steal))
    return samples
