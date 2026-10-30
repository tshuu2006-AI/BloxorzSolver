"""SolverJob: giải trong tiến trình con, trả lời giải + số liệu, và dừng được giữa chừng."""

import time
import unittest
from pathlib import Path

from App.Components.level_loader import load_level
from App.Game.experiment import replay_ok
from App.Game.solver_bridge import SolverJob

LEVELS = Path(__file__).resolve().parent.parent / "levels"


def wait(job, limit=60.0):
    t = time.perf_counter()
    while not job.done and time.perf_counter() - t < limit:
        time.sleep(0.05)
    return job.outcome


class SolverJobTests(unittest.TestCase):
    def test_solves_in_a_child_process(self):
        level = load_level(LEVELS / "02_detour.json")
        job = SolverJob("UCS", level.problem)
        job.start()
        out = wait(job)
        self.assertIsNotNone(out)
        self.assertTrue(out.found, out.error)
        self.assertFalse(out.cancelled)
        self.assertTrue(replay_ok(level.problem, out.actions))
        self.assertGreater(out.metrics["expanded_nodes"], 0)

    def test_a_star_heuristic_is_passed_through(self):
        level = load_level(LEVELS / "02_detour.json")
        job = SolverJob("A*", level.problem, "manhattan")
        job.start()
        out = wait(job)
        self.assertEqual(out.label, "A* (manhattan)")
        self.assertTrue(out.found, out.error)

    def test_cancel_stops_a_long_search_quickly(self):
        # DFS on the biggest custom stage runs for over a minute
        level = load_level(LEVELS / "21_grand_teleport_archipelago.json")
        job = SolverJob("DFS", level.problem)
        job.start()
        time.sleep(1.0)
        self.assertFalse(job.done)
        t = time.perf_counter()
        job.cancel()
        out = wait(job, 10.0)
        self.assertIsNotNone(out)
        self.assertTrue(out.cancelled)
        self.assertLess(time.perf_counter() - t, 5.0)


if __name__ == "__main__":
    unittest.main()
