"""Assemble a :class:`Report` and decide its status and exit code.

Pure functions over already-collected data — no I/O, no sleeping — so the
exit-code and status rules are testable in isolation.

Exit codes (spec):
  0  complete collection, no alerts
  1  complete collection, one or more alerts
  2  invalid arguments, OR an incomplete collection

An incomplete collection takes *precedence* over alerts, and still reports any
alerts it managed to produce.
"""
from __future__ import annotations

from typing import List, Optional

from linuxdiag import SCHEMA_VERSION
from linuxdiag.model import (
    CpuSample,
    CollectionIssue,
    DiskSample,
    FilesystemSample,
    MemorySample,
    NicSample,
    Report,
)

EXIT_OK = 0
EXIT_ALERTS = 1
EXIT_ERROR = 2


def is_complete(issues: List[CollectionIssue]) -> bool:
    """Complete means no *error*-severity issue. ``info`` issues are fine."""
    return not any(issue.severity == "error" for issue in issues)


def exit_code(complete: bool, alerts: list, valid_args: bool = True) -> int:
    """Map (validity, completeness, alerts) to a process exit code."""
    if not valid_args:
        return EXIT_ERROR
    if not complete:
        return EXIT_ERROR          # incomplete takes precedence over alerts
    if alerts:
        return EXIT_ALERTS
    return EXIT_OK


def build_report(
    *,
    generated_at_utc: str,
    hostname: str,
    elapsed_seconds: float,
    cpus: List[CpuSample],
    memory: Optional[MemorySample],
    disks: List[DiskSample],
    filesystems: List[FilesystemSample],
    nics: List[NicSample],
    issues: List[CollectionIssue],
    alerts: list,
) -> Report:
    """Wire collector outputs into a Report and set completeness from issues."""
    return Report(
        schema_version=SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        hostname=hostname,
        elapsed_seconds=elapsed_seconds,
        complete=is_complete(issues),
        cpus=cpus,
        memory=memory,
        disks=disks,
        filesystems=filesystems,
        nics=nics,
        alerts=alerts,
        collection_issues=issues,
    )
