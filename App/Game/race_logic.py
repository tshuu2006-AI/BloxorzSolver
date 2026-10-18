"""Logic thuần của chế độ "Race": hai thuật toán phát lại lời giải của chúng cùng lúc, từng hành động một.

Không phụ thuộc pygame nên test được; phần vẽ nằm ở ``App/GUI/race.py``.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from App.Game.session import GameSession, MoveEvent


class RaceLaneState:
    """Một làn: một ``GameSession`` riêng chạy lời giải của một thuật toán."""

    def __init__(self, level, row: Dict):
        self.label: str = row["solver"]
        self.row = row
        self.actions: List[str] = list(row["actions"])
        self.session = GameSession(level)
        self.index = 0
        self.finished_at: Optional[int] = None  # chỉ số hành động mà làn hoàn tất (để xếp hạng)

    @property
    def total(self) -> int:
        return len(self.actions)

    @property
    def finished(self) -> bool:
        return self.index >= self.total

    @property
    def moves_done(self) -> int:
        """Số lần lăn đã chạy (không tính SWITCH)."""
        return self.session.moves

    def step(self) -> Optional[MoveEvent]:
        if self.finished:
            return None
        ev = self.session.apply(self.actions[self.index])
        self.index += 1
        if self.finished:
            self.finished_at = self.index
        return ev


class RaceState:
    """Hai làn chạy song song theo từng hành động (lockstep): lời giải ngắn hơn về đích trước."""

    def __init__(self, level, rows: Sequence[Dict]):
        if len(rows) != 2:
            raise ValueError("Race cần đúng hai thuật toán")
        self.level = level
        self.rows = list(rows)
        self.reset()

    def reset(self) -> None:
        self.lanes: List[RaceLaneState] = [RaceLaneState(self.level, r) for r in self.rows]

    @property
    def done(self) -> bool:
        return all(l.finished for l in self.lanes)

    def advance(self) -> List[Optional[MoveEvent]]:
        """Mỗi làn chưa xong đi một hành động. Trả về sự kiện của từng làn (None nếu làn đã xong)."""
        return [lane.step() for lane in self.lanes]

    def ranks(self) -> Dict[str, int]:
        """Hạng theo số hành động cần để về đích (ít hơn = hạng 1; bằng nhau thì cùng hạng)."""
        totals = sorted({l.total for l in self.lanes})
        return {l.label: totals.index(l.total) + 1 for l in self.lanes}

    def headline(self) -> str:
        a, b = self.lanes
        if a.total == b.total:
            return f"Tie: {a.label} and {b.label} both need {a.total} actions."
        fast, slow = (a, b) if a.total < b.total else (b, a)
        return (
            f"{fast.label} arrives first: {fast.total} vs {slow.total} actions "
            f"({slow.total - fast.total} fewer)."
        )
