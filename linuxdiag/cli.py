"""Command-line interface for linuxdiag.

``main(argv, collector)`` returns a process exit code:
  0  complete, no alerts          1  complete, one or more alerts
  2  invalid arguments, or incomplete collection

``collector`` is injectable so the argument/validation/render/exit path can be
tested cross-platform without touching /proc or sleeping; the default is the
real :func:`linuxdiag.sampling.collect`.
"""
from __future__ import annotations

import argparse
import datetime
import socket
import sys
from typing import List, Optional

from linuxdiag import SCHEMA_VERSION
from linuxdiag.config import (
    DEFAULT_FORMAT,
    DEFAULT_INTERVAL,
    DEFAULT_MOUNTS,
    DEFAULT_SKIP_PREFIXES,
    Config,
    ConfigError,
    validate,
)
from linuxdiag.evaluate import evaluate
from linuxdiag.report import EXIT_ERROR, build_report, exit_code
from linuxdiag.render_json import render_json
from linuxdiag.render_text import render_text
from linuxdiag.sampling import collect

_DEFAULT_MOUNT = DEFAULT_MOUNTS[0]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linuxdiag",
        description="Read-only Linux compute & storage diagnostics: one short sample.",
    )
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, metavar="SECONDS",
                        help="sample window in seconds; positive and finite (default 1.0)")
    parser.add_argument("--mount", action="append", metavar="PATH",
                        help="filesystem path to inspect; repeatable (default /)")
    parser.add_argument("--format", choices=["text", "json"], default=DEFAULT_FORMAT,
                        help="output format (default text)")
    parser.add_argument("--warn-cpu-busy", type=float, default=90.0, metavar="PCT",
                        help="alert when a logical CPU (or aggregate) busy%% reaches PCT [0-100]")
    parser.add_argument("--warn-iowait", type=float, default=20.0, metavar="PCT",
                        help="alert when iowait%% reaches PCT [0-100]")
    parser.add_argument("--warn-memory-used", type=float, default=90.0, metavar="PCT",
                        help="alert when memory used%% reaches PCT [0-100]")
    parser.add_argument("--warn-space-used", type=float, default=90.0, metavar="PCT",
                        help="alert when a filesystem space-used%% reaches PCT [0-100]")
    parser.add_argument("--warn-inodes-used", type=float, default=90.0, metavar="PCT",
                        help="alert when a filesystem inode-used%% reaches PCT [0-100]")
    parser.add_argument("--warn-nic-errors", type=int, default=1, metavar="COUNT",
                        help="alert when any NIC error delta reaches COUNT (positive int)")
    parser.add_argument("--warn-nic-drops", type=int, default=1, metavar="COUNT",
                        help="alert when any NIC drop delta reaches COUNT (positive int)")
    return parser


def _config_from_args(args: argparse.Namespace) -> Config:
    return Config(
        interval=args.interval,
        mounts=list(args.mount) if args.mount else [_DEFAULT_MOUNT],
        format=args.format,
        warn_cpu_busy=args.warn_cpu_busy,
        warn_iowait=args.warn_iowait,
        warn_memory_used=args.warn_memory_used,
        warn_space_used=args.warn_space_used,
        warn_inodes_used=args.warn_inodes_used,
        warn_nic_errors=args.warn_nic_errors,
        warn_nic_drops=args.warn_nic_drops,
        skip_prefixes=DEFAULT_SKIP_PREFIXES,
    )


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: Optional[List[str]] = None, collector=collect) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # argparse already wrote an actionable message to stderr. --help exits 0.
        return exc.code if isinstance(exc.code, int) else EXIT_ERROR

    config = _config_from_args(args)
    try:
        validate(config)
    except ConfigError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return EXIT_ERROR

    collected = collector(config)

    report = build_report(
        generated_at_utc=_utcnow(),
        hostname=socket.gethostname(),
        elapsed_seconds=collected["elapsed_seconds"],
        cpus=collected["cpus"],
        memory=collected["memory"],
        disks=collected["disks"],
        filesystems=collected["filesystems"],
        nics=collected["nics"],
        issues=collected["issues"],
        alerts=[],
    )
    report.alerts = evaluate(report, config)

    if config.format == "json":
        sys.stdout.write(render_json(report) + "\n")
    else:
        sys.stdout.write(render_text(report) + "\n")

    # Diagnostics stay off the data stream: in JSON mode, stdout is exactly the
    # document; any notes are already inside collection_issues.
    return exit_code(report.complete, report.alerts, valid_args=True)


if __name__ == "__main__":
    sys.exit(main())
