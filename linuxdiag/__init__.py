"""linuxdiag — a read-only Linux compute & storage diagnostics CLI.

One short sample tells an operator whether a logical CPU is busy, iowait is
elevated, memory is low, a disk is moving data, a filesystem is running out of
blocks or inodes, or a network interface is accumulating errors or drops.

Standard library only. Read-only. Targets an unprivileged Linux user.
"""
from __future__ import annotations

__version__ = "0.1.0"
SCHEMA_VERSION = 1

__all__ = ["__version__", "SCHEMA_VERSION"]
