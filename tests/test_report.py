"""Unit tests for the Value model and report status/exit-code rules."""
import unittest

from linuxdiag.model import Alert, CollectionIssue, Report, Value
from linuxdiag.report import (
    EXIT_ALERTS,
    EXIT_ERROR,
    EXIT_OK,
    build_report,
    exit_code,
    is_complete,
)


class ValueTests(unittest.TestCase):
    def test_zero_is_available_not_unavailable(self):
        v = Value.number(0.0)
        self.assertTrue(v.available)
        self.assertIsNone(v.reason)
        self.assertEqual(v.value, 0.0)

    def test_unavailable_has_reason_and_null_value(self):
        v = Value.unavailable("denominator was zero")
        self.assertFalse(v.available)
        self.assertIsNone(v.value)
        self.assertEqual(v.reason, "denominator was zero")

    def test_zero_json_is_number(self):
        self.assertEqual(Value.number(0.0).to_json(), {"value": 0.0, "reason": None})

    def test_unavailable_json_is_null_plus_reason(self):
        self.assertEqual(
            Value.unavailable("r").to_json(), {"value": None, "reason": "r"}
        )

    def test_number_helper_returns_default_when_unavailable(self):
        self.assertEqual(Value.unavailable("x").as_number(default=7.5), 7.5)


class ExitCodeTests(unittest.TestCase):
    def test_complete_no_alerts_is_zero(self):
        self.assertEqual(exit_code(True, []), EXIT_OK)

    def test_complete_with_alerts_is_one(self):
        self.assertEqual(exit_code(True, [Alert("cpu0", "busy_percent", 91, "percent", 90)]), EXIT_ALERTS)

    def test_incomplete_no_alerts_is_two(self):
        self.assertEqual(exit_code(False, []), EXIT_ERROR)

    def test_incomplete_with_alerts_still_two(self):
        alerts = [Alert("cpu0", "busy_percent", 91, "percent", 90)]
        self.assertEqual(exit_code(False, alerts), EXIT_ERROR)

    def test_invalid_args_is_two_even_if_clean(self):
        self.assertEqual(exit_code(True, [], valid_args=False), EXIT_ERROR)


class CompletenessTests(unittest.TestCase):
    def test_no_issues_is_complete(self):
        self.assertTrue(is_complete([]))

    def test_info_issue_stays_complete(self):
        issues = [CollectionIssue("block devices", "none", "no whole devices", "info")]
        self.assertTrue(is_complete(issues))

    def test_error_issue_breaks_completeness(self):
        issues = [CollectionIssue("/proc/stat", "read_failed", "gone", "error")]
        self.assertFalse(is_complete(issues))


class StatusTests(unittest.TestCase):
    def _report(self, complete, n_alerts=0):
        return build_report(
            generated_at_utc="2026-01-01T00:00:00Z",
            hostname="h",
            elapsed_seconds=1.0,
            cpus=[], memory=None, disks=[], filesystems=[], nics=[],
            issues=[],
            alerts=[Alert("cpu0", "busy_percent", 91, "percent", 90)] * n_alerts,
        ) if complete else build_report(
            generated_at_utc="2026-01-01T00:00:00Z",
            hostname="h",
            elapsed_seconds=1.0,
            cpus=[], memory=None, disks=[], filesystems=[], nics=[],
            issues=[CollectionIssue("/proc/stat", "read_failed", "gone", "error")],
            alerts=[Alert("cpu0", "busy_percent", 91, "percent", 90)] * n_alerts,
        )

    def test_ok_when_complete_and_quiet(self):
        self.assertEqual(self._report(True, 0).status, "ok")

    def test_alert_when_complete_and_crossed(self):
        self.assertEqual(self._report(True, 2).status, "alert")

    def test_incomplete_wins_over_alert(self):
        self.assertEqual(self._report(False, 2).status, "incomplete")


if __name__ == "__main__":
    unittest.main()
