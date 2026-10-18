"""Nạp màn chơi từ file JSON và dựng ra đối tượng ``Problem``.

Định dạng file màn chơi (JSON)::

    {
      "name": "Tên màn",
      "group": "simple | fragile | switch | split | combined",
      "description": "Gợi ý ngắn hiển thị trong game",
      "grid": ["###.", "#S#G"],
      "bridges": [{"cells": [[0, 2]], "open": false}],
      "switches": [
        {"pos": [1, 1], "mode": "toggle | open | close", "link": [0]},
        {"pos": [2, 2], "targets": [[0, 0], [3, 3]]}
      ]
    }

Ký tự trong ``grid``:
    ``.`` hoặc khoảng trắng: ô trống (void)   ``#`` sàn thường
    ``S`` ô xuất phát (sàn)   ``G`` ô đích   ``F`` ô mỏng (fragile)
    ``B`` ô cầu (phải thuộc một nhóm trong ``bridges``)
    ``o`` công tắc mềm (soft)   ``x`` công tắc nặng (heavy)   ``p`` công tắc tách khối (split)

Mỗi ô cầu có một chỉ số riêng trong ``State.bridges_state``; một nhóm cầu
(``bridges[i]``) chỉ là cách gom các ô cầu để công tắc ``link`` tới và để GUI
tô cùng một màu.  ``mode`` của công tắc: ``toggle`` (đảo trạng thái), ``open``
hoặc ``close`` (đặt cố định - permanent).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from App.Components.features import (
    Switch,
    SwitchMode,
    SwitchType,
    TileType,
)
from App.Components.problem import Problem
from App.Components.state import Orientation, State

Cell = Tuple[int, int]

_TILE_CHARS = {
    "#": TileType.FLOOR,
    "S": TileType.FLOOR,
    "G": TileType.GOAL,
    "F": TileType.FRAGILE,
    "B": TileType.BRIDGE,
    "o": TileType.FLOOR,
    "x": TileType.FLOOR,
    "p": TileType.FLOOR,
}
_SWITCH_CHARS = {
    "o": SwitchType.SOFT,
    "x": SwitchType.HEAVY,
    "p": SwitchType.SPLIT,
}


class LevelError(ValueError):
    """File màn chơi không hợp lệ."""


@dataclass
class Level:
    """Một màn chơi đã nạp: ``problem`` cho solver + metadata cho GUI."""

    name: str
    group: str
    description: str
    rows: int
    cols: int
    problem: Problem
    bridge_groups: List[Tuple[Cell, ...]] = field(default_factory=list)
    path: str = ""
    section: str = "custom"  # "classic" (màn gốc của game) hoặc "custom" (màn nhóm tự thiết kế)
    reference_moves: Optional[int] = None  # số nước tối thiểu đã biết (nếu có), dùng để kiểm thử

    def bridge_group_of(self, cell: Cell) -> int:
        for i, cells in enumerate(self.bridge_groups):
            if cell in cells:
                return i
        return -1


def _cell(value, what: str) -> Cell:
    try:
        r, c = value
        return int(r), int(c)
    except (TypeError, ValueError) as exc:
        raise LevelError(f"{what}: toạ độ không hợp lệ {value!r}") from exc


def level_from_dict(data: dict, path: str = "") -> Level:
    name = data.get("name", Path(path).stem or "Untitled")
    where = f"Màn '{name}'"

    grid_rows = data.get("grid")
    if not grid_rows:
        raise LevelError(f"{where}: thiếu 'grid'")
    rows = len(grid_rows)
    cols = max(len(row) for row in grid_rows)

    grid: Dict[Cell, TileType] = {}
    switch_chars: Dict[Cell, str] = {}
    starts: List[Cell] = []
    goals: List[Cell] = []
    for r, row in enumerate(grid_rows):
        for c, ch in enumerate(row):
            if ch in (".", " "):
                continue
            tile = _TILE_CHARS.get(ch)
            if tile is None:
                raise LevelError(f"{where}: ký tự lạ {ch!r} tại ({r}, {c})")
            grid[(r, c)] = tile
            if ch == "S":
                starts.append((r, c))
            elif ch == "G":
                goals.append((r, c))
            elif ch in _SWITCH_CHARS:
                switch_chars[(r, c)] = ch
    if len(starts) != 1:
        raise LevelError(f"{where}: cần đúng một ô 'S' (có {len(starts)})")
    if len(goals) != 1:
        raise LevelError(f"{where}: cần đúng một ô 'G' (có {len(goals)})")

    # ----- cầu -----
    bridge_groups: List[Tuple[Cell, ...]] = []
    bridge_indices: Dict[Cell, int] = {}
    initial_bridges: List[bool] = []
    for i, spec in enumerate(data.get("bridges", [])):
        cells = tuple(_cell(c, f"{where}: bridges[{i}]") for c in spec["cells"])
        for cell in cells:
            if grid.get(cell) != TileType.BRIDGE:
                raise LevelError(f"{where}: bridges[{i}] ô {cell} không phải 'B'")
            if cell in bridge_indices:
                raise LevelError(f"{where}: ô cầu {cell} thuộc hai nhóm")
            bridge_indices[cell] = len(initial_bridges)
            initial_bridges.append(bool(spec.get("open", False)))
        bridge_groups.append(cells)
    for cell, tile in grid.items():
        if tile == TileType.BRIDGE and cell not in bridge_indices:
            raise LevelError(f"{where}: ô cầu {cell} chưa thuộc nhóm nào")

    # ----- công tắc -----
    switches: Dict[Cell, Switch] = {}
    for i, spec in enumerate(data.get("switches", [])):
        pos = _cell(spec["pos"], f"{where}: switches[{i}]")
        ch = switch_chars.get(pos)
        if ch is None:
            raise LevelError(f"{where}: switches[{i}] tại {pos} nhưng grid không có o/x/p")
        if pos in switches:
            raise LevelError(f"{where}: hai công tắc trùng ô {pos}")

        def parse_mode(name):
            if name == "toggle":
                return SwitchMode.TOGGLE, True
            if name in ("open", "close"):
                return SwitchMode.PERMANENT, name == "open"
            raise LevelError(f"{where}: switches[{i}] mode {name!r} không hợp lệ")

        def group_cells(g):
            if not isinstance(g, int) or not 0 <= g < len(bridge_groups):
                raise LevelError(f"{where}: switches[{i}] trỏ tới nhóm cầu {g!r} không tồn tại")
            return bridge_groups[g]

        linked: List[Cell] = []
        effects = None
        if "effects" in spec:
            # Hiệu ứng riêng cho từng nhóm cầu: [{"bridge": g, "mode": "toggle|open|close"}, ...]
            if "link" in spec or "mode" in spec:
                raise LevelError(f"{where}: switches[{i}] không dùng 'effects' cùng 'link'/'mode'")
            effects = []
            for eff in spec["effects"]:
                mode, target = parse_mode(eff.get("mode", "toggle"))
                for cell in group_cells(eff.get("bridge")):
                    effects.append((cell, mode, target))
                    if cell not in linked:
                        linked.append(cell)
            mode, target = SwitchMode.TOGGLE, True
        else:
            for g in spec.get("link", []):
                linked.extend(group_cells(g))
            mode, target = parse_mode(spec.get("mode", "toggle"))

        split_targets = None
        split_active = 0
        if _SWITCH_CHARS[ch] == SwitchType.SPLIT:
            raw = spec.get("targets")
            if not raw or len(raw) != 2:
                raise LevelError(f"{where}: công tắc split tại {pos} cần đúng 2 'targets'")
            a, b = (_cell(t, f"{where}: targets") for t in raw)
            split_targets = (a, b)
            split_active = spec.get("active", 0)
            if split_active not in (0, 1):
                raise LevelError(f"{where}: 'active' của công tắc split tại {pos} phải là 0 hoặc 1")
        elif not linked:
            raise LevelError(f"{where}: công tắc tại {pos} không link tới cầu nào")
        switches[pos] = Switch(
            pos=pos,
            switch_type=_SWITCH_CHARS[ch],
            linked_bridges=linked,
            mode=mode,
            target_state=target,
            split_targets=split_targets,
            effects=effects,
            split_active=split_active,
        )
    for pos in switch_chars:
        if pos not in switches:
            raise LevelError(f"{where}: ô công tắc {pos} chưa khai báo trong 'switches'")

    goal = goals[0]
    for sw in switches.values():
        if sw.split_targets is None:
            continue
        a, b = sw.split_targets
        for t in (a, b):
            if t not in grid:
                raise LevelError(f"{where}: đích dịch chuyển {t} là ô trống")
            if t == goal:
                raise LevelError(f"{where}: đích dịch chuyển {t} trùng ô đích")
        if a == b or abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1:
            raise LevelError(f"{where}: hai đích dịch chuyển {a}, {b} không được trùng/kề nhau")

    problem = Problem(
        grid=grid,
        goal_pos=goal,
        initial_state=State(
            Orientation.STANDING, starts[0], bridges_state=tuple(initial_bridges)
        ),
        bridge_indices=bridge_indices,
        switches=switches,
    )
    return Level(
        name=name,
        group=data.get("group", "custom"),
        description=data.get("description", ""),
        rows=rows,
        cols=cols,
        problem=problem,
        bridge_groups=bridge_groups,
        path=path,
        reference_moves=data.get("reference_moves"),
    )


def load_level(path, section: str = "custom") -> Level:
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        level = level_from_dict(json.load(fh), str(path))
    level.section = section
    return level


def load_levels(directory, section: str = "custom") -> List[Level]:
    """Nạp mọi ``*.json`` trong thư mục, sắp theo tên file."""
    return [load_level(p, section) for p in sorted(Path(directory).glob("*.json"))]
