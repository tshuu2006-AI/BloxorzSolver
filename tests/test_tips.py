"""tips.py: cơ chế mỗi màn dùng và gợi ý nào đến lượt."""

import unittest
from pathlib import Path

from App.Components.level_loader import load_levels
from App.Game.tips import ORDER, TIPS, mechanics, tip_for

ROOT = Path(__file__).resolve().parent.parent
LV = {lv.name: lv for lv in load_levels(ROOT / "levels", "custom")}
CL = {lv.name: lv for lv in load_levels(ROOT / "levels" / "classic", "classic")}


class Mechanics(unittest.TestCase):
    def test_detects_each_mechanic(self):
        self.assertEqual(mechanics(LV["First Roll"]), set())
        self.assertEqual(mechanics(LV["Thin Ice"]), {"fragile"})
        self.assertEqual(mechanics(LV["Soft Touch"]), {"switch"})
        self.assertEqual(mechanics(LV["Heavy Duty"]), {"heavy"})
        self.assertEqual(mechanics(LV["Split and Merge"]), {"split", "switch"})
        self.assertEqual(mechanics(LV["The Gauntlet"]), {"fragile", "switch", "heavy", "split"})

    def test_every_tip_has_text_and_every_key_is_ordered(self):
        self.assertEqual(set(ORDER), set(TIPS))
        for title, body in TIPS.values():
            self.assertTrue(title and len(body) > 20)


class TipFor(unittest.TestCase):
    def test_basics_comes_first_on_any_level(self):
        self.assertEqual(tip_for(LV["First Roll"], []), "basics")
        self.assertEqual(tip_for(LV["Thin Ice"], []), "basics")

    def test_after_basics_the_levels_mechanics_follow_in_order(self):
        gauntlet = LV["The Gauntlet"]
        seen = ["basics"]
        order = []
        while True:
            key = tip_for(gauntlet, seen)
            if key is None:
                break
            order.append(key)
            seen.append(key)
        self.assertEqual(order, ["fragile", "switch", "heavy", "split"])

    def test_nothing_is_due_for_a_plain_level_once_basics_are_seen(self):
        self.assertIsNone(tip_for(CL["Classic 01"], ["basics"]))

    def test_already_seen_mechanics_are_skipped(self):
        self.assertIsNone(tip_for(LV["Thin Ice"], ["basics", "fragile"]))
        self.assertEqual(tip_for(LV["Heavy Duty"], ["basics", "switch"]), "heavy")


if __name__ == "__main__":
    unittest.main()
