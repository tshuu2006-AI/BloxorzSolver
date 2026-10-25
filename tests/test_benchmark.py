"""benchmark.py: dựng dòng kết quả, ghi CSV, chọn màn - không dùng tiến trình con."""

import csv
import tempfile
import unittest
from pathlib import Path

from tools import benchmark
from App.Components.level_loader import load_level

LEVELS = Path(benchmark.LEVELS_DIR)


def level_named(name):
    for i, path in enumerate(sorted(LEVELS.glob("*.json"))):
        lv = load_level(path)
        if lv.name == name:
            return i + 1, lv
    raise KeyError(name)


class Rows(unittest.TestCase):
    def test_ucs_row_has_all_metrics_and_replays(self):
        no, lv = level_named("First Roll")
        row = benchmark.run_config(lv, no, benchmark.Config("UCS", "UCS"))
        self.assertEqual(row["status"], "ok")
        self.assertTrue(row["valid"])
        self.assertGreater(row["expanded"], 0)
        self.assertGreaterEqual(row["time_ms"], 0)  # đồng hồ Windows thô: có thể ra 0.0 với màn rất nhỏ
        self.assertGreater(row["memory_kb"], 0)
        self.assertEqual(row["moves"], row["length"])  # màn không có SWITCH

    def test_moves_exclude_switch_actions(self):
        no, lv = level_named("Split and Merge")
        row = benchmark.run_config(lv, no, benchmark.Config("UCS", "UCS"))
        self.assertEqual(row["length"] - row["moves"], 2)  # hai lần đổi khối

    def test_risk_cost_changes_the_chosen_route(self):
        no, lv = level_named("Cracked Bridge")
        default = benchmark.run_config(lv, no, benchmark.Config("UCS", "UCS"))
        risk = benchmark.run_config(lv, no, benchmark.Config("UCS (risk)", "UCS", cost="risk"))
        self.assertTrue(default["valid"] and risk["valid"])
        self.assertGreaterEqual(risk["length"], default["length"])
        # sau khi chạy, hàm chi phí gốc phải được khôi phục
        self.assertNotIn("action_cost", lv.problem.__dict__)

    def test_a_star_variants_find_the_same_cost_as_ucs(self):
        no, lv = level_named("Staircase")
        ucs = benchmark.run_config(lv, no, benchmark.Config("UCS", "UCS"))
        for h in ("manhattan", "modified_manhattan", "relaxed"):
            a = benchmark.run_config(lv, no, benchmark.Config(f"A* {h}", "A*", heuristic=h))
            self.assertEqual(a["cost"], ucs["cost"], h)


class Helpers(unittest.TestCase):
    def test_parse_levels(self):
        self.assertEqual(benchmark.parse_levels(None, 4), [0, 1, 2, 3])
        self.assertEqual(benchmark.parse_levels("1-3,5", 6), [0, 1, 2, 4])
        self.assertEqual(benchmark.parse_levels("2,2,99", 5), [1])

    def test_csv_round_trip(self):
        rows = [{"level_no": 1, "level": "A", "group": "simple", "solver": "UCS", "status": "ok", "length": 5}]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "b.csv"
            benchmark.write_csv(rows, path)
            with path.open(encoding="utf-8") as fh:
                back = list(csv.DictReader(fh))
        self.assertEqual(back[0]["level"], "A")
        self.assertEqual(back[0]["length"], "5")
        self.assertEqual(set(back[0]), set(benchmark.FIELDS))

    def test_configs_cover_all_solvers_and_heuristics(self):
        labels = [c.label for c in benchmark.all_configs()]
        self.assertIn("BFS", labels)
        self.assertIn("UCS (risk)", labels)
        self.assertEqual(sum(1 for l in labels if l.startswith("A*")), 3)


if __name__ == "__main__":
    unittest.main()
