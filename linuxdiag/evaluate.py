"""Threshold evaluation.

Inclusive (``value >= threshold``), operating on the *unrounded* observed value,
matching the spec's flag table. Unavailable values never alert. Disk throughput
is intentionally NOT evaluated — a high MiB/s figure alone does not identify a
saturated disk, so it is reported as context only.

    --warn-cpu-busy    aggregate or any logical CPU busy%  >= threshold
    --warn-iowait      aggregate or any logical CPU iowait% >= threshold
    --warn-memory-used memory used%                        >= threshold
    --warn-space-used  a requested filesystem space used%   >= threshold
    --warn-inodes-used a requested filesystem inode used%   >= threshold
    --warn-nic-errors  any per-interface error delta        >= threshold
    --warn-nic-drops   any per-interface drop delta         >= threshold
"""
from __future__ import annotations

from typing import List, Optional

from linuxdiag.config import Config
from linuxdiag.model import Alert, Report, Value


def _alert_if(value: Value, threshold, resource: str, metric: str, unit: str) -> Optional[Alert]:
    if not value.available:
        return None
    if value.value >= threshold:
        return Alert(
            resource=resource,
            metric=metric,
            observed=value.value,
            unit=unit,
            threshold=threshold,
        )
    return None


def evaluate(report: Report, config: Config) -> List[Alert]:
    """Produce the list of alerts for a collected report under a config."""
    alerts: List[Alert] = []

    for cpu in report.cpus:
        a = _alert_if(cpu.busy, config.warn_cpu_busy, cpu.name, "busy_percent", "percent")
        if a:
            alerts.append(a)
        a = _alert_if(cpu.iowait, config.warn_iowait, cpu.name, "iowait_percent", "percent")
        if a:
            alerts.append(a)

    if report.memory is not None:
        a = _alert_if(
            report.memory.used_percent, config.warn_memory_used,
            "memory", "memory_used_percent", "percent",
        )
        if a:
            alerts.append(a)

    for fs in report.filesystems:
        a = _alert_if(
            fs.space_used_percent, config.warn_space_used,
            fs.path, "space_used_percent", "percent",
        )
        if a:
            alerts.append(a)
        a = _alert_if(
            fs.inode_used_percent, config.warn_inodes_used,
            fs.path, "inode_used_percent", "percent",
        )
        if a:
            alerts.append(a)

    for nic in report.nics:
        for metric, value in (
            ("rx_errors_delta", nic.rx_errors_delta),
            ("tx_errors_delta", nic.tx_errors_delta),
        ):
            a = _alert_if(value, config.warn_nic_errors, nic.name, metric, "count")
            if a:
                alerts.append(a)
        for metric, value in (
            ("rx_drops_delta", nic.rx_drops_delta),
            ("tx_drops_delta", nic.tx_drops_delta),
        ):
            a = _alert_if(value, config.warn_nic_drops, nic.name, metric, "count")
            if a:
                alerts.append(a)

    return alerts
