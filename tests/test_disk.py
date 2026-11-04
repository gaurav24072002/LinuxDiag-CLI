"""Unit tests for disk parsing, whole-device selection, and MiB/s math.

The core test is the spec's exact fixture: over exactly 2 seconds, 4096 extra
read sectors and 2048 extra write sectors must yield 1.0 MiB/s read and 0.5
MiB/s write. Plus zero-activity, zero-elapsed, and counter-reset cases.
"""
import sys
import unittest

from linuxdiag.disk import (
    DEFAULT_SKIP_PREFIXES,
    compute_disk,
    list_sysfs_whole_devices,
    parse_diskstats,
    select_whole_devices,
)


def line(name, sectors_read, sectors_written):
    # 10 fields: major minor name reads merged sectors_read ms writes merged sectors_written
    return " 259   0 %s 0 0 %d 0 0 0 %d" % (name, sectors_read, sectors_written)


class ParseTests(unittest.TestCase):
    def test_extracts_sectors(self):
        d = parse_diskstats(line("sdb", 12345, 6789) + "\n")
        self.assertEqual(d["sdb"], (12345, 6789))

    def test_ignores_short_lines(self):
        self.assertEqual(parse_diskstats("garbage\n\n"), {})


class SelectionTests(unittest.TestCase):
    ALL = {"sda", "sda1", "sdb", "sdb1", "loop0", "loop10", "ram0", "sr0",
           "dm-0", "nvme0n1", "nvme0n1p1"}
    SYSFS_WHOLE = {"sda", "sdb", "loop0", "loop10", "ram0", "sr0", "dm-0", "nvme0n1"}

    def test_keeps_real_and_stacked_whole_devices(self):
        sel = select_whole_devices(self.ALL, self.SYSFS_WHOLE, DEFAULT_SKIP_PREFIXES)
        for keep in ("sda", "sdb", "dm-0", "nvme0n1"):
            self.assertIn(keep, sel)

    def test_drops_partitions(self):
        sel = select_whole_devices(self.ALL, self.SYSFS_WHOLE, DEFAULT_SKIP_PREFIXES)
        self.assertNotIn("sda1", sel)
        self.assertNotIn("nvme0n1p1", sel)

    def test_skips_loop_ram_cd(self):
        sel = select_whole_devices(self.ALL, self.SYSFS_WHOLE, DEFAULT_SKIP_PREFIXES)
        for skip in ("loop0", "loop10", "ram0", "sr0"):
            self.assertNotIn(skip, sel)

    def test_empty_when_no_eligible_devices(self):
        sel = select_whole_devices({"loop0", "ram0"}, {"loop0", "ram0"}, DEFAULT_SKIP_PREFIXES)
        self.assertEqual(sel, [])


class RateTests(unittest.TestCase):
    def test_spec_fixture_1_and_0_5(self):
        a = parse_diskstats(line("sdb", 0, 0) + "\n")
        b = parse_diskstats(line("sdb", 4096, 2048) + "\n")
        s = compute_disk(a, b, 2.0, ["sdb"])[0]
        self.assertEqual(s.read_mib_s.value, 1.0)
        self.assertEqual(s.write_mib_s.value, 0.5)

    def test_zero_activity_is_available_zero(self):
        a = parse_diskstats(line("sdb", 100, 100) + "\n")
        b = parse_diskstats(line("sdb", 100, 100) + "\n")
        s = compute_disk(a, b, 2.0, ["sdb"])[0]
        self.assertTrue(s.read_mib_s.available)
        self.assertEqual(s.read_mib_s.value, 0.0)
        self.assertEqual(s.write_mib_s.value, 0.0)

    def test_zero_elapsed_is_unavailable(self):
        a = parse_diskstats(line("sdb", 0, 0) + "\n")
        b = parse_diskstats(line("sdb", 4096, 4096) + "\n")
        s = compute_disk(a, b, 0.0, ["sdb"])[0]
        self.assertFalse(s.read_mib_s.available)
        self.assertIsNotNone(s.read_mib_s.reason)

    def test_counter_reset_is_unavailable_not_negative(self):
        a = parse_diskstats(line("sdb", 1000, 1000) + "\n")
        b = parse_diskstats(line("sdb", 500, 500) + "\n")
        s = compute_disk(a, b, 2.0, ["sdb"])[0]
        self.assertFalse(s.read_mib_s.available)
        self.assertFalse(s.write_mib_s.available)

    def test_device_appearing_between_samples_is_unavailable(self):
        a = parse_diskstats(line("sdb", 0, 0) + "\n")
        b = parse_diskstats(line("sdc", 10, 10) + "\n")
        by = {s.name: s for s in compute_disk(a, b, 2.0, ["sdb", "sdc"])}
        self.assertFalse(by["sdb"].read_mib_s.available)   # gone in B
        self.assertFalse(by["sdc"].read_mib_s.available)   # absent in A


@unittest.skipUnless(sys.platform == "linux", "requires a Linux /sys/block")
class LiveSysfsTests(unittest.TestCase):
    def test_selected_devices_respect_the_filter(self):
        import linuxdiag.disk as disk
        whole = list_sysfs_whole_devices()
        text = disk.read_diskstats()
        names = select_whole_devices(set(parse_diskstats(text)), whole, DEFAULT_SKIP_PREFIXES)
        for name in names:
            self.assertIn(name, whole)
            self.assertFalse(any(name.startswith(p) for p in DEFAULT_SKIP_PREFIXES))


if __name__ == "__main__":
    unittest.main()
