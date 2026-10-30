"""Đường đi của một lời giải trên bàn cờ, để GUI vẽ lớp phủ "path" và đánh số bước."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from App.Components.problem import Problem
from App.Components.state import Orientation, State

Cell = Tuple[int, int]


def replay_states(problem: Problem, actions: Sequence[str]) -> List[State]:
    """Các trạng thái đi qua khi chạy ``actions`` từ trạng thái đầu (dừng ở hành động không hợp lệ)."""
    states = [problem.initial_state]
    for a in actions:
        nxt = problem.result(states[-1], a)
        if nxt is None:
            break
        states.append(nxt)
    return states


def path_steps(problem: Problem, actions: Sequence[str]) -> List[dict]:
    """Mỗi hành động lăn (bỏ SWITCH) thành ``{"step", "action", "cells"}``.

    ``step`` là số thứ tự hành động (tính cả SWITCH, khớp bộ đếm replay);
    ``cells`` là các ô khối đáp xuống sau cú lăn, trước khi dịch chuyển/ghép.
    """
    states = replay_states(problem, actions)
    steps = []
    for i, (a, prev) in enumerate(zip(actions, states[:-1]), start=1):
        if a == "SWITCH":
            continue
        orient, b1, b2 = problem._compute_next_geometry(prev, a)
        if prev.is_split:
            cells = (b1,) if prev.active_block == 0 else (b2,)
        elif orient == Orientation.STANDING:
            cells = (b1,)
        else:
            cells = (b1, b2)
        steps.append({"step": i, "action": a, "cells": cells})
    return steps


def solve_by_algorithm(problem: Problem, solver_name: str, heuristic: Optional[str] = None) -> Optional[List[str]]:
    """Giải problem bằng thuật giải cụ thể."""
    from App.Game.solver_bridge import make_solver
    try:
        solver = make_solver(solver_name, heuristic)
        return solver.solve(problem)
    except Exception:
        return None


def compute_step_guide(
    problem: Problem,
    current_state: State,
    cached_solution: Optional[Sequence[str]] = None,
    cached_states: Optional[Sequence[State]] = None,
    solver_name: Optional[str] = None,
    heuristic: Optional[str] = None,
) -> Optional[dict]:
    """Tìm bước đi kế tiếp (hành động, trạng thái kế tiếp, lộ trình) từ trạng thái hiện tại theo thuật giải được chọn."""
    if problem.is_goal(current_state):
        return None

    # 1. Thử dùng lộ trình có sẵn nếu current_state nằm trong lộ trình
    if cached_solution and cached_states and len(cached_states) == len(cached_solution) + 1:
        try:
            idx = cached_states.index(current_state)
            if idx < len(cached_solution):
                act = cached_solution[idx]
                nxt = cached_states[idx + 1]
                remaining_actions = cached_solution[idx:]
                remaining_states = cached_states[idx:]
                return {
                    "action": act,
                    "next_state": nxt,
                    "solution": list(remaining_actions),
                    "states": list(remaining_states),
                }
        except ValueError:
            pass

    # 2. Nếu đi chệch ô hoặc chưa có lộ trình, giải lại từ trạng thái hiện tại theo solver_name
    if not solver_name:
        return None

    sub_problem = Problem(
        grid=problem.grid,
        goal_pos=problem.goal_pos,
        initial_state=current_state,
        bridge_indices=problem.bridge_indices,
        switches=problem.switches,
    )
    acts = solve_by_algorithm(sub_problem, solver_name, heuristic)
    if acts:
        act = acts[0]
        nxt = problem.result(current_state, act)
        if nxt is not None:
            new_states = replay_states(sub_problem, acts)
            return {
                "action": act,
                "next_state": nxt,
                "solution": acts,
                "states": new_states,
            }
    return None
