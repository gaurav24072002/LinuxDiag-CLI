"""Unit tests for CPU parsing and busy/iowait/steal math (cross-platform, no I/O).

The first test is the spec's exact fixture: delta user=20, system=10, idle=50,
iowait=15, steal=5, all other included fields zero, and a *nonzero* guest delta
to catch accidental double counting. Expected: busy=30%, iowait=15%, steal=5%.
"""
import unittest

from linuxdiag.cpu import compute_cpu, parse_stat_text


def stat_line(name, user, nice, system, idle, iowait, irq, softirq, steal,
              guest=0, guest_nice=0):
    return ("%s %d %d %d %d %d %d %d %d %d %d"
            % (name, user, nice, system, idle, iowait, irq, softirq, steal,
               guest, guest_nice))


def compute(a_text, b_text):
    return compute_cpu(parse_stat_text(a_text), parse_stat_text(b_text))


class ParseTests(unittest.TestCase):
    def test_extracts_aggregate_and_logical_cpus(self):
        text = ("cpu  1 2 3 4 5 6 7 8 9 10\n"
                "cpu0 1 2 3 4 5 6 7 8 9 10\n"
                "cpu1 1 2 3 4 5 6 7 8 9 10\n"
                "intr 0 0 0 0\nctxt 1\nbtime 1700000000\n")
        d = parse_stat_text(text)
        self.assertEqual(set(d), {"cpu", "cpu0", "cpu1"})

    def test_guest_fields_are_excluded(self):
        d = parse_stat_text(stat_line("cpu", 1, 2, 3, 4, 5, 6, 7, 8, guest=99, guest_nice=99) + "\n")
        # Exactly the 8 accounting fields; guest (99) must not be present.
        self.assertEqual(d["cpu"], (1, 2, 3, 4, 5, 6, 7, 8))


class SpecFixtureTests(unittest.TestCase):
    def setUp(self):
        a = stat_line("cpu", 0, 0, 0, 0, 0, 0, 0, 0) + "\n"
        b = (stat_line("cpu", 20, 0, 10, 50, 15, 0, 0, 5, guest=100) + "\n")
        self.agg = compute(a, b)[0]

    def test_names(self):
        self.assertEqual(self.agg.name, "aggregate")

    def test_busy_is_30(self):
        self.assertEqual(self.agg.busy.value, 30.0)

    def test_iowait_is_15(self):
        self.assertEqual(self.agg.iowait.value, 15.0)

    def test_steal_is_5(self):
        self.assertEqual(self.agg.steal.value, 5.0)

    def test_guest_delta_does_not_shift_busy(self):
        # A naive implementation that counts guest into `total` would report 15%.
        self.assertNotEqual(self.agg.busy.value, 15.0)
        self.assertEqual(self.agg.busy.value, 30.0)


class BusySingleQuietAggregateTests(unittest.TestCase):
    def test_one_cpu_busy_while_aggregate_is_quiet(self):
        a = (stat_line("cpu", 0, 0, 0, 0, 0, 0, 0, 0) + "\n" +
             stat_line("cpu3", 0, 0, 0, 0, 0, 0, 0, 0) + "\n")
        b = (stat_line("cpu", 10, 0, 0, 90, 0, 0, 0, 0) + "\n" +
             stat_line("cpu3", 94, 0, 0, 6, 0, 0, 0, 0) + "\n")
        samples = {s.name: s for s in compute(a, b)}
        self.assertEqual(samples["aggregate"].busy.value, 10.0)
        self.assertEqual(samples["cpu3"].busy.value, 94.0)
        # cpu3 crosses a 90 threshold while the aggregate does not.
        self.assertGreaterEqual(samples["cpu3"].busy.value, 90.0)
        self.assertLess(samples["aggregate"].busy.value, 90.0)


class ZeroDeltaTests(unittest.TestCase):
    def test_genuine_zero_busy_delta_is_available_zero(self):
        # Idle advanced (valid denominator) but no executing time: busy is 0.0.
        a = stat_line("cpu", 0, 0, 0, 0, 0, 0, 0, 0) + "\n"
        b = stat_line("cpu", 0, 0, 0, 50, 0, 0, 0, 0) + "\n"
        agg = compute(a, b)[0]
        self.assertTrue(agg.busy.available)
        self.assertEqual(agg.busy.value, 0.0)
        self.assertEqual(agg.iowait.value, 0.0)
        self.assertEqual(agg.steal.value, 0.0)

    def test_zero_total_delta_is_unavailable(self):
        a = stat_line("cpu", 5, 0, 5, 5, 5, 0, 0, 5) + "\n"
        b = stat_line("cpu", 5, 0, 5, 5, 5, 0, 0, 5) + "\n"  # nothing advanced
        agg = compute(a, b)[0]
        self.assertFalse(agg.busy.available)
        self.assertIn("zero", agg.busy.reason.lower())

    def test_counter_reset_is_unavailable_not_negative(self):
        a = stat_line("cpu", 100, 0, 100, 100, 0, 0, 0, 0) + "\n"
        b = stat_line("cpu", 50, 0, 50, 50, 0, 0, 0, 0) + "\n"
        agg = compute(a, b)[0]
        self.assertFalse(agg.busy.available)
        self.assertIsNotNone(agg.busy.reason)


class IowaitDecreaseTests(unittest.TestCase):
    def test_iowait_decrease_is_unavailable_but_busy_still_valid(self):
        # iowait falls 20 -> 15 (decrease) while idle rises: valid total, so
        # busy is computable but iowait's negative delta is not a rate.
        a = stat_line("cpu", 0, 0, 0, 0, 20, 0, 0, 0) + "\n"
        b = stat_line("cpu", 0, 0, 0, 100, 15, 0, 0, 0) + "\n"
        agg = compute(a, b)[0]
        self.assertFalse(agg.iowait.available)
        self.assertTrue(agg.busy.available)
        self.assertEqual(agg.busy.value, 0.0)


if __name__ == "__main__":
    unittest.main()
