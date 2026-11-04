"""Data model for linuxdiag reports.

The central idea is the distinction the spec keeps returning to:

* a **zero delta on a valid counter** is a real ``0.0`` (available), and
* a **derived value we cannot compute** (denominator was zero, a counter went
  backwards, an interface vanished, a field is missing) is **unavailable**,
  carried with a *reason* — never a negative number, never silently ``0``.

Every derived number is therefore wrapped in a :class:`Value`. Plain ints/floats
are reserved for quantities that are always known (totals, cumulative counts,
elapsed seconds).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


class Value:
    """A possibly-unavailable scalar.

    * available:  ``value`` is a number (may be ``0.0``), ``reason`` is None.
    * unavailable: ``value`` is None, ``reason`` is a short human string.

    Availability is decided by ``value is not None`` so a legitimate ``0.0``
    is never mistaken for "unavailable".
    """

    __slots__ = ("value", "reason")

    def __init__(self, value: Optional[float] = None, reason: Optional[str] = None):
        self.value = value
        self.reason = reason

    @classmethod
    def number(cls, value: float) -> "Value":
        return cls(value=float(value), reason=None)

    @classmethod
    def unavailable(cls, reason: str) -> "Value":
        return cls(value=None, reason=reason)

    @property
    def available(self) -> bool:
        return self.value is not None

    def as_number(self, default: float = 0.0) -> float:
        """Return the number, or ``default`` if unavailable."""
        return self.value if self.value is not None else default

    def to_json(self) -> dict:
        """Uniform JSON leaf: a number, or an explicit null + reason."""
        return {"value": self.value, "reason": self.reason}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        if self.value is None:
            return "Value(unavailable, %r)" % (self.reason,)
        return "Value(%r)" % (self.value,)


@dataclass
class Alert:
    """One threshold crossing. Always carries the observed value and threshold."""

    resource: str      # "aggregate", "cpu3", "mem", "sdb", "/", "ens3"
    metric: str        # "busy_percent", "memory_used_percent", "rx_drops_delta", ...
    observed: float    # the unrounded value that crossed the threshold
    unit: str          # "percent", "count", or "MiB/s"
    threshold: float   # the configured threshold it crossed (inclusive >=)

    def to_json(self) -> dict:
        return {
            "resource": self.resource,
            "metric": self.metric,
            "observed": self.observed,
            "unit": self.unit,
            "threshold": self.threshold,
        }


@dataclass
class CollectionIssue:
    """A note that something could not (or need not) be collected.

    ``severity`` is the key to exit codes:
      * ``"error"`` — a requested source failed to read/parse; makes the
        collection *incomplete* (exit 2), but the rest of the report survives.
      * ``"info"``  — a legitimate empty (e.g. no whole block devices, no
        non-loopback NICs). Recorded for honesty but does not fail the run.
    """

    resource: str      # "/proc/stat", "block devices", "/var", "interfaces", ...
    issue: str         # short machine-able phrase
    detail: str        # human-readable explanation
    severity: str = "error"   # "error" | "info"

    def to_json(self) -> dict:
        return {
            "resource": self.resource,
            "issue": self.issue,
            "detail": self.detail,
            "severity": self.severity,
        }


# --- Per-area samples -------------------------------------------------------


@dataclass
class CpuSample:
    """One logical CPU, or the ``aggregate`` row."""

    name: str          # "aggregate", "cpu0" ... "cpuN" (each a logical CPU)
    busy: Value        # percent executing (user+nice+system+irq+softirq)
    iowait: Value      # percent of delta(total)
    steal: Value       # percent of delta(total)

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "busy_percent": self.busy.to_json(),
            "iowait_percent": self.iowait.to_json(),
            "steal_percent": self.steal.to_json(),
        }


@dataclass
class MemorySample:
    total_bytes: int
    available_bytes: Optional[int]  # None only if MemAvailable was absent
    used_percent: Value  # 100 * (total - available) / total

    def to_json(self) -> dict:
        return {
            "total_bytes": self.total_bytes,
            "available_bytes": self.available_bytes,
            "used_percent": self.used_percent.to_json(),
        }


@dataclass
class DiskSample:
    """One whole block device. Labeled individually, never summed across layers."""

    name: str
    read_mib_s: Value
    write_mib_s: Value

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "read_mib_s": self.read_mib_s.to_json(),
            "write_mib_s": self.write_mib_s.to_json(),
        }


@dataclass
class FilesystemSample:
    """One requested mount path (os.statvfs)."""

    path: str
    total_bytes: int
    used_bytes: int
    available_bytes: int          # f_bavail: space available to an unprivileged user
    space_used_percent: Value
    inode_total: int              # f_files (0 when the fs reports none)
    inode_used: int
    inode_free: int
    inode_used_percent: Value

    def to_json(self) -> dict:
        return {
            "path": self.path,
            "total_bytes": self.total_bytes,
            "used_bytes": self.used_bytes,
            "available_bytes": self.available_bytes,
            "space_used_percent": self.space_used_percent.to_json(),
            "inode_total": self.inode_total,
            "inode_used": self.inode_used,
            "inode_free": self.inode_free,
            "inode_used_percent": self.inode_used_percent.to_json(),
        }


@dataclass
class NicSample:
    """One network interface (excluding loopback by default)."""

    name: str
    rx_errors_cumulative: int
    rx_errors_delta: Value
    tx_errors_cumulative: int
    tx_errors_delta: Value
    rx_drops_cumulative: int
    rx_drops_delta: Value
    tx_drops_cumulative: int
    tx_drops_delta: Value

    def to_json(self) -> dict:
        return {
            "name": self.name,
            "rx_errors": {"cumulative": self.rx_errors_cumulative,
                          "delta": self.rx_errors_delta.to_json()},
            "tx_errors": {"cumulative": self.tx_errors_cumulative,
                          "delta": self.tx_errors_delta.to_json()},
            "rx_drops": {"cumulative": self.rx_drops_cumulative,
                         "delta": self.rx_drops_delta.to_json()},
            "tx_drops": {"cumulative": self.tx_drops_cumulative,
                         "delta": self.tx_drops_delta.to_json()},
        }


@dataclass
class Report:
    """The assembled result of one linuxdiag run (pre-rendering)."""

    schema_version: int
    generated_at_utc: str
    hostname: str
    elapsed_seconds: float
    complete: bool
    cpus: List[CpuSample] = field(default_factory=list)
    memory: Optional[MemorySample] = None
    disks: List[DiskSample] = field(default_factory=list)
    filesystems: List[FilesystemSample] = field(default_factory=list)
    nics: List[NicSample] = field(default_factory=list)
    alerts: List[Alert] = field(default_factory=list)
    collection_issues: List[CollectionIssue] = field(default_factory=list)

    @property
    def status(self) -> str:
        """ok | alert | incomplete. Incomplete wins over alert, alert over ok."""
        if not self.complete:
            return "incomplete"
        if self.alerts:
            return "alert"
        return "ok"

    def to_json(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "generated_at_utc": self.generated_at_utc,
            "hostname": self.hostname,
            "elapsed_seconds": self.elapsed_seconds,
            "status": self.status,
            "metrics": {
                "cpu": [c.to_json() for c in self.cpus],
                "memory": self.memory.to_json() if self.memory else None,
                "disk": [d.to_json() for d in self.disks],
                "filesystem": [f.to_json() for f in self.filesystems],
                "nic": [n.to_json() for n in self.nics],
            },
            "alerts": [a.to_json() for a in self.alerts],
            "collection_issues": [i.to_json() for i in self.collection_issues],
        }
