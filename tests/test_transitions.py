"""Bảng chuyển trạng thái (orientation, hướng) -> (orientation, vị trí)."""

import unittest

from App.Components.features import TileType
from App.Components.problem import Problem
from App.Components.state import Orientation as O, State

ST, HZ, VT = O.STANDING, O.HORIZONTAL, O.VERTICAL


def open_board() -> Problem:
    grid = {(r, c): TileType.FLOOR for r in range(12) for c in range(12)}
    grid[(11, 11)] = TileType.GOAL
    return Problem(grid, (11, 11), State(ST, (5, 5)), {}, {})


class TransitionTable(unittest.TestCase):
    def setUp(self):
        self.p = open_board()

    def check(self, start, action, orient, b1, b2=None):
        nxt = self.p.result(start, action)
        self.assertIsNotNone(nxt, f"{start} --{action}--> bị coi là rơi")
        self.assertEqual(nxt.orientation, orient)
        self.assertEqual(nxt.get_occupied_cells()[0], b1)
        if b2 is not None:
            self.assertEqual(nxt.get_occupied_cells()[1], b2)

    def test_standing(self):
        s = State(ST, (5, 5))
        self.check(s, "U", VT, (3, 5), (4, 5))
        self.check(s, "D", VT, (6, 5), (7, 5))
        self.check(s, "L", HZ, (5, 3), (5, 4))
        self.check(s, "R", HZ, (5, 6), (5, 7))

    def test_horizontal(self):
        s = State(HZ, (5, 5), (5, 6))
        self.check(s, "L", ST, (5, 4))
        self.check(s, "R", ST, (5, 7))
        self.check(s, "U", HZ, (4, 5), (4, 6))
        self.check(s, "D", HZ, (6, 5), (6, 6))

    def test_vertical(self):
        s = State(VT, (5, 5), (6, 5))
        self.check(s, "U", ST, (4, 5))
        self.check(s, "D", ST, (7, 5))
        self.check(s, "L", VT, (5, 4), (6, 4))
        self.check(s, "R", VT, (5, 6), (6, 6))

    def test_roll_and_back_is_identity(self):
        back = {"U": "D", "D": "U", "L": "R", "R": "L"}
        start = State(ST, (5, 5))
        for a in "UDLR":
            s1 = self.p.result(start, a)
            # Đứng -> nằm: lăn ngược lại đưa về đúng ô cũ.
            self.assertEqual(self.p.result(s1, back[a]), start)

    def test_off_board_is_illegal(self):
        corner = State(ST, (0, 0))
        for a in "UL":
            self.assertIsNone(self.p.result(corner, a))
        self.assertIsNone(self.p.result(State(HZ, (0, 0), (0, 1)), "U"))
        self.assertIsNone(self.p.result(State(VT, (0, 0), (1, 0)), "L"))

    def test_actions_exclude_illegal_moves(self):
        self.assertEqual(sorted(self.p.actions(State(ST, (0, 0)))), ["D", "R"])

    def test_goal_requires_standing(self):
        self.assertTrue(self.p.is_goal(State(ST, (11, 11))))
        self.assertFalse(self.p.is_goal(State(HZ, (11, 10), (11, 11))))
        self.assertFalse(self.p.is_goal(State(VT, (10, 11), (11, 11))))


if __name__ == "__main__":
    unittest.main()
