"""race_logic.py: hai làn chạy lockstep, hạng và dòng tóm tắt (không cần pygame)."""

import unittest
from pathlib import Path

from App.Components.level_loader import load_level
from App.Game.race_logic import RaceLaneState, RaceState
from App.Solvers.DFS_solver import DFSSolver
from App.Solvers.UCS_solver import UCSSolver

LEVEL = Path(__file__).resolve().parent.parent / "levels" / "02_detour.json"


def row_for(level, solver_cls, label):
    solver = solver_cls()
    actions = solver.solve(level.problem)
    return {"solver": label, "actions": actions}


class Race(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.level = load_level(LEVEL)
        cls.dfs = row_for(cls.level, DFSSolver, "DFS")
        cls.ucs = row_for(cls.level, UCSSolver, "UCS")

    def test_needs_exactly_two_rows(self):
        with self.assertRaises(ValueError):
            RaceState(self.level, [self.dfs])

    def test_lanes_advance_one_action_at_a_time_in_lockstep(self):
        race = RaceState(self.level, [self.dfs, self.ucs])
        events = race.advance()
        self.assertEqual([l.index for l in race.lanes], [1, 1])
        self.assertTrue(all(ev is not None for ev in events))

    def test_a_finished_lane_stays_put_while_the_other_continues(self):
        short = {"solver": "short", "actions": self.ucs["actions"][:3]}
        long = {"solver": "long", "actions": self.ucs["actions"]}
        race = RaceState(self.level, [short, long])
        for _ in range(3):
            race.advance()
        self.assertTrue(race.lanes[0].finished)
        state_before = race.lanes[0].session.state
        events = race.advance()
        self.assertIsNone(events[0])
        self.assertIsNotNone(events[1])
        self.assertEqual(race.lanes[0].session.state, state_before)
        self.assertFalse(race.done)

    def test_race_finishes_with_both_lanes_on_the_goal(self):
        race = RaceState(self.level, [self.dfs, self.ucs])
        while not race.done:
            race.advance()
        for lane in race.lanes:
            self.assertTrue(self.level.problem.is_goal(lane.session.state), lane.label)
            self.assertEqual(lane.finished_at, lane.total)

    def test_ranks_and_headline(self):
        long = {"solver": "long", "actions": self.ucs["actions"] + []}
        padded = {"solver": "padded", "actions": self.ucs["actions"]}
        tie = RaceState(self.level, [long, padded])
        self.assertEqual(tie.ranks(), {"long": 1, "padded": 1})
        self.assertTrue(tie.headline().startswith("Tie"))
        race = RaceState(self.level, [self.dfs, self.ucs])
        ranks = race.ranks()
        if self.dfs["actions"] and len(self.dfs["actions"]) != len(self.ucs["actions"]):
            self.assertEqual(ranks["UCS"], 1)
            self.assertEqual(ranks["DFS"], 2)
            self.assertIn("UCS arrives first", race.headline())

    def test_reset_starts_over(self):
        race = RaceState(self.level, [self.dfs, self.ucs])
        race.advance()
        race.reset()
        self.assertEqual([l.index for l in race.lanes], [0, 0])
        self.assertEqual(race.lanes[0].session.moves, 0)

    def test_lane_counts_moves_without_switch_actions(self):
        split = load_level(Path(__file__).resolve().parent.parent / "levels" / "14_split_and_merge.json")
        row = row_for(split, UCSSolver, "UCS")
        lane = RaceLaneState(split, row)
        while not lane.finished:
            lane.step()
        self.assertEqual(lane.total - lane.moves_done, 2)  # hai lần SWITCH


if __name__ == "__main__":
    unittest.main()
