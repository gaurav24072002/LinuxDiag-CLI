"""Unit tests for threshold evaluation (inclusive, unrounded, per flag table)."""
import unittest

from linuxdiag.config import Config
from linuxdiag.evaluate import evaluate
from linuxdiag.model import (
    CpuSample,
    FilesystemSample,
    MemorySample,
    NicSample,
    Report,
    Value,
)


def base_report(**kw):
    return Report(
        schema_version=1,
        generated_at_utc="2026-01-01T00:00:00Z",
        hostname="h",
        elapsed_seconds=2.01,
        complete=True,
        **kw,
    )


def cpu(name, busy, iowait=0.0, steal=0.0):
    return CpuSample(name=name, busy=Value.number(busy),
                     iowait=Value.number(iowait), steal=Value.number(steal))


class CpuThresholdTests(unittest.TestCase):
    def test_inclusive_boundary_alerts(self):
        r = base_report(cpus=[cpu("cpu3", 90.0)])
        alerts = evaluate(r, Config(warn_cpu_busy=90))
        self.assertTrue(any(a.metric == "busy_percent" and a.resource == "cpu3" for a in alerts))

    def test_just_below_does_not_alert(self):
        r = base_report(cpus=[cpu("cpu3", 89.999)])
        alerts = evaluate(r, Config(warn_cpu_busy=90))
        self.assertFalse(any(a.metric == "busy_percent" for a in alerts))

    def test_one_cpu_over_while_aggregate_below(self):
        r = base_report(cpus=[cpu("aggregate", 10.0), cpu("cpu3", 94.2)])
        alerts = [a for a in evaluate(r, Config(warn_cpu_busy=90)) if a.metric == "busy_percent"]
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].resource, "cpu3")

    def test_iowait_threshold_is_independent(self):
        r = base_report(cpus=[cpu("cpu0", busy=10.0, iowait=25.0)])
        alerts = evaluate(r, Config(warn_cpu_busy=90, warn_iowait=20))
        self.assertTrue(any(a.metric == "iowait_percent" for a in alerts))
        self.assertFalse(any(a.metric == "busy_percent" for a in alerts))

    def test_unavailable_value_does_not_alert(self):
        c = CpuSample("cpu0", busy=Value.unavailable("x"), iowait=Value.number(0), steal=Value.number(0))
        alerts = evaluate(base_report(cpus=[c]), Config(warn_cpu_busy=0))
        self.assertFalse(any(a.metric == "busy_percent" for a in alerts))


class MemoryThresholdTests(unittest.TestCase):
    def test_memory_crossing(self):
        r = base_report(memory=MemorySample(1000, 50, Value.number(95.0)))
        self.assertTrue(any(a.metric == "memory_used_percent"
                            for a in evaluate(r, Config(warn_memory_used=90))))

    def test_memory_below(self):
        r = base_report(memory=MemorySample(1000, 90, Value.number(89.9)))
        self.assertFalse(any(a.metric == "memory_used_percent"
                             for a in evaluate(r, Config(warn_memory_used=90))))


class FilesystemThresholdTests(unittest.TestCase):
    def fs(self, space, inode):
        return FilesystemSample("/x", 100, 95, 5, Value.number(space),
                                1000, 950, 50, Value.number(inode))

    def test_space_and_inode_are_separate(self):
        r = base_report(filesystems=[self.fs(space=95.0, inode=10.0)])
        alerts = evaluate(r, Config(warn_space_used=90, warn_inodes_used=90))
        self.assertTrue(any(a.metric == "space_used_percent" for a in alerts))
        self.assertFalse(any(a.metric == "inode_used_percent" for a in alerts))


class NicThresholdTests(unittest.TestCase):
    def nic(self, rx_err=0.0, tx_err=0.0, rx_drop=0.0, tx_drop=0.0):
        return NicSample(
            "eth0",
            rx_errors_cumulative=0, rx_errors_delta=Value.number(rx_err),
            tx_errors_cumulative=0, tx_errors_delta=Value.number(tx_err),
            rx_drops_cumulative=0, rx_drops_delta=Value.number(rx_drop),
            tx_drops_cumulative=0, tx_drops_delta=Value.number(tx_drop),
        )

    def test_drop_delta_alerts_error_does_not(self):
        r = base_report(nics=[self.nic(rx_drop=1.0)])
        alerts = evaluate(r, Config(warn_nic_errors=1, warn_nic_drops=1))
        self.assertTrue(any(a.metric == "rx_drops_delta" for a in alerts))
        self.assertFalse(any(a.metric == "rx_errors_delta" for a in alerts))

    def test_zero_delta_does_not_alert(self):
        r = base_report(nics=[self.nic(rx_drop=0.0, tx_err=0.0)])
        alerts = evaluate(r, Config(warn_nic_errors=1, warn_nic_drops=1))
        self.assertEqual(alerts, [])

    def test_each_direction_independent(self):
        r = base_report(nics=[self.nic(tx_drop=1.0, rx_drop=0.0)])
        alerts = evaluate(r, Config(warn_nic_drops=1))
        self.assertTrue(any(a.metric == "tx_drops_delta" for a in alerts))
        self.assertFalse(any(a.metric == "rx_drops_delta" for a in alerts))


if __name__ == "__main__":
    unittest.main()
