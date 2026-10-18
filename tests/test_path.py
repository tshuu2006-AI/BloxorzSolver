"""path.py: các bước của lời giải để vẽ lớp phủ đường đi."""

import unittest
from pathlib import Path

from App.Components.level_loader import load_levels
from App.Game.path import path_steps, replay_states
from App.Solvers.UCS_solver import UCSSolver

LEVELS = {lv.name: lv for lv in load_levels(Path(__file__).resolve().parent.parent / "levels")}


class PathSteps(unittest.TestCase):
    def test_states_and_steps_line_up_with_the_actions(self):
        lv = LEVELS["First Roll"]
        actions = UCSSolver().solve(lv.problem)
        states = replay_states(lv.problem, actions)
        self.assertEqual(len(states), len(actions) + 1)
        self.assertTrue(lv.problem.is_goal(states[-1]))
        steps = path_steps(lv.problem, actions)
        self.assertEqual([s["step"] for s in steps], list(range(1, len(actions) + 1)))
        # ô cuối cùng của đường đi là ô đích
        self.assertEqual(steps[-1]["cells"], (lv.problem.goal_pos,))

    def test_switch_actions_are_skipped_but_counted(self):
        lv = LEVELS["Split and Merge"]
        actions = UCSSolver().solve(lv.problem)
        steps = path_steps(lv.problem, actions)
        self.assertEqual(len(steps), sum(1 for a in actions if a != "SWITCH"))
        self.assertEqual(max(s["step"] for s in steps), len(actions))

    def test_split_moves_mark_only_the_moved_cube(self):
        lv = LEVELS["Split and Merge"]
        actions = UCSSolver().solve(lv.problem)
        steps = path_steps(lv.problem, actions)
        states = replay_states(lv.problem, actions)
        for s in steps:
            prev = states[s["step"] - 1]
            if prev.is_split:
                self.assertEqual(len(s["cells"]), 1)

    def test_replay_stops_at_an_illegal_action(self):
        lv = LEVELS["First Roll"]
        states = replay_states(lv.problem, ["U"])  # rơi khỏi bàn
        self.assertEqual(len(states), 1)


if __name__ == "__main__":
    unittest.main()
