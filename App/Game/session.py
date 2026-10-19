"""Trạng thái một ván chơi: nước đi, hoàn tác, thắng/thua.

Lớp này là cầu nối giữa ``Problem`` (luật chơi dùng chung với solver) và GUI.
Nó không vẽ gì, nên có thể test không cần pygame.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from App.Components.features import SwitchType, TileType
from App.Components.level_loader import Level
from App.Components.state import Orientation, State

Cell = Tuple[int, int]
DELTAS = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}


class Status(Enum):
    PLAYING = "playing"
    WON = "won"
    LOST = "lost"


class Outcome(Enum):
    MOVED = "moved"
    SWITCHED = "switched"  # đổi khối điều khiển (SWITCH)
    WON = "won"
    FELL = "fell"
    BLOCKED = "blocked"  # nước đi bị chặn nhưng không rơi (hai khối chồng nhau)
    IGNORED = "ignored"  # ván đã kết thúc / hành động không áp dụng được


@dataclass
class MoveEvent:
    """Mô tả một lần gọi ``GameSession.apply`` để GUI dựng hiệu ứng."""

    action: str
    outcome: Outcome
    prev: State
    new: Optional[State] = None  # None khi FELL / BLOCKED / IGNORED
    reason: str = ""
    # Với FELL: các ô khối đã lăn tới trước khi rơi (để vẽ hiệu ứng rơi).
    fall_cells: Tuple[Cell, ...] = ()
    # Với FELL trên ô mỏng: tấm sàn tụt xuống cùng khối.
    fragile_fall_cells: Tuple[Cell, ...] = ()
    # Cầu đổi trạng thái trong nước đi này: {chỉ số: True nếu vừa mở}.
    bridge_changes: dict = field(default_factory=dict)
    teleported: bool = False
    merged: bool = False
    split_move: bool = False  # nước đi do một khối đơn thực hiện


def explain_fall(problem, s: State, action: str) -> Tuple[str, Tuple[Cell, ...]]:
    """Lý do một nước đi làm khối rơi, cùng các ô khối đã lăn tới."""
    geom = problem._compute_next_geometry(s, action)
    if geom is None:
        return "The cubes can't overlap.", ()
    orient, b1, b2 = geom
    cells = (b1,) if orient == Orientation.STANDING else (b1, b2)
    if s.is_split:
        moved = b1 if s.active_block == 0 else b2
        fall_cells: Tuple[Cell, ...] = (moved,)
        if moved == problem.goal_pos:
            return "The cube fell into the goal hole!", fall_cells
    else:
        fall_cells = cells
    for cell in cells:
        tile = problem.grid.get(cell, TileType.VOID)
        if tile == TileType.VOID:
            return "The block rolled off the platform.", fall_cells
        if tile == TileType.BRIDGE:
            idx = problem.bridge_indices.get(cell)
            if idx is None or not s.bridges_state[idx]:
                return "The bridge is closed - nothing to stand on.", fall_cells
    if orient == Orientation.STANDING and problem.grid.get(b1) == TileType.FRAGILE:
        return "The fragile tile gave way under the standing block.", fall_cells
    return "The floor disappeared under the block.", fall_cells


def fragile_fall_cells(problem, s: State, action: str) -> Tuple[Cell, ...]:
    """Ô fragile tụt xuống trong nước đi này, hoặc ``()`` nếu rơi vì lý do khác."""
    geom = problem._compute_next_geometry(s, action)
    if geom is None:
        return ()
    orient, b1, _b2 = geom
    if orient == Orientation.STANDING and problem.grid.get(b1) == TileType.FRAGILE:
        return (b1,)
    return ()


def fired_switches(problem, ev: "MoveEvent") -> List[Cell]:
    """Ô công tắc mà nước đi ``ev`` vừa kích hoạt (để GUI làm hiệu ứng phát sáng)."""
    if ev.outcome not in (Outcome.MOVED, Outcome.WON):
        return []
    geom = problem._compute_next_geometry(ev.prev, ev.action)
    if geom is None:
        return []
    orient, b1, b2 = geom
    if ev.prev.is_split:
        landed = (b1 if ev.prev.active_block == 0 else b2,)
    else:
        landed = (b1,) if orient == Orientation.STANDING else (b1, b2)
    fired = []
    for cell in landed:
        sw = problem.switches.get(cell)
        if sw is None:
            continue
        if sw.switch_type != SwitchType.SOFT and orient != Orientation.STANDING:
            continue  # công tắc nặng / tách chỉ chạy khi khối đứng thẳng
        fired.append(cell)
    return fired


class GameSession:
    def __init__(self, level: Level):
        self.level = level
        self.problem = level.problem
        self.reset()

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.state: State = self.problem.initial_state
        self.history: List[Tuple[State, int]] = []
        self.moves = 0  # không tính SWITCH
        self.status = Status.PLAYING
        self.fail_reason = ""

    @property
    def can_undo(self) -> bool:
        return bool(self.history) or self.status == Status.LOST

    @property
    def active_cell(self) -> Optional[Cell]:
        if not self.state.is_split:
            return None
        return self.state.get_occupied_cells()[self.state.active_block]

    # ------------------------------------------------------------------
    def apply(self, action: str) -> MoveEvent:
        s = self.state
        if self.status != Status.PLAYING:
            return MoveEvent(action, Outcome.IGNORED, s)

        if action == "SWITCH":
            nxt = self.problem.result(s, action)
            if nxt is None:
                return MoveEvent(action, Outcome.IGNORED, s)
            self.history.append((s, self.moves))
            self.state = nxt
            return MoveEvent(action, Outcome.SWITCHED, s, nxt)

        nxt = self.problem.result(s, action)
        if nxt is None:
            reason, fall_cells = explain_fall(self.problem, s, action)
            if not fall_cells and not s.is_split:
                return MoveEvent(action, Outcome.IGNORED, s)
            if not fall_cells:  # hai khối đơn chồng nhau
                return MoveEvent(action, Outcome.BLOCKED, s, reason=reason, split_move=True)
            self.status = Status.LOST
            self.fail_reason = reason
            return MoveEvent(
                action, Outcome.FELL, s, reason=reason, fall_cells=fall_cells,
                fragile_fall_cells=fragile_fall_cells(self.problem, s, action),
                split_move=s.is_split,
            )

        self.history.append((s, self.moves))
        self.moves += 1
        self.state = nxt
        changes = {
            i: nxt.bridges_state[i]
            for i in range(len(nxt.bridges_state))
            if nxt.bridges_state[i] != s.bridges_state[i]
        }
        won = self.problem.is_goal(nxt)
        if won:
            self.status = Status.WON
        return MoveEvent(
            action,
            Outcome.WON if won else Outcome.MOVED,
            s,
            nxt,
            bridge_changes=changes,
            teleported=nxt.is_split and not s.is_split,
            merged=s.is_split and not nxt.is_split,
            split_move=s.is_split,
        )

    def undo(self) -> bool:
        if self.status == Status.LOST:  # trạng thái giữ nguyên trước nước đi chết
            self.status = Status.PLAYING
            self.fail_reason = ""
            return True
        if not self.history:
            return False
        self.state, self.moves = self.history.pop()
        self.status = Status.PLAYING
        self.fail_reason = ""
        return True
