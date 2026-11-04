"""Unit tests for memory parsing and used-percent math (cross-platform).

The spec calls for a host with a low MemFree but substantial MemAvailable: the
used% must be low, proving we use MemAvailable (not MemFree) in the formula.
"""
import unittest

from linuxdiag.memory import compute_memory, parse_meminfo


class ParseTests(unittest.TestCase):
    def test_extracts_numeric_fields(self):
        mem = parse_meminfo("MemTotal:       1000000 kB\nMemFree:         1000 kB\n")
        self.assertEqual(mem["MemTotal"], 1000000)
        self.assertEqual(mem["MemFree"], 1000)

    def test_ignores_non_numeric(self):
        self.assertEqual(parse_meminfo("AnonHugePages:        0 kB\nfoo\n"), {"AnonHugePages": 0})


class UsedPercentTests(unittest.TestCase):
    def test_uses_memoavailable_not_memo_free(self):
        # Low MemFree (1000 kB) but high MemAvailable (900000 kB) => mostly free.
        mem = {"MemTotal": 1000000, "MemFree": 1000, "MemAvailable": 900000}
        s = compute_memory(mem)
        self.assertEqual(s.total_bytes, 1000000 * 1024)
        self.assertEqual(s.available_bytes, 900000 * 1024)
        self.assertEqual(s.used_percent.value, 10.0)
        # A MemFree-based formula would report 99.9% — make sure that is not us.
        self.assertNotAlmostEqual(s.used_percent.value, 99.9, places=2)

    def test_kib_converted_to_bytes(self):
        s = compute_memory({"MemTotal": 8, "MemAvailable": 4})
        self.assertEqual(s.total_bytes, 8 * 1024)
        self.assertEqual(s.available_bytes, 4 * 1024)
        self.assertEqual(s.used_percent.value, 50.0)

    def test_fully_used_is_100(self):
        s = compute_memory({"MemTotal": 100, "MemAvailable": 0})
        self.assertEqual(s.used_percent.value, 100.0)

    def test_missing_memoavailable_is_unavailable(self):
        s = compute_memory({"MemTotal": 1000000, "MemFree": 1000})
        self.assertIsNotNone(s)
        self.assertFalse(s.used_percent.available)
        self.assertIsNone(s.available_bytes)

    def test_missing_memtotal_yields_none(self):
        self.assertIsNone(compute_memory({"MemFree": 1000}))


if __name__ == "__main__":
    unittest.main()
