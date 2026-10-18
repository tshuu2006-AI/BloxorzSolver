from enum import Enum, auto
from typing import Dict, List, Optional, Set, Tuple


class TileType(Enum):
    VOID = auto()
    FLOOR = auto()
    FRAGILE = auto()
    GOAL = auto()
    BRIDGE = auto()


class SwitchType(Enum):
    SOFT = auto()  # Dẫm kiểu nào cũng bật
    HEAVY = auto()  # Chỉ bật khi STANDING
    SPLIT = auto()  # Chỉ bật khi STANDING, dịch chuyển & tách khối


class SwitchMode(Enum):
    TOGGLE = auto()
    PERMANENT = auto()


class Switch:

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
        """
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
        """Danh sách ``(ô cầu, mode, target_state)`` mà công tắc này tác động."""
        if self.effects is not None:
            return self.effects
        return [(cell, self.mode, self.target_state) for cell in self.linked_bridges]
