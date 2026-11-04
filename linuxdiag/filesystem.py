"""Filesystem capacity via os.statvfs.

For each requested mount path we report:
  * space: total / used / available bytes and a df-style used%.
  * inodes: total / used / free and an inode used%.

Block bytes use ``f_frsize`` (the fundamental block size), as df does.

Space used% (df-style):
    used_blocks   = f_blocks - f_bfree
    space_used%   = used_blocks / (used_blocks + f_bavail)
Using ``f_bavail`` (not ``f_bfree``) for the free side is what makes this match
df: ``f_bfree - f_bavail`` are root-reserved blocks, so an unprivileged user
cannot actually use them.

Inode used%:
    inode_used% = (f_files - f_ffree) / f_files
A filesystem that reports ``f_files == 0`` has no meaningful inode count (some
network/tmp filesystems); we mark inode used% unavailable rather than dividing
by zero.
"""
from __future__ import annotations

import os
from typing import Dict

from linuxdiag.model import FilesystemSample, Value


def read_statvfs(path: str) -> Dict:
    """Run os.statvfs on ``path`` and return the fields we need (plus path).

    Raises OSError (e.g. ENOENT) if the path does not exist — the caller turns
    that into a per-path collection issue and keeps the other mounts reporting.
    """
    s = os.statvfs(path)
    return {
        "path": path,
        "f_frsize": s.f_frsize,
        "f_blocks": s.f_blocks,
        "f_bfree": s.f_bfree,
        "f_bavail": s.f_bavail,
        "f_files": s.f_files,
        "f_ffree": s.f_ffree,
    }


def compute_filesystem(data: Dict) -> FilesystemSample:
    """Derive bytes, space used%, and inode used% from a statvfs field dict."""
    frsize = data.get("f_frsize") or 0
    f_blocks = data.get("f_blocks", 0)
    f_bfree = data.get("f_bfree", 0)
    f_bavail = data.get("f_bavail", 0)

    total_bytes = frsize * f_blocks
    used_blocks = f_blocks - f_bfree
    used_bytes = frsize * used_blocks
    available_bytes = frsize * f_bavail

    denom = used_blocks + f_bavail
    if denom <= 0:
        space_used = Value.unavailable("no usable blocks reported by statvfs")
    else:
        space_used = Value.number(100.0 * used_blocks / denom)

    f_files = data.get("f_files", 0)
    f_ffree = data.get("f_ffree", 0)
    if f_files <= 0:
        inode_used_pct = Value.unavailable("filesystem reports no inode count")
    else:
        inode_used_pct = Value.number(100.0 * (f_files - f_ffree) / f_files)

    return FilesystemSample(
        path=data.get("path", ""),
        total_bytes=total_bytes,
        used_bytes=used_bytes,
        available_bytes=available_bytes,
        space_used_percent=space_used,
        inode_total=f_files,
        inode_used=f_files - f_ffree,
        inode_free=f_ffree,
        inode_used_percent=inode_used_pct,
    )
