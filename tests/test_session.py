"""GameSession: đếm nước đi, rơi, thắng, hoàn tác, đổi khối."""

import unittest

from App.Components.level_loader import level_from_dict
from App.Game.session import GameSession, Outcome, Status


def session(grid, bridges=(), switches=()):
    return GameSession(
        level_from_dict(
            {"name": "t", "grid": grid, "bridges": list(bridges), "switches": list(switches)}
        )
    )


class Session(unittest.TestCase):
    def test_move_counter_and_win(self):
        s = session(["S###G"])
        for a in "RR":
            self.assertEqual(s.apply(a).outcome, Outcome.MOVED)
        self.assertEqual(s.moves, 2)
        # S(0,0) R -> nằm (0,1)-(0,2); R -> đứng (0,3); R -> nằm (0,4)... đứng tại G cần đúng nhịp
        s = session(["S##G"])
        self.assertEqual(s.apply("R").outcome, Outcome.MOVED)
        self.assertEqual(s.apply("R").outcome, Outcome.WON)
        self.assertEqual(s.status, Status.WON)
        self.assertEqual(s.apply("L").outcome, Outcome.IGNORED)

    def test_fall_keeps_state_and_undo_recovers(self):
        s = session(["S###G"])
        start = s.state
        ev = s.apply("U")
        self.assertEqual(ev.outcome, Outcome.FELL)
        self.assertTrue(ev.reason)
        self.assertEqual(s.state, start)
        self.assertEqual(s.status, Status.LOST)
        self.assertEqual(s.apply("R").outcome, Outcome.IGNORED)
        self.assertTrue(s.undo())
        self.assertEqual(s.status, Status.PLAYING)
        self.assertEqual(s.moves, 0)

    def test_undo_restores_moves_and_state(self):
        s = session(["S####G"])
        first = s.state
        s.apply("R")
        self.assertTrue(s.undo())
        self.assertEqual(s.state, first)
        self.assertEqual(s.moves, 0)
        self.assertFalse(s.undo())

    def test_fall_reasons(self):
        from App.Components.state import Orientation, State
        s = session(["S#F#G"])
        s.state = State(Orientation.HORIZONTAL, (0, 0), (0, 1), 0, ())
        self.assertEqual(s.apply("R").outcome, Outcome.FELL)
        self.assertIn("fragile", s.fail_reason.lower())
        s = session(["S#B#G"], [{"cells": [[0, 2]], "open": False}])
        s.apply("R")  # nằm (0,1)-(0,2): (0,2) là cầu đóng
        self.assertEqual(s.status, Status.LOST)
        self.assertIn("bridge", s.fail_reason.lower())

    def test_switch_cube_does_not_count_as_a_move(self):
        s = session(["S#p##", "#...#", "..G.."], switches=[{"pos": [0, 2], "targets": [[1, 0], [1, 4]]}])
        from App.Components.state import Orientation, State
        s2 = s
        s2.state = State(Orientation.SPLIT, (1, 0), (1, 4), 0, ())
        moves = s2.moves
        ev = s2.apply("SWITCH")
        self.assertEqual(ev.outcome, Outcome.SWITCHED)
        self.assertEqual(s2.moves, moves)
        self.assertEqual(s2.state.active_block, 1)
        self.assertTrue(s2.undo())
        self.assertEqual(s2.state.active_block, 0)

    def test_overlapping_cubes_are_blocked_not_fatal(self):
        from App.Components.state import Orientation, State
        s = session(["S###G"])
        s.state = State(Orientation.SPLIT, (0, 1), (0, 2), 0, ())
        ev = s.apply("R")
        self.assertEqual(ev.outcome, Outcome.BLOCKED)
        self.assertEqual(s.status, Status.PLAYING)


if __name__ == "__main__":
    unittest.main()
