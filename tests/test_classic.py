"""33 màn gốc (levels/classic): nạp được và có đúng số nước tối thiểu đã biết."""

import unittest
from collections import deque
from pathlib import Path

from App.Components.level_loader import load_levels

CLASSIC_DIR = Path(__file__).resolve().parent.parent / "levels" / "classic"


def min_moves(problem, cap=500_000):
    """0-1 BFS: SWITCH (đổi khối) tốn 0, mỗi cú lăn tốn 1."""
    start = problem.initial_state
    dist = {start: 0}
    dq = deque([start])
    done = set()
    while dq:
        s = dq.popleft()
        if s in done:
            continue
        done.add(s)
        if problem.is_goal(s):
            return dist[s]
        if len(done) > cap:
            return None
        for a in problem.actions(s):
            n = problem.result(s, a)
            if n is None:
                continue
            w = 0 if a == "SWITCH" else 1
            nd = dist[s] + w
            if n not in dist or nd < dist[n]:
                dist[n] = nd
                (dq.appendleft if w == 0 else dq.append)(n)
    return None


class ClassicStages(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.levels = load_levels(CLASSIC_DIR, "classic")

    def test_there_are_33_named_classic_stages(self):
        self.assertEqual(len(self.levels), 33)
        self.assertEqual([lv.name for lv in self.levels], [f"Classic {i:02d}" for i in range(1, 34)])
        self.assertTrue(all(lv.section == "classic" and lv.group == "classic" for lv in self.levels))

    def test_every_stage_has_the_known_minimum_move_count(self):
        # Khớp con số tối thiểu đã công bố cho game gốc => luật của engine (ô mỏng, công tắc,
        # cầu, dịch chuyển, tách/ghép khối) đúng với game thật trên cả 33 màn.
        for lv in self.levels:
            with self.subTest(stage=lv.name):
                self.assertIsNotNone(lv.reference_moves)
                self.assertEqual(min_moves(lv.problem), lv.reference_moves)

    def test_reference_total(self):
        self.assertEqual(sum(lv.reference_moves for lv in self.levels), 1999)


if __name__ == "__main__":
    unittest.main()
