"""Quan hệ công tắc -> cầu / điểm dịch chuyển, để GUI vẽ đường nối gợi ý (tuỳ chọn trong Settings)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from App.Components.features import SwitchMode

Cell = Tuple[int, int]


@dataclass(frozen=True)
class LinkSegment:
    source: Cell  # ô chứa công tắc
    target: Tuple[float, float]  # (r, c) điểm cuối: tâm nhóm cầu hoặc tâm ô đích dịch chuyển
    kind: str  # "toggle" | "open" | "close" (công tắc cầu) hoặc "split" (đích dịch chuyển)
    group: int  # chỉ số nhóm cầu (chọn màu); -1 với "split"


def link_segments(level) -> List[LinkSegment]:
    """Mỗi công tắc một đoạn tới từng nhóm cầu nó điều khiển (không phải từng ô cầu), cộng với
    một đoạn tới mỗi ô đích nếu là công tắc dịch chuyển."""
    segments: List[LinkSegment] = []
    for pos, sw in sorted(level.problem.switches.items()):
        seen = {}  # nhóm cầu -> (mode, target_state) của hiệu ứng đầu tiên lên nhóm đó
        for cell, mode, target in sw.bridge_effects():
            g = level.bridge_group_of(cell)
            if g >= 0 and g not in seen:
                seen[g] = (mode, target)
        for g, (mode, target) in seen.items():
            cells = level.bridge_groups[g]
            centre = (
                sum(r for r, _ in cells) / len(cells) + 0.5,
                sum(c for _, c in cells) / len(cells) + 0.5,
            )
            if mode == SwitchMode.TOGGLE:
                kind = "toggle"
            else:
                kind = "open" if target else "close"
            segments.append(LinkSegment(pos, centre, kind, g))
        if sw.split_targets:
            for r, c in sw.split_targets:
                segments.append(LinkSegment(pos, (r + 0.5, c + 0.5), "split", -1))
    return segments
