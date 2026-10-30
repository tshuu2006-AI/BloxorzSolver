"""Chạy solver của cả nhóm từ GUI (tiến trình con, dừng được) và lấy lại lời giải + số liệu.

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
import multiprocessing as mp
import queue
import threading
import time
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
    cancelled: bool = False

    @property
    def found(self) -> bool:
        return self.actions is not None


def _solve_child(problem: Problem, name: str, heuristic: Optional[str], out) -> None:
    """Chạy trong tiến trình con: giải ``problem`` và gửi kết quả về qua hàng đợi ``out``."""
    try:
        solver = make_solver(name, heuristic)
        actions = solver.solve(problem)
        out.put(("ok", actions, solver.get_metrics()))
    except Exception as exc:  # báo lỗi của solver lên GUI thay vì làm sập game
        traceback.print_exc()
        out.put(("error", f"{type(exc).__name__}: {exc}", {}))


class SolverJob(threading.Thread):
    """Giải một màn trong tiến trình con; GUI đọc ``outcome`` khi ``done``.

    Chạy ở tiến trình riêng nên tìm kiếm dài không làm giật khung hình (không tranh GIL),
    ``tracemalloc`` của solver không ảnh hưởng game, và ``cancel()`` dừng được ngay.
    """

    def __init__(self, name: str, problem: Problem, heuristic: Optional[str] = None):
        super().__init__(daemon=True)
        self.name_ = name
        self.problem = problem
        self.heuristic = heuristic
        self.label = f"A* ({heuristic})" if name == "A*" and heuristic else name
        self.outcome: Optional[SolveOutcome] = None
        self.started_at = time.perf_counter()
        self._cancel = threading.Event()

    @property
    def done(self) -> bool:
        return self.outcome is not None

    @property
    def elapsed(self) -> float:
        return time.perf_counter() - self.started_at

    def cancel(self) -> None:
        self._cancel.set()

    def _finish(self, **kw) -> None:
        self.outcome = SolveOutcome(self.name_, self.label, **kw)

    def run(self) -> None:
        ctx = mp.get_context("spawn")
        results = ctx.Queue()
        proc = ctx.Process(
            target=_solve_child, args=(self.problem, self.name_, self.heuristic, results), daemon=True
        )
        try:
            proc.start()
        except Exception as exc:
            self._finish(error=f"could not start solver process: {exc}")
            return
        result = None
        try:
            # Đọc hàng đợi trong lúc chờ: tiến trình con chỉ thoát khi kết quả đã được lấy ra.
            while result is None:
                try:
                    result = results.get(timeout=0.1)
                    break
                except queue.Empty:
                    pass
                if self._cancel.is_set():
                    self._finish(cancelled=True)
                    return
                if not proc.is_alive():
                    try:
                        result = results.get(timeout=0.5)
                    except queue.Empty:
                        self._finish(error=f"solver process exited unexpectedly (code {proc.exitcode})")
                        return
        finally:
            if proc.is_alive():
                proc.terminate()
            proc.join(2)
        kind, payload, metrics = result
        if kind == "ok":
            self._finish(actions=payload, metrics=metrics)
        else:
            self._finish(error=payload)
