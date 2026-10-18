"""Settings: mặc định, lưu/đọc, file hỏng, kiểm tra giá trị."""

import json
import tempfile
import unittest
from pathlib import Path

from App.Game.settings import DEFAULTS, Settings


class SettingsFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_when_file_missing(self):
        s = Settings(self.path)
        for key, value in DEFAULTS.items():
            self.assertEqual(getattr(s, key), value)
        self.assertFalse(s.show_link_lines)  # tắt mặc định
        self.assertTrue(s.show_tips)

    def test_set_persists_and_reloads(self):
        s = Settings(self.path)
        s.set("show_link_lines", True)
        s.set("astar_heuristic", "manhattan")
        s.set("replay_speed", 3)
        again = Settings(self.path)
        self.assertTrue(again.show_link_lines)
        self.assertEqual(again.astar_heuristic, "manhattan")
        self.assertEqual(again.replay_speed, 3.0)

    def test_numbers_are_clamped(self):
        s = Settings(self.path)
        s.set("tilt_deg", 400)
        s.set("replay_speed", 0)
        self.assertEqual(s.tilt_deg, 45.0)
        self.assertEqual(s.replay_speed, 0.5)

    def test_invalid_assignments_are_rejected(self):
        s = Settings(self.path)
        with self.assertRaises(ValueError):
            s.set("show_tips", "yes")
        with self.assertRaises(ValueError):
            s.set("replay_speed", "fast")
        with self.assertRaises(KeyError):
            s.set("nope", 1)

    def test_corrupt_or_wrong_typed_file_falls_back(self):
        self.path.write_text("{oops", encoding="utf-8")
        self.assertEqual(Settings(self.path).show_compass, True)
        self.path.write_text(json.dumps({"show_compass": "no", "tilt_deg": 20, "extra": 1, "tips_seen": [1, "a"]}), encoding="utf-8")
        s = Settings(self.path)
        self.assertTrue(s.show_compass)       # sai kiểu: giữ mặc định
        self.assertEqual(s.tilt_deg, 20.0)    # đúng kiểu: dùng
        self.assertEqual(s.tips_seen, ["a"])  # lọc phần tử sai kiểu

    def test_tips_seen_helpers(self):
        s = Settings(self.path)
        s.mark_tip_seen("fragile")
        s.mark_tip_seen("fragile")
        self.assertEqual(s.tips_seen, ["fragile"])
        self.assertEqual(Settings(self.path).tips_seen, ["fragile"])
        s.reset_tips()
        self.assertEqual(Settings(self.path).tips_seen, [])

    def test_defaults_are_not_shared_between_instances(self):
        a, b = Settings(self.path), Settings(Path(self.tmp.name) / "other.json")
        a.mark_tip_seen("x")
        self.assertEqual(b.tips_seen, [])
        self.assertEqual(DEFAULTS["tips_seen"], [])


if __name__ == "__main__":
    unittest.main()
