"""Chạy solver của cả nhóm từ GUI (luồng nền) và lấy lại lời giải + số liệu.

Quy ước đặt tên để GUI tự tìm solver (đã khớp với code hiện có)::

    BFS : App/Solvers/BFS_solver.py     class BFSSolver
    DFS : App/Solvers/DFS_solver.py     class DFSSolver
    UCS : App/Solvers/UCS_solver.py     class UCSSolver
    A*  : App/Solvers/A_star_solver.py  class AstarSolver  (thuộc tính ``heuristic``)

Solver nào chưa có file/class thì nút tương ứng bị làm mờ trong GUI.
"""

from __future__ import annotations

import importlib
import importlib.util
import threading
import traceback
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from App.Components.problem import Problem

SOLVER_SPECS = {
    "BFS": ("App.Solvers.BFS_solver", "BFSSolver"),
    "DFS": ("App.Solvers.DFS_solver", "DFSSolver"),
    "UCS": ("App.Solvers.UCS_solver", "UCSSolver"),
    "A*": ("App.Solvers.A_star_solver", "AstarSolver"),
}
SOLVER_ORDER = ["BFS", "DFS", "UCS", "A*"]


def _find_class(name: str):
    module_name, class_name = SOLVER_SPECS[name]
    try:
        if importlib.util.find_spec(module_name) is None:
            return None
        module = importlib.import_module(module_name)
    except Exception:  # file solver đang viết dở: coi như chưa có
        return None
    return getattr(module, class_name, None)


def available_heuristics() -> List[str]:
    """Return heuristic names registered by the currently installed A* solver."""
    module_name, _ = SOLVER_SPECS["A*"]
    try:
        module = importlib.import_module(module_name)
    except Exception:
        return []
    registry = getattr(module, "HEURISTICS", {})
    return list(registry.keys())


# Keep the benchmark configuration list in sync with A*'s actual registry.
HEURISTICS = available_heuristics()


def available_solvers() -> Dict[str, bool]:
    return {name: _find_class(name) is not None for name in SOLVER_ORDER}


def make_solver(name: str, heuristic: Optional[str] = None):
    cls = _find_class(name)
    if cls is None:
        raise LookupError(f"Solver {name} chưa được cài đặt")
    solver = cls()
    if name == "A*" and heuristic:
        solver.heuristic = heuristic
    return solver


@dataclass
class SolveOutcome:
    name: str
    label: str
    actions: Optional[List[str]] = None
    metrics: dict = field(default_factory=dict)
    error: str = ""

    @property
    def found(self) -> bool:
        return self.actions is not None


class SolverJob(threading.Thread):
    """Chạy ``solver.solve(problem)`` ở luồng nền; GUI đọc ``outcome`` khi ``done``."""

    def __init__(self, name: str, problem: Problem, heuristic: Optional[str] = None):
        super().__init__(daemon=True)
        self.name_ = name
        self.problem = problem
        self.heuristic = heuristic
        self.label = f"A* ({heuristic})" if name == "A*" and heuristic else name
        self.outcome: Optional[SolveOutcome] = None

    @property
    def done(self) -> bool:
        return self.outcome is not None

    def run(self) -> None:
        try:
            solver = make_solver(self.name_, self.heuristic)
            actions = solver.solve(self.problem)
            self.outcome = SolveOutcome(
                self.name_, self.label, actions, solver.get_metrics()
            )
        except Exception as exc:  # hiện lỗi của solver lên GUI thay vì làm sập game
            traceback.print_exc()
            self.outcome = SolveOutcome(
                self.name_, self.label, error=f"{type(exc).__name__}: {exc}"
            )
