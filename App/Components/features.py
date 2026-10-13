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
    ):
        self.pos = pos
        self.switch_type = switch_type
        self.linked_bridges = linked_bridges
        self.mode = mode
        self.target_state = target_state
        self.split_targets = split_targets
