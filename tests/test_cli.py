"""CLI tests: arg validation, exit codes, JSON shape, missing+healthy mounts.

The collector is injected so these run cross-platform (no /proc, no sleeping).
"""
import contextlib
import io
import json
import unittest

from linuxdiag import cli
from linuxdiag.model import CollectionIssue, CpuSample, FilesystemSample, Value
from linuxdiag.report import EXIT_ALERTS, EXIT_ERROR, EXIT_OK


def healthy_fs(path):
    return FilesystemSample(path, 100 * 1024, 50 * 1024, 50 * 1024,
                            Value.number(50.0), 1000, 50, 950, Value.number(5.0))


def make_collector(cpus=(), issues=(), missing=frozenset(), memory=None):
    def collector(config):
        fs, all_issues = [], list(issues)
        for path in config.mounts:
            if path in missing:
                all_issues.append(CollectionIssue(path, "statvfs_failed",
                                                  "No such file or directory", "error"))
            else:
                fs.append(healthy_fs(path))
        return {"cpus": list(cpus), "memory": memory, "disks": [], "filesystems": fs,
                "nics": [], "issues": all_issues, "elapsed_seconds": 2.01}
    return collector


def run(argv, collector=None):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main(argv, collector=collector)
    return code, out.getvalue(), err.getvalue()


EXPECTED_KEYS = {"schema_version", "generated_at_utc", "hostname", "elapsed_seconds",
                 "status", "metrics", "alerts", "collection_issues"}


class JsonOutputTests(unittest.TestCase):
    def test_one_parseable_document(self):
        code, out, _ = run(["--format", "json", "--mount", "/"], make_collector())
        doc = json.loads(out)          # raises if not exactly one JSON object
        self.assertEqual(code, EXIT_OK)
        self.assertEqual(set(doc), EXPECTED_KEYS)


class ExitCodeTests(unittest.TestCase):
    def test_zero_when_complete_and_quiet(self):
        code, _, _ = run(["--format", "json"], make_collector(
            cpus=[CpuSample("cpu0", Value.number(10.0), Value.number(0.0), Value.number(0.0))]))
        self.assertEqual(code, EXIT_OK)

    def test_one_when_complete_with_alert(self):
        code, _, _ = run(["--format", "json"], make_collector(
            cpus=[CpuSample("cpu3", Value.number(95.0), Value.number(0.0), Value.number(0.0))]))
        self.assertEqual(code, EXIT_ALERTS)

    def test_two_when_incomplete(self):
        code, _, _ = run(["--format", "json"], make_collector(
            issues=[CollectionIssue("/proc/stat", "read_failed", "gone", "error")]))
        self.assertEqual(code, EXIT_ERROR)

    def test_incomplete_retains_valid_alerts_and_still_two(self):
        code, out, _ = run(["--format", "json"], make_collector(
            cpus=[CpuSample("cpu3", Value.number(95.0), Value.number(0.0), Value.number(0.0))],
            issues=[CollectionIssue("/proc/stat", "read_failed", "gone", "error")]))
        doc = json.loads(out)
        self.assertEqual(code, EXIT_ERROR)                 # precedence
        self.assertTrue(any(a["metric"] == "busy_percent" for a in doc["alerts"]))
        self.assertEqual(doc["status"], "incomplete")


class MissingAndHealthyMountTests(unittest.TestCase):
    def test_healthy_reports_missing_is_issue_exit_two(self):
        code, out, _ = run(
            ["--format", "json", "--mount", "/", "--mount", "/definitely/missing"],
            make_collector(missing=frozenset({"/definitely/missing"})))
        doc = json.loads(out)
        self.assertEqual(code, EXIT_ERROR)
        self.assertTrue(any(f["path"] == "/" for f in doc["metrics"]["filesystem"]))
        self.assertTrue(any(i["resource"] == "/definitely/missing" and i["severity"] == "error"
                            for i in doc["collection_issues"]))


class InvalidInputTests(unittest.TestCase):
    def test_zero_interval_is_actionable(self):
        code, _, err = run(["--interval", "0"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("interval", err)

    def test_over_100_percent_is_actionable(self):
        code, _, err = run(["--warn-cpu-busy", "150"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("warn-cpu-busy", err)

    def test_zero_nic_count_is_actionable(self):
        code, _, err = run(["--warn-nic-errors", "0"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("warn-nic-errors", err)

    def test_non_numeric_interval_is_actionable(self):
        code, _, err = run(["--interval", "abc"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("interval", err)

    def test_bad_format_is_actionable(self):
        code, _, err = run(["--format", "yaml"])
        self.assertEqual(code, EXIT_ERROR)
        self.assertIn("format", err)


class HelpTests(unittest.TestCase):
    def test_help_exits_zero(self):
        code, out, _ = run(["--help"])
        self.assertEqual(code, 0)
        self.assertIn("linuxdiag", out)


if __name__ == "__main__":
    unittest.main()
