"""compare.py: chạy lần lượt nhiều solver trên một màn và đánh dấu giá trị tốt nhất."""

import threading
import time
import unittest
from pathlib import Path

from App.Components.level_loader import load_level
from App.Game.compare import CompareJob, best_marks, summary_line, usable
from App.Game.experiment import Config, all_configs, compare_configs

FIRST_ROLL = Path(__file__).resolve().parent.parent / "levels" / "01_first_roll.json"


def row(solver, **kw):
    base = {"solver": solver, "status": "ok", "valid": True, "moves": 6, "cost": 14,
            "expanded": 35, "time_ms": 3.0, "memory_kb": 26.0}
    base.update(kw)
    return base


class BestMarks(unittest.TestCase):
    def test_marks_lowest_value_per_metric_and_ties(self):
        rows = [row("A", expanded=10, time_ms=5.0), row("B", expanded=20, time_ms=2.0), row("C", expanded=10, time_ms=9.0)]
        marks = best_marks(rows)
        self.assertIn("expanded", marks[0])
        self.assertIn("expanded", marks[2])  # hoà
        self.assertNotIn("expanded", marks[1])
        self.assertIn("time_ms", marks[1])

    def test_failed_or_invalid_rows_are_never_best(self):
        rows = [row("ok", expanded=50), row("bad", expanded=1, valid=False), row("slow", status="timeout")]
        marks = best_marks(rows)
        self.assertIn("expanded", marks[0])
        self.assertEqual(marks[1], set())
        self.assertEqual(marks[2], set())
        self.assertFalse(usable(rows[2]))

    def test_summary_names_the_winners(self):
        rows = [row("DFS", cost=40, expanded=7, time_ms=1.0), row("UCS", cost=14, expanded=35, time_ms=3.0)]
        text = summary_line(rows)
        self.assertIn("Fastest: DFS", text)
        self.assertIn("Fewest nodes: DFS", text)
        self.assertIn("Cheapest solution: UCS", text)
        self.assertEqual(summary_line([row("x", status="timeout")]), "No algorithm found a solution.")


class Configs(unittest.TestCase):
    def test_compare_configs_are_the_default_cost_ones(self):
        labels = [c.label for c in compare_configs()]
        self.assertNotIn("UCS (risk)", labels)
        self.assertEqual(len(labels), len(all_configs()) - 1)


class Job(unittest.TestCase):
    def test_runs_each_config_in_order_and_returns_replayable_rows(self):
        level = load_level(FIRST_ROLL)
        configs = [Config("DFS", "DFS"), Config("UCS", "UCS")]
        job = CompareJob(level, configs, timeout=60)
        job.start()
        job.join(120)
        self.assertTrue(job.finished)
        self.assertEqual([r["solver"] for r in job.results], ["DFS", "UCS"])
        for r in job.results:
            self.assertEqual(r["status"], "ok")
            self.assertTrue(r["valid"])
            self.assertEqual(r["level"], "First Roll")
            self.assertTrue(r["actions"])

    def test_cancel_stops_before_all_configs_run(self):
        level = load_level(FIRST_ROLL)
        job = CompareJob(level, [Config("DFS", "DFS"), Config("UCS", "UCS"), Config("A* relaxed", "A*", "relaxed")], timeout=60)
        job.cancel()  # huỷ trước khi bắt đầu
        job.start()
        job.join(30)
        self.assertTrue(job.finished)
        self.assertEqual(job.results, [])


if __name__ == "__main__":
    unittest.main()
