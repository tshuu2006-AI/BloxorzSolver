
from enum import IntEnum
from typing import Optional, Tuple


class Orientation(IntEnum):
    """Block configuration: upright, lying across cells, or split."""

    STANDING = 0
    HORIZONTAL = 1  # (r, c) và (r, c + 1)
    VERTICAL = 2  # (r, c) và (r + 1, c)
    SPLIT = 3  # Tách thành hai khối 1x1x1 độc lập


class State:
    """Lớp biểu diễn trạng thái của trò chơi Bloxorz.

    Đảm bảo tính immutable (bất biến) để có thể dùng làm key trong dict/set.
    """

    __slots__ = (
        "_orientation",
        "_b1",
        "_b2",
        "_active_block",
        "_bridges_state",
        "_hash",
    )

    def __init__(
        self,
        orientation: Orientation,
        b1: Tuple[int, int],
        b2: Optional[Tuple[int, int]] = None,
        active_block: int = 0,
        bridges_state: Tuple[bool, ...] = (),
    ):
        """Khởi tạo trạng thái.

        :param orientation: Hướng hiện tại của khối
        :param b1: Tọa độ khối thứ nhất (r, c) hoặc ô chuẩn khi chưa tách
        :param b2: Tọa độ khối thứ hai (r, c) khi ở tư thế nằm ngang/dọc/split
        :param active_block: 0 nếu đang điều khiển b1, 1 nếu đang điều khiển b2 (chỉ dùng khi SPLIT)
        :param bridges_state: Bộ boolean trạng thái các cây cầu (True = mở/đi được, False = đóng)
        """
        self._orientation = orientation
        self._b1 = b1
        self._b2 = b1 if b2 is None else b2
        self._active_block = active_block if orientation == Orientation.SPLIT else 0
        self._bridges_state = tuple(bridges_state)

        # Chuẩn hóa để hai trạng thái tương đương có cùng hash
        # Khi SPLIT, nếu b1 và b2 hoán vị cùng active_block tương ứng thì là một
        if self._orientation == Orientation.SPLIT:
            if self._b1 > self._b2:
                self._b1, self._b2 = self._b2, self._b1
                self._active_block = 1 - self._active_block

        # Pre-compute hash để tối ưu tốc độ tra cứu visited set
        self._hash = hash((
            self._orientation,
            self._b1,
            self._b2,
            self._active_block,
            self._bridges_state,
        ))

    @property
    def orientation(self) -> Orientation:
        """Return the block's current orientation."""
        return self._orientation

    @property
    def is_split(self) -> bool:
        """Return whether the block is currently split into two cubes."""
        return self._orientation == Orientation.SPLIT

    @property
    def active_block(self) -> int:
        """Return the controlled cube index when split (otherwise zero)."""
        return self._active_block

    @property
    def bridges_state(self) -> Tuple[bool, ...]:
        """Return the open/closed state of each bridge cell."""
        return self._bridges_state

    def get_occupied_cells(self) -> Tuple[Tuple[int, int], ...]:
        """Trả về danh sách các ô hiện tại đang bị khối chiếm dụng."""
        if self._orientation == Orientation.STANDING:
            return (self._b1,)
        return (self._b1, self._b2)

    def is_goal(self, goal_pos: Tuple[int, int]) -> bool:
        """Đạt mục tiêu: Khối phải STANDING đúng ngay ô đích."""
        return (
            self._orientation == Orientation.STANDING
            and self._b1 == goal_pos
        )

    def __eq__(self, other: object) -> bool:
        """Compare states by orientation, positions, control, and bridges."""
        if not isinstance(other, State):
            return False
        return (
            self._orientation == other._orientation
            and self._b1 == other._b1
            and self._b2 == other._b2
            and self._active_block == other._active_block
            and self._bridges_state == other._bridges_state
        )

    def __hash__(self) -> int:
        """Return the precomputed hash used by search visited sets."""
        return self._hash

    def __repr__(self) -> str:
        """Return a readable representation of this state."""
        if self._orientation == Orientation.SPLIT:
            return f"State(SPLIT, b1={self._b1}, b2={self._b2}, active={self._active_block}, bridges={self._bridges_state})"
        return f"State({self._orientation.name}, pos=({self._b1}, {self._b2}), bridges={self._bridges_state})"
