"""Ô đặc biệt: fragile, cầu, 3 loại công tắc, tách/ghép khối."""

import unittest

from App.Components.level_loader import level_from_dict
from App.Components.state import Orientation as O, State

ST, HZ, VT, SP = O.STANDING, O.HORIZONTAL, O.VERTICAL, O.SPLIT


def build(grid, bridges=(), switches=()):
    return level_from_dict(
        {"name": "t", "grid": grid, "bridges": list(bridges), "switches": list(switches)}
    ).problem


def at(p, orient, b1, b2=None, active_block=0):
    """State với cấu hình cầu ban đầu của màn."""
    return State(orient, b1, b2, active_block, p.initial.bridges_state)


def bridge(r, c, open_=False):
    return {"cells": [[r, c]], "open": open_}


class FragileTiles(unittest.TestCase):
    def setUp(self):
        self.p = build(["S#F###G"])

    def test_standing_on_fragile_falls(self):
        self.assertIsNone(self.p.result(at(self.p, HZ, (0, 0), (0, 1)), "R"))

    def test_lying_on_fragile_is_safe(self):
        self.assertIsNotNone(self.p.result(at(self.p, ST, (0, 1)), "R"))
        self.assertIsNotNone(self.p.result(at(self.p, ST, (0, 0)), "R"))

    def test_single_cube_on_fragile_is_safe(self):
        nxt = self.p.result(at(self.p, SP, (0, 1), (0, 5)), "R")
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt.orientation, SP)


class GoalHole(unittest.TestCase):
    def setUp(self):
        self.p = build(["S###G#"])

    def test_standing_wins(self):
        nxt = self.p.result(at(self.p, HZ, (0, 2), (0, 3)), "R")
        self.assertTrue(self.p.is_goal(nxt))

    def test_lying_across_goal_is_not_a_win(self):
        nxt = self.p.result(at(self.p, ST, (0, 2)), "R")
        self.assertIsNotNone(nxt)
        self.assertFalse(self.p.is_goal(nxt))

    def test_cube_entering_goal_falls(self):
        p = build(["S#G#"])
        self.assertIsNone(p.result(at(p, SP, (0, 1), (0, 3)), "R"))

    def test_cube_entering_goal_falls_even_if_it_would_merge(self):
        p = build(["S#G#"])
        # Khối còn lại ở (0,3) kề ô đích: vẫn là rơi xuống hố, không ghép.
        self.assertIsNone(p.result(at(p, SP, (0, 1), (0, 3)), "R"))


class Bridges(unittest.TestCase):
    def test_closed_bridge_is_void(self):
        p = build(["S#B#G"], [bridge(0, 2)])
        self.assertIsNone(p.result(at(p, ST, (0, 1)), "R"))

    def test_open_bridge_is_floor(self):
        p = build(["S#B#G"], [bridge(0, 2, True)], [])
        self.assertIsNotNone(p.result(at(p, ST, (0, 1)), "R"))

    def test_bridge_closing_under_the_block_makes_it_fall(self):
        p = build(
            ["SoB#G"],
            [bridge(0, 2, True)],
            [{"pos": [0, 1], "mode": "toggle", "link": [0]}],
        )
        self.assertIsNone(p.result(at(p, ST, (0, 0)), "R"))


class Switches(unittest.TestCase):
    def test_soft_triggers_when_lying(self):
        p = build(["S#oB#G"], [bridge(0, 3)],
                  [{"pos": [0, 2], "mode": "open", "link": [0]}])
        nxt = p.result(at(p, ST, (0, 0)), "R")
        self.assertEqual(nxt.orientation, HZ)
        self.assertEqual(nxt.bridges_state, (True,))

    def test_heavy_ignored_when_lying_but_fires_when_standing(self):
        p = build(["S#xB#G"], [bridge(0, 3)],
                  [{"pos": [0, 2], "mode": "open", "link": [0]}])
        lying = p.result(at(p, ST, (0, 0)), "R")
        self.assertEqual(lying.bridges_state, (False,))
        standing = p.result(at(p, HZ, (0, 0), (0, 1)), "R")
        self.assertEqual(standing.orientation, ST)
        self.assertEqual(standing.bridges_state, (True,))

    def test_toggle_flips_each_time(self):
        p = build(["S#oB#G"], [bridge(0, 3)],
                  [{"pos": [0, 2], "mode": "toggle", "link": [0]}])
        s1 = p.result(at(p, ST, (0, 0)), "R")
        self.assertEqual(s1.bridges_state, (True,))
        s2 = p.result(p.result(s1, "R"), "L")  # đi ra khỏi rồi lăn lại
        self.assertIsNotNone(s2)

    def test_permanent_is_idempotent(self):
        p = build(["S#oB#G"], [bridge(0, 3, True)],
                  [{"pos": [0, 2], "mode": "open", "link": [0]}])
        self.assertEqual(p.result(at(p, ST, (0, 0)), "R").bridges_state, (True,))

    def test_two_toggles_on_same_bridge_cancel(self):
        p = build(["SooB#G"], [bridge(0, 3)],
                  [{"pos": [0, 1], "mode": "toggle", "link": [0]},
                   {"pos": [0, 2], "mode": "toggle", "link": [0]}])
        self.assertEqual(p.result(at(p, ST, (0, 0)), "R").bridges_state, (False,))

    def test_open_and_close_on_same_bridge_cancel(self):
        for initial in (False, True):
            p = build(["SooB#G"], [bridge(0, 3, initial)],
                      [{"pos": [0, 1], "mode": "open", "link": [0]},
                       {"pos": [0, 2], "mode": "close", "link": [0]}])
            nxt = p.result(at(p, ST, (0, 0)), "R")
            self.assertEqual(nxt.bridges_state, (initial,))

    def test_switches_on_different_bridges_both_apply(self):
        p = build(["SooBB#G"], [bridge(0, 3), bridge(0, 4)],
                  [{"pos": [0, 1], "mode": "toggle", "link": [0]},
                   {"pos": [0, 2], "mode": "toggle", "link": [1]}])
        self.assertEqual(p.result(at(p, ST, (0, 0)), "R").bridges_state, (True, True))


SPLIT_GRID = ["S#p##", "#...#", "..G.."]


class SplitSwitch(unittest.TestCase):
    def sw(self, **extra):
        spec = {"pos": [0, 2], "targets": [[1, 0], [1, 4]]}
        spec.update(extra)
        return spec

    def test_standing_on_split_teleports_into_two_cubes(self):
        p = build(SPLIT_GRID, [], [self.sw()])
        nxt = p.result(at(p, HZ, (0, 0), (0, 1)), "R")
        self.assertEqual(nxt.orientation, SP)
        self.assertEqual(nxt.get_occupied_cells(), ((1, 0), (1, 4)))
        self.assertEqual(nxt.active_block, 0)

    def test_lying_on_split_does_nothing(self):
        p = build(SPLIT_GRID, [], [self.sw()])
        self.assertEqual(p.result(at(p, ST, (0, 0)), "R").orientation, HZ)

    def test_bridge_is_resolved_before_teleport(self):
        grid = ["S#p##", "#...B", "..G.."]
        p = build(grid, [bridge(1, 4)], [self.sw(mode="open", link=[0])])
        nxt = p.result(at(p, HZ, (0, 0), (0, 1)), "R")
        self.assertIsNotNone(nxt)
        self.assertEqual(nxt.bridges_state, (True,))

    def test_teleport_onto_closed_bridge_falls(self):
        grid = ["S#p##", "#...B", "..G.."]
        p = build(grid, [bridge(1, 4)], [self.sw()])
        self.assertIsNone(p.result(at(p, HZ, (0, 0), (0, 1)), "R"))

    def test_switch_cube_action(self):
        p = build(SPLIT_GRID, [], [self.sw()])
        s = at(p, SP, (1, 0), (1, 4))
        self.assertEqual(p.result(s, "SWITCH").active_block, 1)
        self.assertIsNone(p.result(at(p, ST, (0, 0)), "SWITCH"))

    def test_cubes_merge_when_adjacent(self):
        p = build(["S###G"])
        nxt = p.result(at(p, SP, (0, 0), (0, 2)), "R")
        self.assertEqual(nxt.orientation, HZ)
        self.assertEqual(nxt.get_occupied_cells(), ((0, 1), (0, 2)))
        p2 = build(["S", "#", "#", "#", "G"])
        nxt = p2.result(at(p2, SP, (0, 0), (2, 0)), "D")
        self.assertEqual(nxt.orientation, VT)

    def test_cubes_cannot_overlap(self):
        p = build(["S###G"])
        self.assertIsNone(p.result(at(p, SP, (0, 1), (0, 2)), "R"))

    def test_cube_rolls_off_board(self):
        p = build(["S###G"])
        self.assertIsNone(p.result(at(p, SP, (0, 0), (0, 3)), "L"))

    def test_resting_cube_does_not_retrigger_its_switch(self):
        p = build(["oS###", "B...G"], [bridge(1, 0)],
                  [{"pos": [0, 0], "mode": "toggle", "link": [0]}])
        # Khối b1 đứng trên công tắc, khối b2 (đang điều khiển) lăn đi chỗ khác.
        s = at(p, SP, (0, 0), (0, 2), active_block=1)
        nxt = p.result(s, "R")
        self.assertEqual(nxt.bridges_state, (False,))

    def test_cube_landing_on_soft_triggers_it(self):
        p = build(["oS###", "B...G"], [bridge(1, 0)],
                  [{"pos": [0, 0], "mode": "toggle", "link": [0]}])
        nxt = p.result(at(p, SP, (0, 1), (0, 4), active_block=0), "L")
        self.assertEqual(nxt.bridges_state, (True,))

    def test_cube_cannot_trigger_heavy_or_split(self):
        p = build(["S#x##", "B...G"], [bridge(1, 0)],
                  [{"pos": [0, 2], "mode": "open", "link": [0]}])
        nxt = p.result(at(p, SP, (0, 1), (0, 4), active_block=0), "R")
        self.assertEqual(nxt.bridges_state, (False,))


class SwitchExtensions(unittest.TestCase):
    """Công tắc nhiều hiệu ứng khác loại và khối đơn được chọn sẵn sau khi tách."""

    def test_one_switch_can_open_one_bridge_and_close_another(self):
        p = build(
            ["S#oBB#G"],
            [bridge(0, 3, False), bridge(0, 4, True)],
            [{"pos": [0, 2], "effects": [{"bridge": 0, "mode": "open"}, {"bridge": 1, "mode": "close"}]}],
        )
        self.assertEqual(p.initial.bridges_state, (False, True))
        self.assertEqual(p.result(at(p, ST, (0, 0)), "R").bridges_state, (True, False))

    def test_effects_can_mix_toggle_with_open(self):
        p = build(
            ["S#oBB#G"],
            [bridge(0, 3, True), bridge(0, 4, True)],
            [{"pos": [0, 2], "effects": [{"bridge": 0, "mode": "toggle"}, {"bridge": 1, "mode": "open"}]}],
        )
        self.assertEqual(p.result(at(p, ST, (0, 0)), "R").bridges_state, (False, True))

    def test_effects_cannot_be_combined_with_link(self):
        from App.Components.level_loader import LevelError

        with self.assertRaises(LevelError):
            build(["S#oB#G"], [bridge(0, 3)],
                  [{"pos": [0, 2], "link": [0], "effects": [{"bridge": 0, "mode": "open"}]}])

    def test_split_switch_can_start_with_the_second_cube_selected(self):
        for active in (0, 1):
            p = build(SPLIT_GRID, [], [{"pos": [0, 2], "targets": [[1, 0], [1, 4]], "active": active}])
            nxt = p.result(at(p, HZ, (0, 0), (0, 1)), "R")
            self.assertEqual(nxt.active_block, active)

    def test_split_active_must_be_zero_or_one(self):
        from App.Components.level_loader import LevelError

        with self.assertRaises(LevelError):
            build(SPLIT_GRID, [], [{"pos": [0, 2], "targets": [[1, 0], [1, 4]], "active": 2}])

if __name__ == "__main__":
    unittest.main()
