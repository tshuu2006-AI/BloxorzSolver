"""Mọi màn trong levels/ phải nạp được và giải được bằng solver có sẵn."""

import unittest
from pathlib import Path

from App.Components.level_loader import LevelError, level_from_dict, load_levels
from App.Solvers.UCS_solver import UCSSolver

LEVELS_DIR = Path(__file__).resolve().parent.parent / "levels"


class LevelLoader(unittest.TestCase):
    def test_rejects_unknown_character(self):
        with self.assertRaises(LevelError):
            level_from_dict({"grid": ["S?G"]})

    def test_requires_one_start_and_goal(self):
        with self.assertRaises(LevelError):
            level_from_dict({"grid": ["S#"]})
        with self.assertRaises(LevelError):
            level_from_dict({"grid": ["SSG"]})

    def test_bridge_cell_must_belong_to_group(self):
        with self.assertRaises(LevelError):
            level_from_dict({"grid": ["S#B#G"]})

    def test_switch_needs_declaration(self):
        with self.assertRaises(LevelError):
            level_from_dict({"grid": ["S#o#G"]})

    def test_split_targets_validated(self):
        base = {"grid": ["S#p##", "#...#", "..G.."], "bridges": []}
        bad = dict(base, switches=[{"pos": [0, 2], "targets": [[1, 0], [1, 1]]}])
        with self.assertRaises(LevelError):
            level_from_dict(bad)  # kề nhau
        bad = dict(base, switches=[{"pos": [0, 2], "targets": [[1, 0], [2, 2]]}])
        with self.assertRaises(LevelError):
            level_from_dict(bad)  # trùng ô đích


class ShippedLevels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.levels = load_levels(LEVELS_DIR) if LEVELS_DIR.exists() else []

    def test_groups_and_names_are_valid_and_unique(self):
        known = {"simple", "fragile", "switch", "split", "combined"}
        self.assertTrue(self.levels)
        names = [lv.name for lv in self.levels]
        self.assertEqual(len(names), len(set(names)), "tên màn bị trùng")
        for lv in self.levels:
            self.assertIn(lv.group, known, lv.name)
            self.assertTrue(lv.description, f"{lv.name} thiếu mô tả")

    def test_every_level_is_solvable_and_replays(self):
        self.assertTrue(self.levels, "chưa có file màn chơi nào trong levels/")
        for level in self.levels:
            with self.subTest(level=level.name):
                problem = level.problem
                actions = UCSSolver().solve(problem)
                self.assertIsNotNone(actions, "không giải được")
                state = problem.initial_state
                for a in actions:
                    state = problem.result(state, a)
                    self.assertIsNotNone(state, f"hành động {a} làm rơi khối")
                self.assertTrue(problem.is_goal(state))


if __name__ == "__main__":
    unittest.main()
