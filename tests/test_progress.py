"""Progress: lưu/đọc tiến độ, chịu được file thiếu hoặc hỏng."""

import json
import tempfile
import unittest
from pathlib import Path

from App.Game.progress import Progress


class ProgressFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "progress.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_file_means_empty_progress(self):
        pr = Progress(self.path)
        self.assertFalse(pr.is_cleared("A"))
        self.assertIsNone(pr.best("A"))

    def test_records_best_and_persists(self):
        pr = Progress(self.path)
        self.assertTrue(pr.record_win("A", 10))
        self.assertFalse(pr.record_win("A", 12))  # tệ hơn: không ghi đè
        self.assertTrue(pr.record_win("A", 8))
        again = Progress(self.path)
        self.assertEqual(again.best("A"), 8)
        self.assertTrue(again.is_cleared("A"))

    def test_corrupt_file_is_ignored(self):
        self.path.write_text("{not json", encoding="utf-8")
        pr = Progress(self.path)
        self.assertIsNone(pr.best("A"))
        self.assertTrue(pr.record_win("A", 3))  # và vẫn ghi lại được
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["best"], {"A": 3})

    def test_bad_values_are_dropped(self):
        self.path.write_text(json.dumps({"best": {"A": "x", "B": -4, "C": 7}}), encoding="utf-8")
        pr = Progress(self.path)
        self.assertEqual((pr.best("A"), pr.best("B"), pr.best("C")), (None, None, 7))


if __name__ == "__main__":
    unittest.main()
