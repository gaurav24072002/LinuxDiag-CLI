"""Unit tests for JSON and text rendering."""
import json
import unittest

from linuxdiag.model import (
    Alert,
    CpuSample,
    FilesystemSample,
    MemorySample,
    Report,
    Value,
)
from linuxdiag.render_json import render_json
from linuxdiag.render_text import render_text


def sample_report():
    return Report(
        schema_version=1,
        generated_at_utc="2026-01-01T00:00:00Z",
        hostname="gaurav",
        elapsed_seconds=2.01,
        complete=True,
        cpus=[
            CpuSample("aggregate", Value.number(10.0), Value.number(0.0), Value.number(0.0)),
            CpuSample("cpu3", Value.number(94.2), Value.number(0.0), Value.number(0.0)),
        ],
        memory=MemorySample(1000 * 1024, 500 * 1024, Value.number(50.0)),
        disks=[],
        filesystems=[FilesystemSample(
            "/", 421078953984, 214945282560, 204484988928,
            Value.number(49.1), 26181632, 591376, 25591626, Value.number(2.25))],
        nics=[],
        alerts=[Alert("cpu3", "busy_percent", 94.2, "percent", 90)],
        collection_issues=[],
    )


class JsonTests(unittest.TestCase):
    def test_is_one_parseable_object_with_expected_keys(self):
        doc = json.loads(render_json(sample_report()))
        self.assertIsInstance(doc, dict)
        self.assertEqual(
            set(doc),
            {"schema_version", "generated_at_utc", "hostname", "elapsed_seconds",
             "status", "metrics", "alerts", "collection_issues"},
        )

    def test_metrics_grouped_by_area(self):
        doc = json.loads(render_json(sample_report()))
        self.assertEqual(set(doc["metrics"]),
                         {"cpu", "memory", "disk", "filesystem", "nic"})

    def test_alert_object_has_all_five_fields(self):
        doc = json.loads(render_json(sample_report()))
        alert = doc["alerts"][0]
        self.assertEqual(set(alert), {"resource", "metric", "observed", "unit", "threshold"})
        self.assertEqual(alert["resource"], "cpu3")

    def test_unavailable_is_null_plus_reason(self):
        r = sample_report()
        r.cpus[0].busy = Value.unavailable("delta(total) was zero over the window")
        doc = json.loads(render_json(r))
        self.assertIsNone(doc["metrics"]["cpu"][0]["busy_percent"]["value"])
        self.assertEqual(doc["metrics"]["cpu"][0]["busy_percent"]["reason"],
                         "delta(total) was zero over the window")

    def test_nan_and_infinity_are_disallowed(self):
        r = sample_report()
        r.cpus[0].busy = Value(value=float("nan"))
        r.memory.used_percent = Value(value=float("inf"))
        out = render_json(r)
        self.assertNotIn("NaN", out)
        self.assertNotIn("Infinity", out)
        doc = json.loads(out)
        self.assertIsNone(doc["metrics"]["cpu"][0]["busy_percent"]["value"])
        self.assertIsNone(doc["metrics"]["memory"]["used_percent"]["value"])


class TextTests(unittest.TestCase):
    def test_leads_with_status_then_findings(self):
        text = render_text(sample_report())
        first = text.splitlines()[0]
        self.assertIn("status: alert", first)
        self.assertIn("FINDINGS", text)
        # Findings appear before the CPU table.
        self.assertLess(text.index("FINDINGS"), text.index("CPU "))

    def test_alert_line_is_specific(self):
        text = render_text(sample_report())
        self.assertIn("cpu3 busy 94.2% >= 90% over 2.01 s", text)

    def test_disk_context_note_when_present(self):
        from linuxdiag.model import DiskSample
        r = sample_report()
        r.disks = [DiskSample("sdb", Value.number(1.0), Value.number(0.5))]
        text = render_text(r)
        self.assertIn("context only", text)
        self.assertIn("sdb", text)

    def test_unavailable_renders_as_na(self):
        r = sample_report()
        r.cpus[1].busy = Value.unavailable("delta(total) negative (counters reset?)")
        text = render_text(r)
        self.assertIn("n/a", text)


if __name__ == "__main__":
    unittest.main()
