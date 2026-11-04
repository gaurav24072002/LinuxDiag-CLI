"""Configuration for linuxdiag.

A plain, explicit, validated dataclass. No hidden state: everything an operator
can set is a named field, and :func:`validate` turns each out-of-range value
into an actionable error message.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Tuple

DEFAULT_INTERVAL = 1.0
DEFAULT_MOUNTS: Tuple[str, ...] = ("/",)
DEFAULT_FORMAT = "text"

# Demo threshold defaults. These are starting points an operator overrides; they
# are intentionally simple, round numbers.
DEFAULT_WARN = {
    "warn_cpu_busy": 90.0,
    "warn_iowait": 20.0,
    "warn_memory_used": 90.0,
    "warn_space_used": 90.0,
    "warn_inodes_used": 90.0,
    "warn_nic_errors": 1,
    "warn_nic_drops": 1,
}

# Block device name prefixes that are not "real" whole disks: loopback, RAM
# disks, and CD-ROMs. Kept as prefixes so `loop10` matches `loop` too.
DEFAULT_SKIP_PREFIXES: Tuple[str, ...] = ("loop", "ram", "zram", "sr", "scd")

_PERCENT_FIELDS = (
    "warn_cpu_busy",
    "warn_iowait",
    "warn_memory_used",
    "warn_space_used",
    "warn_inodes_used",
)
_NIC_COUNT_FIELDS = ("warn_nic_errors", "warn_nic_drops")


class ConfigError(ValueError):
    """Raised when a configuration value is out of range or malformed."""


@dataclass
class Config:
    """Validated runtime configuration for a single linuxdiag run."""

    interval: float = DEFAULT_INTERVAL
    mounts: List[str] = field(default_factory=lambda: list(DEFAULT_MOUNTS))
    format: str = DEFAULT_FORMAT
    warn_cpu_busy: float = DEFAULT_WARN["warn_cpu_busy"]
    warn_iowait: float = DEFAULT_WARN["warn_iowait"]
    warn_memory_used: float = DEFAULT_WARN["warn_memory_used"]
    warn_space_used: float = DEFAULT_WARN["warn_space_used"]
    warn_inodes_used: float = DEFAULT_WARN["warn_inodes_used"]
    warn_nic_errors: int = DEFAULT_WARN["warn_nic_errors"]
    warn_nic_drops: int = DEFAULT_WARN["warn_nic_drops"]
    skip_prefixes: Tuple[str, ...] = DEFAULT_SKIP_PREFIXES


def _is_number(value: object) -> bool:
    """True for int/float but not bool (bool is an int subclass)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate(config: Config) -> Config:
    """Validate ranges and types, returning ``config`` for convenience.

    Raises :class:`ConfigError` with an actionable message naming the offending
    flag. Percentages must lie in ``[0, 100]``; NIC count thresholds must be
    positive integers; the interval must be a positive, finite number.
    """
    if (
        not _is_number(config.interval)
        or not math.isfinite(config.interval)
        or config.interval <= 0
    ):
        raise ConfigError(
            "--interval must be a positive, finite number of seconds (got %r)"
            % (config.interval,)
        )

    for name in _PERCENT_FIELDS:
        value = getattr(config, name)
        if (
            not _is_number(value)
            or not math.isfinite(value)
            or value < 0
            or value > 100
        ):
            raise ConfigError(
                "--%s must be a percentage in [0, 100] (got %r)"
                % (name.replace("_", "-"), value)
            )

    for name in _NIC_COUNT_FIELDS:
        value = getattr(config, name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigError(
                "--%s must be a positive integer (got %r)"
                % (name.replace("_", "-"), value)
            )

    if config.format not in ("text", "json"):
        raise ConfigError("--format must be 'text' or 'json' (got %r)" % (config.format,))

    if not config.mounts:
        raise ConfigError("at least one --mount PATH is required")
    for path in config.mounts:
        if not isinstance(path, str) or not path:
            raise ConfigError("each --mount PATH must be a non-empty string (got %r)" % (path,))

    return config
