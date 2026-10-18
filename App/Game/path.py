"""Đường đi của một lời giải trên bàn cờ, để GUI vẽ lớp phủ "path" và đánh số bước."""

from __future__ import annotations

from typing import List, Sequence, Tuple

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
