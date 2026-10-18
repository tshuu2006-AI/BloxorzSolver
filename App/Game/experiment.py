"""Chạy một cấu hình solver trên một màn và gom số liệu; dùng chung cho tools/benchmark.py và GUI.

Mỗi lần chạy trả về một ``dict`` (một "dòng kết quả") gồm: set, level_no, level, group, rows,
cols, solver, status ("ok" | "no_solution" | "timeout" | "cancelled" | "error: ..."), length,
moves (không tính SWITCH), cost, expanded, time_ms, memory_kb, valid và ``actions``.
"""

from __future__ import annotations

import csv
import multiprocessing as mp
import statistics
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from App.Components.features import TileType
from App.Components.level_loader import load_level
from App.Game.solver_bridge import HEURISTICS, make_solver

FRAGILE_PENALTY = 10

FIELDS = [
    "set", "level_no", "level", "group", "rows", "cols", "solver", "status",
    "length", "moves", "cost", "expanded", "time_ms", "memory_kb", "valid",
]


@dataclass(frozen=True)
class Config:
    label: str
    solver: str  # tên trong solver_bridge: BFS / DFS / UCS / A*
    heuristic: Optional[str] = None
    cost: str = "default"  # "default" | "risk"


def all_configs() -> List[Config]:
    configs = [Config("BFS", "BFS"), Config("DFS", "DFS"), Config("UCS", "UCS"),
               Config("UCS (risk)", "UCS", cost="risk")]
    configs += [Config(f"A* {h}", "A*", heuristic=h) for h in HEURISTICS]
    return configs


def compare_configs() -> List[Config]:
    """Các cấu hình mà nút "Compare all" của GUI chạy (không gồm biến thể UCS risk)."""
    return [c for c in all_configs() if c.cost == "default"]


# ----------------------------------------------------------------------------
def apply_cost(problem, mode: str) -> None:
    """Đổi hàm chi phí của ``problem`` (chỉ ảnh hưởng solver dùng chi phí)."""
    if mode == "default":
        return
    if mode != "risk":
        raise ValueError(f"cost mode {mode!r} không hợp lệ")

    def risk_cost(s, a, s_new) -> int:
        if a == "SWITCH":
            return 1
        cost = 2
        for cell in s_new.get_occupied_cells():
            if problem.grid.get(cell) == TileType.FRAGILE:
                cost += FRAGILE_PENALTY
        return cost

    problem.action_cost = risk_cost


def replay_ok(problem, actions) -> bool:
    state = problem.initial_state
    for a in actions:
        state = problem.result(state, a)
        if state is None:
            return False
    return problem.is_goal(state)


def run_config(level, number: int, config: Config, repeat: int = 1) -> Dict:
    """Chạy một cấu hình trên một màn (trong tiến trình hiện tại) và trả về một dòng kết quả."""
    row = {
        "set": level.section, "level_no": number, "level": level.name, "group": level.group,
        "rows": level.rows, "cols": level.cols, "solver": config.label, "status": "ok",
    }
    times, mems = [], []
    first_metrics, first_actions = None, None
    for _ in range(max(1, repeat)):
        problem = level.problem
        problem.__dict__.pop("action_cost", None)  # bỏ ghi đè của lần trước
        apply_cost(problem, config.cost)
        solver = make_solver(config.solver, config.heuristic)
        actions = solver.solve(problem)
        problem.__dict__.pop("action_cost", None)
        metrics = solver.get_metrics()
        if first_metrics is None:
            first_metrics, first_actions = metrics, actions
        times.append(metrics["search_time_sec"])
        mems.append(metrics["peak_memory_kb"])
    if first_actions is None:
        row.update(status="no_solution", expanded=first_metrics["expanded_nodes"],
                   time_ms=round(statistics.median(times) * 1000, 3),
                   memory_kb=round(statistics.median(mems), 1), actions=None)
        return row
    row.update(
        length=first_metrics["solution_length"],
        moves=sum(1 for a in first_actions if a != "SWITCH"),
        cost=first_metrics["solution_cost"],
        expanded=first_metrics["expanded_nodes"],
        time_ms=round(statistics.median(times) * 1000, 3),
        memory_kb=round(statistics.median(mems), 1),
        valid=replay_ok(level.problem, first_actions),
        actions=list(first_actions),
    )
    return row


def _child(path: str, number: int, section: str, config: Config, repeat: int, queue) -> None:
    try:
        queue.put(run_config(load_level(path, section), number, config, repeat))
    except Exception as exc:  # báo lỗi của solver thay vì làm sập cả chương trình gọi
        queue.put({"status": f"error: {type(exc).__name__}: {exc}"})


def run_isolated(
    path: Path,
    number: int,
    section: str,
    config: Config,
    repeat: int,
    timeout: float,
    cancel: Optional[threading.Event] = None,
) -> Dict:
    """Chạy ``run_config`` trong tiến trình con; dừng nó khi quá ``timeout`` giây hoặc khi ``cancel`` được set."""
    ctx = mp.get_context("spawn")
    queue = ctx.Queue()
    proc = ctx.Process(target=_child, args=(str(path), number, section, config, repeat, queue), daemon=True)
    proc.start()
    waited = 0.0
    while proc.is_alive() and waited < timeout:
        if cancel is not None and cancel.is_set():
            proc.terminate()
            proc.join()
            return {"status": "cancelled"}
        proc.join(0.1)
        waited += 0.1
    if proc.is_alive():
        proc.terminate()
        proc.join()
        return {"status": "timeout"}
    try:
        return queue.get(timeout=5)
    except Exception:
        return {"status": "error: no result"}


def write_csv(rows: Sequence[Dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in FIELDS})