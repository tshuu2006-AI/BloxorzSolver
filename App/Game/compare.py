"""So sánh các thuật toán trên cùng một màn: chạy lần lượt từng solver ở luồng nền.

``CompareJob`` chạy từng cấu hình (BFS, DFS, UCS, A* với mỗi heuristic) trong một
tiến trình con (có timeout, huỷ được), nên GUI không bị đứng và một solver chạy
quá lâu không kéo cả chương trình xuống.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from App.Game.experiment import Config, run_isolated

# Các chỉ số mà "thấp hơn là tốt hơn" và được tô nổi bật ở ô tốt nhất mỗi cột.
BEST_KEYS = ("moves", "cost", "expanded", "time_ms", "memory_kb")


class CompareJob(threading.Thread):
    def __init__(self, level, configs: Sequence[Config], timeout: float = 60.0):
        super().__init__(daemon=True)
        self.level = level
        self.configs: List[Config] = list(configs)
        self.timeout = timeout
        self.results: List[Dict] = []  # thêm dần theo thứ tự chạy
        self.current: Optional[Config] = None
        self.finished = False
        self.cancel_event = threading.Event()

    @property
    def total(self) -> int:
        return len(self.configs)

    def cancel(self) -> None:
        self.cancel_event.set()

    def run(self) -> None:
        lv = self.level
        for cfg in self.configs:
            if self.cancel_event.is_set():
                break
            self.current = cfg
            row = run_isolated(Path(lv.path), 0, lv.section, cfg, 1, self.timeout, self.cancel_event)
            if row.get("status") == "cancelled":
                break
            row = {
                "set": lv.section, "level_no": 0, "level": lv.name, "group": lv.group,
                "rows": lv.rows, "cols": lv.cols, "solver": cfg.label, **row,
            }
            self.results.append(row)
        self.current = None
        self.finished = True


def usable(row: Dict) -> bool:
    return row.get("status") == "ok" and row.get("valid") is True


def best_marks(rows: Sequence[Dict]) -> Dict[int, Set[str]]:
    """``{chỉ số dòng: {các chỉ số mà dòng đó đạt giá trị tốt nhất}}`` (hoà thì đều được tô)."""
    marks: Dict[int, Set[str]] = {i: set() for i in range(len(rows))}
    good = [(i, r) for i, r in enumerate(rows) if usable(r)]
    for key in BEST_KEYS:
        values = [(i, r[key]) for i, r in good if r.get(key) not in (None, "")]
        if not values:
            continue
        best = min(v for _, v in values)
        for i, v in values:
            if v == best:
                marks[i].add(key)
    return marks


def summary_line(rows: Sequence[Dict]) -> str:
    """Một dòng tóm tắt: nhanh nhất, ít nút nhất, lời giải rẻ nhất."""
    good = [r for r in rows if usable(r)]
    if not good:
        return "No algorithm found a solution."

    def names(key):
        best = min(r[key] for r in good)
        return ", ".join(r["solver"] for r in good if r[key] == best), best

    fast, t = names("time_ms")
    few, n = names("expanded")
    cheap, c = names("cost")
    return f"Fastest: {fast} ({t:g} ms)   -   Fewest nodes: {few} ({n:,})   -   Cheapest solution: {cheap} (cost {c})"
