"""Các khối 3D cần vẽ cho một ``State`` (dùng chung giữa game chính và chế độ Race)."""

from __future__ import annotations

from typing import List

from App.Components.state import Orientation, State


def pieces_of(state: State) -> List[dict]:
    cells = state.get_occupied_cells()
    if state.is_split:
        return [
            {"cells": (cells[i],), "kind": "cube", "height": 1.0, "active": i == state.active_block}
            for i in range(2)
        ]
    height = 2.0 if state.orientation == Orientation.STANDING else 1.0
    return [{"cells": tuple(cells), "kind": "block", "height": height, "active": True}]
