"""Text rendering: lead with status and findings, then compact tables.

The spec wants status and findings first, then resource tables with names,
values, units, and the sample duration. Unavailable values render as ``n/a``.
Numbers are rounded here, for display only — thresholds already ran on the
unrounded values.
"""
from __future__ import annotations

from linuxdiag.model import Alert, Report, Value

_METRIC_LABEL = {
    "busy_percent": "busy",
    "iowait_percent": "iowait",
    "memory_used_percent": "memory used",
    "space_used_percent": "space used",
    "inode_used_percent": "inode used",
    "rx_errors_delta": "rx errors",
    "tx_errors_delta": "tx errors",
    "rx_drops_delta": "rx drops",
    "tx_drops_delta": "tx drops",
}


def _pct(value: Value) -> str:
    return "n/a" if not value.available else "%.1f%%" % value.value


def _rate(value: Value) -> str:
    return "n/a" if not value.available else "%.2f" % value.value


def _count(value: Value) -> str:
    return "n/a" if not value.available else str(int(round(value.value)))


def _alert_line(alert: Alert, elapsed: float) -> str:
    label = _METRIC_LABEL.get(alert.metric, alert.metric)
    if alert.unit == "percent":
        return "  - %s %s %.1f%% >= %g%% over %.2f s" % (
            alert.resource, label, alert.observed, alert.threshold, elapsed)
    return "  - %s %s %d >= %d over %.2f s" % (
        alert.resource, label, int(round(alert.observed)), int(round(alert.threshold)), elapsed)


def render_text(report: Report) -> str:
    lines = []
    lines.append(
        "linuxdiag — status: %s  (host: %s, window: %.2f s, %s)" % (
            report.status, report.hostname, report.elapsed_seconds, report.generated_at_utc)
    )
    lines.append("")

    # --- Status + findings first ---
    if report.alerts:
        lines.append("FINDINGS (%d):" % len(report.alerts))
        for alert in report.alerts:
            lines.append(_alert_line(alert, report.elapsed_seconds))
    else:
        lines.append("FINDINGS: none (no threshold crossed in this window)")
    lines.append("")

    if report.collection_issues:
        lines.append("COLLECTION ISSUES:")
        for issue in report.collection_issues:
            lines.append("  - [%s] %s: %s — %s" % (issue.severity, issue.resource, issue.issue, issue.detail))
        lines.append("")

    # --- CPU ---
    if report.cpus:
        lines.append("CPU (per logical CPU; busy = executing %; iowait/steal reported separately):")
        lines.append("  %-12s %8s %9s %8s" % ("NAME", "BUSY%", "IOWAIT%", "STEAL%"))
        for c in report.cpus:
            lines.append("  %-12s %8s %9s %8s" % (c.name, _pct(c.busy), _pct(c.iowait), _pct(c.steal)))
        lines.append("")

    # --- Memory ---
    if report.memory is not None:
        m = report.memory
        avail = "n/a" if m.available_bytes is None else str(m.available_bytes)
        lines.append("MEMORY:")
        lines.append("  total=%d B   available=%s B   used=%s" % (m.total_bytes, avail, _pct(m.used_percent)))
        lines.append("")

    # --- Disk (context only) ---
    if report.disks:
        lines.append("DISK (MiB/s; context only — a high MiB/s does not by itself mean a saturated disk):")
        lines.append("  %-12s %12s %12s" % ("DEVICE", "READ MiB/s", "WRITE MiB/s"))
        for d in report.disks:
            lines.append("  %-12s %12s %12s" % (d.name, _rate(d.read_mib_s), _rate(d.write_mib_s)))
        lines.append("")

    # --- Filesystems ---
    if report.filesystems:
        lines.append("FILESYSTEMS:")
        lines.append("  %-16s %12s %13s %14s" % ("PATH", "SPACE USED%", "INODE USED%", "AVAILABLE B"))
        for f in report.filesystems:
            lines.append("  %-16s %12s %13s %14s" % (
                f.path, _pct(f.space_used_percent), _pct(f.inode_used_percent), str(f.available_bytes)))
        lines.append("")

    # --- NIC ---
    if report.nics:
        def cc(delta: Value, cum: int) -> str:
            return "%s/%d" % (_count(delta), cum)
        lines.append("NIC (errors/drops; delta-over-window/cumulative):")
        lines.append("  %-10s %15s %15s %15s %15s" % (
            "IFACE", "RX ERR d/cum", "TX ERR d/cum", "RX DROP d/cum", "TX DROP d/cum"))
        for n in report.nics:
            lines.append("  %-10s %15s %15s %15s %15s" % (
                n.name,
                cc(n.rx_errors_delta, n.rx_errors_cumulative),
                cc(n.tx_errors_delta, n.tx_errors_cumulative),
                cc(n.rx_drops_delta, n.rx_drops_cumulative),
                cc(n.tx_drops_delta, n.tx_drops_cumulative)))
        lines.append("")

    return "\n".join(lines).rstrip("\n")
