"""Unit tests for configuration validation (cross-platform, no I/O)."""
import unittest

from linuxdiag.config import Config, ConfigError, validate


def make(**kw):
    return validate(Config(**kw))


class IntervalTests(unittest.TestCase):
    def test_default_interval_is_one_second(self):
        self.assertEqual(make().interval, 1.0)

    def test_valid_interval(self):
        self.assertEqual(make(interval=2.0).interval, 2.0)

    def test_zero_interval_rejected(self):
        with self.assertRaises(ConfigError):
            make(interval=0)

    def test_negative_interval_rejected(self):
        with self.assertRaises(ConfigError):
            make(interval=-1)

    def test_nan_interval_rejected(self):
        with self.assertRaises(ConfigError):
            make(interval=float("nan"))

    def test_infinite_interval_rejected(self):
        with self.assertRaises(ConfigError):
            make(interval=float("inf"))


class PercentThresholdTests(unittest.TestCase):
    def test_zero_is_a_valid_bound(self):
        self.assertEqual(make(warn_cpu_busy=0).warn_cpu_busy, 0)

    def test_100_is_a_valid_bound(self):
        self.assertEqual(make(warn_iowait=100).warn_iowait, 100)

    def test_negative_percent_rejected(self):
        with self.assertRaises(ConfigError):
            make(warn_memory_used=-1)

    def test_over_100_percent_rejected(self):
        with self.assertRaises(ConfigError):
            make(warn_inodes_used=101)

    def test_nan_percent_rejected(self):
        with self.assertRaises(ConfigError):
            make(warn_space_used=float("nan"))


class NicCountThresholdTests(unittest.TestCase):
    def test_positive_int_is_valid(self):
        self.assertEqual(make(warn_nic_errors=5).warn_nic_errors, 5)

    def test_zero_rejected(self):
        with self.assertRaises(ConfigError):
            make(warn_nic_errors=0)

    def test_negative_rejected(self):
        with self.assertRaises(ConfigError):
            make(warn_nic_drops=-1)


class MountsAndFormatTests(unittest.TestCase):
    def test_default_mount_is_root(self):
        self.assertEqual(make().mounts, ["/"])

    def test_multiple_mounts_preserved_in_order(self):
        self.assertEqual(make(mounts=["/", "/var"]).mounts, ["/", "/var"])

    def test_empty_mounts_rejected(self):
        with self.assertRaises(ConfigError):
            make(mounts=[])

    def test_default_format_is_text(self):
        self.assertEqual(make().format, "text")

    def test_json_format_accepted(self):
        self.assertEqual(make(format="json").format, "json")

    def test_unknown_format_rejected(self):
        with self.assertRaises(ConfigError):
            make(format="yaml")


if __name__ == "__main__":
    unittest.main()
