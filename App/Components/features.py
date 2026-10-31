"""Board tile and switch definitions used by Bloxorz levels."""

from enum import Enum
from typing import List, Optional, Tuple


class TileType(Enum):
    """Types of cells that can appear on the game board."""

    VOID = 1
    FLOOR = 2
    FRAGILE = 3
    GOAL = 4
    BRIDGE = 5


class SwitchType(Enum):
    """Activation rule and behavior of a switch."""

    SOFT = 1  # Dẫm kiểu nào cũng bật
    HEAVY = 2  # Chỉ bật khi STANDING
    SPLIT = 3  # Chỉ bật khi STANDING, dịch chuyển & tách khối


class SwitchMode(Enum):
    """How a switch changes the state of its linked bridges."""

    TOGGLE = 1
    PERMANENT = 2


class Switch:
    """A board switch and the bridge or split effects it triggers."""

    def __init__(
        self,
        pos: Tuple[int, int],
        switch_type: SwitchType,
        linked_bridges: List[Tuple[int, int]],
        mode: SwitchMode = SwitchMode.TOGGLE,
        target_state: bool = True,
        split_targets: Optional[Tuple[Tuple[int, int], Tuple[int, int]]] = None,
        effects: Optional[List[Tuple[Tuple[int, int], SwitchMode, bool]]] = None,
        split_active: int = 0,
    ):
        """Create a switch at ``pos`` with its configured effects.

        :param effects: tùy chọn - hiệu ứng riêng cho từng cầu dưới dạng
            ``(ô cầu, mode, target_state)``. Dùng khi một công tắc vừa "toggle"
            cầu này vừa "mở"/"đóng" cầu kia. Nếu không đặt, mọi cầu trong
            ``linked_bridges`` dùng chung ``mode`` / ``target_state``.
        :param split_active: với công tắc SPLIT, khối đơn nào (0 hoặc 1, theo thứ tự
            ``split_targets``) được điều khiển ngay sau khi tách.
        """
        self.pos = pos
        self.switch_type = switch_type
        self.linked_bridges = linked_bridges
        self.mode = mode
        self.target_state = target_state
        self.split_targets = split_targets
        self.effects = effects
        self.split_active = split_active

    def bridge_effects(self) -> List[Tuple[Tuple[int, int], SwitchMode, bool]]:
        """Return bridge effects as ``(cell, mode, target_state)`` tuples."""
        if self.effects is not None:
            return self.effects
        return [(cell, self.mode, self.target_state) for cell in self.linked_bridges]

    @property
    def is_permanent(self) -> bool:
        """Kiểm tra công tắc có phải là công tắc một chiều (PERMANENT) mở/đóng vĩnh viễn hay không."""
        if self.effects is not None:
            return any(m == SwitchMode.PERMANENT for _, m, _ in self.effects)
        return self.mode == SwitchMode.PERMANENT

