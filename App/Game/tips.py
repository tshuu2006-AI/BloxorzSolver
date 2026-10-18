"""Gợi ý hướng dẫn hiện một lần khi người chơi lần đầu gặp mỗi cơ chế (ô mỏng, công tắc, ...)."""

from __future__ import annotations

from typing import Collection, Dict, Optional, Set, Tuple

from App.Components.features import SwitchType, TileType

# khoá -> (tiêu đề, nội dung)
TIPS: Dict[str, Tuple[str, str]] = {
    "basics": (
        "Rolling the block",
        "Roll with the arrow keys or WASD. Stand the block upright on the hole to win; "
        "rolling off the platform loses. Z undoes, R restarts.",
    ),
    "fragile": (
        "Fragile tiles",
        "Orange tiles crack if the whole block stands on them. Lie the block across them instead.",
    ),
    "switch": (
        "Switches and bridges",
        "A round switch works with any part of the block. Matching colours link a switch to its "
        "bridges: it can open them, close them or flip them.",
    ),
    "heavy": (
        "Heavy switches",
        "An X-shaped switch only triggers when the block stands upright on it. Lying across it does nothing.",
    ),
    "split": (
        "Splitting the block",
        "The bracket tile splits the block into two cubes. Press Space to swap cubes; put them side by side "
        "to merge again. A cube that rolls into the hole is lost.",
    ),
}
ORDER = ("basics", "fragile", "switch", "heavy", "split")


def mechanics(level) -> Set[str]:
    """Các cơ chế (khoá trong ``TIPS``, trừ "basics") mà màn chơi này dùng."""
    pb = level.problem
    found: Set[str] = set()
    if any(t == TileType.FRAGILE for t in pb.grid.values()):
        found.add("fragile")
    for sw in pb.switches.values():
        if sw.switch_type == SwitchType.SOFT:
            found.add("switch")
        elif sw.switch_type == SwitchType.HEAVY:
            found.add("heavy")
        elif sw.switch_type == SwitchType.SPLIT:
            found.add("split")
    return found


def tip_for(level, seen: Collection[str]) -> Optional[str]:
    """Gợi ý đầu tiên chưa xem mà màn này cần ("basics" luôn đến trước)."""
    needed = mechanics(level)
    for key in ORDER:
        if key in seen:
            continue
        if key == "basics" or key in needed:
            return key
    return None
