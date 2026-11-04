"""Unit tests for NIC parsing and delta math (cross-platform).

Spec: cumulative RX drops 100 -> 100 must NOT alert (delta 0), while 100 -> 101
MUST alert at the default threshold (delta 1). A disappearing interface or a
counter reset must not produce a negative delta.
"""
import unittest

from linuxdiag.nic import compute_nic, parse_netdev


def line(name, rx_errs=0, rx_drop=0, tx_errs=0, tx_drop=0):
    rx = [0, 0, rx_errs, rx_drop, 0, 0, 0, 0]
    tx = [0, 0, tx_errs, tx_drop, 0, 0, 0, 0]
    return "%s: %s" % (name, " ".join(str(x) for x in rx + tx))


def compute(a_text, b_text, exclude=("lo",)):
    return compute_nic(parse_netdev(a_text), parse_netdev(b_text), exclude)


class ParseTests(unittest.TestCase):
    def test_extracts_counters_and_skips_headers(self):
        text = ("Inter-|   Receive        |  Transmit\n"
                " face |bytes packets errs drop ...|bytes packets errs drop ...\n"
                + line("eth0", rx_drop=2087) + "\n")
        d = parse_netdev(text)
        self.assertEqual(set(d), {"eth0"})
        self.assertEqual(d["eth0"]["rx_drops"], 2087)

    def test_tx_fields_coming_after_eight_rx(self):
        d = parse_netdev(line("eth0", tx_drop=7) + "\n")
        self.assertEqual(d["eth0"]["tx_drops"], 7)
        self.assertEqual(d["eth0"]["rx_drops"], 0)


class DeltaTests(unittest.TestCase):
    A = line("eth0", rx_drop=100) + "\n"

    def test_unchanged_counter_is_zero_not_alert(self):
        b = line("eth0", rx_drop=100) + "\n"
        s = compute(self.A, b)[0]
        self.assertEqual(s.rx_drops_cumulative, 100)
        self.assertTrue(s.rx_drops_delta.available)
        self.assertEqual(s.rx_drops_delta.value, 0.0)   # zero delta, available

    def test_increased_by_one_is_one(self):
        b = line("eth0", rx_drop=101) + "\n"
        s = compute(self.A, b)[0]
        self.assertEqual(s.rx_drops_delta.value, 1.0)   # alerts at default threshold 1

    def test_disappearing_interface_has_no_negative_delta(self):
        b = ""                                          # eth0 gone in snapshot B
        s = compute(self.A, b)[0]
        self.assertFalse(s.rx_drops_delta.available)
        self.assertIsNone(s.rx_drops_delta.value)        # not a negative number
        self.assertEqual(s.rx_drops_cumulative, 100)     # last known count retained

    def test_counter_reset_is_unavailable_not_negative(self):
        b = line("eth0", rx_drop=50) + "\n"              # 100 -> 50 (reset)
        s = compute(self.A, b)[0]
        self.assertFalse(s.rx_drops_delta.available)
        self.assertIsNone(s.rx_drops_delta.value)

    def test_loopback_excluded_by_default(self):
        text = (line("lo", rx_drop=999) + "\n" + line("eth0") + "\n")
        names = [s.name for s in compute(text, text)]
        self.assertNotIn("lo", names)
        self.assertIn("eth0", names)


if __name__ == "__main__":
    unittest.main()
