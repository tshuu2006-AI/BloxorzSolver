"""Chế độ "Race": hai thuật toán phát lại lời giải của chúng cạnh nhau, mỗi bên một bàn cờ riêng.

Hai làn đi lockstep từng hành động nên lời giải ngắn hơn về đích trước. Mỗi làn có renderer,
trạng thái cầu và màu khối riêng (vàng / tím) để dễ phân biệt.
Hỗ trợ cả chủ đề Bắc Cực (chim cánh cụt) và Sa Mạc (cây xương rồng).
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence

import pygame

from App.GUI import theme
from App.GUI.models import frame_for_orientation, roll_frame
from App.GUI.pieces import pieces_of
from App.GUI.render import BoardRenderer, Camera, smoothstep
from App.GUI.widgets import draw_text, rrect
from App.Game.path import path_steps
from App.Game.race_logic import RaceState
from App.Game.session import DELTAS, Outcome

ROLL_DUR = 0.24
LANE_COLORS = [theme.BLOCK, (178, 132, 250)]  # vàng, tím
LANE_PATH = [(theme.INFO, theme.ACCENT), ((120, 200, 255), (178, 132, 250))]


class Race:
    def __init__(
        self,
        level,
        rows: Sequence[Dict],
        cam: Camera,
        area: Optional[pygame.Rect] = None,
        arctic_theme: bool = False,
        theme_name: Optional[str] = None,
    ):
        self.level = level
        self.state = RaceState(level, rows)
        if theme_name is not None:
            self.theme_name = theme_name
        else:
            self.theme_name = "arctic" if arctic_theme else "desert"

        # Bố cục 2 làn gọn gàng bên trái màn hình (để dành chỗ cho bảng telemetry bên phải)
        area = area or pygame.Rect(40, 110, 1380, 820)
        gap = 18
        w = (area.w - gap) // 2
        self.lane_rects = [
            pygame.Rect(area.x, area.y, w, area.h),
            pygame.Rect(area.x + w + gap, area.y, w, area.h),
        ]
        self.renderers: List[BoardRenderer] = [
            BoardRenderer(
                level,
                area=r.inflate(-20, -110).move(0, 42),
                cam=cam,
                theme_name=self.theme_name,
            )
            for r in self.lane_rects
        ]
        self.paths = [path_steps(level.problem, lane.actions) for lane in self.state.lanes]
        self.restart()

    def set_theme(self, theme_name: str) -> None:
        self.theme_name = theme_name
        for r in self.renderers:
            r.set_theme(theme_name)

    # ------------------------------------------------------------------ điều khiển
    def restart(self) -> None:
        self.state.reset()
        initial = self.state.lanes[0].session.state.bridges_state
        for r in self.renderers:
            r.set_bridges(initial, snap=True)
            r.particles.clear()
        self.lane_frames = [frame_for_orientation(self.level.problem.initial_state.orientation) for _ in range(2)]
        self.tween: List[Optional[dict]] = [None, None]
        self.fx: List[Optional[float]] = [None, None]  # thời gian từ lúc làn về đích (hiệu ứng chìm xuống hố)
        self.wait = 0.5

    def set_camera(self, cam: Camera) -> None:
        for r in self.renderers:
            r.set_camera(cam)

    # ------------------------------------------------------------------ cập nhật
    def update(self, dt: float, speed: float, paused: bool) -> None:
        for r in self.renderers:
            r.update(dt)
        for i, tw in enumerate(self.tween):
            if tw is None:
                continue
            tw["t"] += dt * speed
            if tw["t"] >= ROLL_DUR:
                self.renderers[i].set_bridges(tw["bridges"])
                if "action" in tw:
                    self.lane_frames[i] = roll_frame(self.lane_frames[i], tw["action"])
                self.tween[i] = None
        for i, lane in enumerate(self.state.lanes):
            if lane.finished and self.tween[i] is None and self.fx[i] is None:
                self.fx[i] = 0.0
                self.renderers[i].burst(self.level.problem.goal_pos)
            elif self.fx[i] is not None:
                self.fx[i] += dt
        if paused or any(self.tween) or self.state.done:
            return
        self.wait -= dt
        if self.wait > 0:
            return
        events = self.state.advance()
        for i, ev in enumerate(events):
            if ev is None or ev.outcome not in (Outcome.MOVED, Outcome.WON):
                continue
            prev = ev.prev
            pcs = pieces_of(prev)
            if prev.is_split:
                k = prev.active_block
                moving, statics = pcs[k], [pcs[1 - k]]
            else:
                moving, statics = pcs[0], []
            moving["frame"] = self.lane_frames[i]
            self.tween[i] = {
                "piece": moving, "statics": statics, "dir": DELTAS[ev.action], "action": ev.action, "t": 0.0,
                "bridges": ev.new.bridges_state,
            }
        self.wait = 0.12 / max(0.1, speed)

    # ------------------------------------------------------------------ vẽ
    def _draw_piece(self, surf, i: int, piece: dict, **kw) -> None:
        color = LANE_COLORS[i] if piece["kind"] == "block" else None
        frame = kw.pop("frame", piece.get("frame"))
        self.renderers[i].draw_piece(
            surf, piece["cells"], piece["kind"], piece["height"], active=piece["active"], color=color, frame=frame, **kw
        )

    def draw(self, surf, mouse, show_path: bool = True) -> None:
        ranks = self.state.ranks() if self.state.done else {}
        is_desert = (self.theme_name == "desert")
        for i, lane in enumerate(self.state.lanes):
            rect = self.lane_rects[i]
            rd = self.renderers[i]
            col = LANE_COLORS[i]
            bg_col = (34, 20, 28, 200) if is_desert else (16, 24, 38, 200)
            rrect(surf, rect, bg_col, 20, col, 2)
            rd.draw_board(surf)
            if show_path:
                rd.draw_path(surf, self.paths[i], done=lane.index, palette=LANE_PATH[i])
            self._draw_lane_pieces(surf, i)
            rd.draw_particles(surf)

            # Tiêu đề làn
            draw_text(surf, lane.label, theme.font(28, True), col, (rect.x + 22, rect.y + 16))
            cost = lane.row.get("cost", "-")
            draw_text(
                surf, f"Step {lane.index}/{lane.total}   |   Moves {lane.moves_done}   |   Cost {cost}",
                theme.font(16), theme.TEXT_DIM, (rect.x + 24, rect.y + 52),
            )
            if lane.finished and self.tween[i] is None:
                rank = ranks.get(lane.label)
                tag = "1ST PLACE" if rank == 1 else "2ND PLACE"
                f = theme.font(15, True)
                chip = pygame.Rect(0, 0, f.size(tag)[0] + 24, 28)
                chip.topright = (rect.right - 18, rect.y + 18)
                rrect(surf, chip, (*theme.GOOD, 50), 14, theme.GOOD, 2)
                draw_text(surf, tag, f, theme.GOOD, chip.center, "center")

            # Thanh tiến độ
            bar = pygame.Rect(rect.x + 22, rect.y + 80, rect.w - 44, 6)
            rrect(surf, bar, (42, 26, 36) if is_desert else (28, 40, 62), 3)
            frac = lane.index / max(1, lane.total)
            rrect(surf, pygame.Rect(bar.x, bar.y, max(6, int(bar.w * frac)), bar.h), col, 3)

    def _draw_lane_pieces(self, surf, i: int) -> None:
        lane = self.state.lanes[i]
        tw = self.tween[i]
        if tw is not None:
            p = min(1.0, tw["t"] / ROLL_DUR)
            for s in tw["statics"]:
                self._draw_piece(surf, i, s)
            self._draw_piece(surf, i, tw["piece"], roll=(tw["dir"], smoothstep(p) * math.pi / 2))
            return
        if lane.finished and self.fx[i] is not None:
            f = self.fx[i]
            if f > 0.7:
                return  # đã rơi xuống hố
            goal = self.level.problem.goal_pos
            piece = {"cells": (goal,), "kind": "block", "height": 2.0, "active": True, "frame": self.lane_frames[i]}
            self._draw_piece(surf, i, piece, dz=-smoothstep(f / 0.7) * 2.1, alpha=1.0 - max(0.0, (f / 0.7 - 0.45) / 0.55))
            return
        for pc in sorted(pieces_of(lane.session.state), key=lambda q: self.renderers[i].iso.order(*q["cells"][0])):
            pc["frame"] = self.lane_frames[i]
            self._draw_piece(surf, i, pc)
