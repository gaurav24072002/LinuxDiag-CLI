"""Unit tests for filesystem capacity math (cross-platform, pure compute).

Covers reserved blocks (f_bfree > f_bavail), high inode use with plenty of
bytes free, and filesystems that report no inode count.
"""
import unittest

from linuxdiag.filesystem import compute_filesystem, read_statvfs


class ReservedBlockTests(unittest.TestCase):
    def test_space_used_uses_bavail_not_bfree(self):
        # 100 blocks are root-reserved: f_bfree=500 but f_bavail=400.
        data = {"path": "/", "f_frsize": 4096,
                "f_blocks": 1000, "f_bfree": 500, "f_bavail": 400,
                "f_files": 100, "f_ffree": 80}
        s = compute_filesystem(data)
        # used_blocks=500; denom=500+400=900 => 55.56%, not the naive 50%.
        self.assertAlmostEqual(s.space_used_percent.value, 100.0 * 500 / 900, places=6)
        self.assertNotAlmostEqual(s.space_used_percent.value, 50.0, places=2)
        self.assertEqual(s.used_bytes, 500 * 4096)
        self.assertEqual(s.available_bytes, 400 * 4096)   # unprivileged available
        self.assertEqual(s.total_bytes, 1000 * 4096)

    def test_no_reserved_blocks_is_plain_ratio(self):
        data = {"path": "/", "f_frsize": 512,
                "f_blocks": 1000, "f_bfree": 250, "f_bavail": 250,
                "f_files": 1000, "f_ffree": 100}
        s = compute_filesystem(data)
        self.assertAlmostEqual(s.space_used_percent.value, 75.0, places=6)


class InodeTests(unittest.TestCase):
    def test_high_inode_use_with_bytes_free(self):
        data = {"path": "/x", "f_frsize": 4096,
                "f_blocks": 100000, "f_bfree": 90000, "f_bavail": 90000,
                "f_files": 1000, "f_ffree": 50}
        s = compute_filesystem(data)
        self.assertEqual(s.inode_used_percent.value, 95.0)   # (1000-50)/1000
        self.assertLess(s.space_used_percent.value, 15.0)    # plenty of bytes free
        self.assertEqual(s.inode_total, 1000)
        self.assertEqual(s.inode_used, 950)
        self.assertEqual(s.inode_free, 50)

    def test_no_inode_count_is_unavailable_but_space_still_valid(self):
        data = {"path": "/y", "f_frsize": 4096,
                "f_blocks": 100, "f_bfree": 50, "f_bavail": 50,
                "f_files": 0, "f_ffree": 0}
        s = compute_filesystem(data)
        self.assertFalse(s.inode_used_percent.available)
        self.assertIsNotNone(s.inode_used_percent.reason)
        self.assertTrue(s.space_used_percent.available)
        self.assertEqual(s.space_used_percent.value, 50.0)


class ReadStatvfsTests(unittest.TestCase):
    def test_existing_path_returns_fields(self):
        data = read_statvfs("/")
        self.assertEqual(data["path"], "/")
        self.assertIn("f_frsize", data)
        self.assertGreaterEqual(data["f_blocks"], 0)

    def test_missing_path_raises_oserror(self):
        with self.assertRaises(OSError):
            read_statvfs("/nonexistent/path/linuxdiag_does_not_exist")


if __name__ == "__main__":
    unittest.main()
