"""Chế độ "Race": hai thuật toán phát lại lời giải của chúng cạnh nhau, mỗi bên một bàn cờ riêng.

Hai làn đi lockstep từng hành động nên lời giải ngắn hơn về đích trước. Mỗi làn có renderer,
trạng thái cầu và màu khối riêng (vàng / tím) để dễ phân biệt.
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
    def __init__(self, level, rows: Sequence[Dict], cam: Camera, area: Optional[pygame.Rect] = None, arctic_theme: bool = False):
        self.level = level
        self.state = RaceState(level, rows)
        area = area or theme.BOARD_VIEW
        gap = 14
        w = (area.w - gap) // 2
        self.lane_rects = [
            pygame.Rect(area.x + 10, area.y, w - 10, area.h),
            pygame.Rect(area.x + w + gap, area.y, w - 10, area.h),
        ]
        self.renderers: List[BoardRenderer] = [
            BoardRenderer(level, area=r.inflate(-16, -90).move(0, 30), cam=cam, arctic_theme=arctic_theme) for r in self.lane_rects
        ]
        self.paths = [path_steps(level.problem, lane.actions) for lane in self.state.lanes]
        self.restart()

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
        for i, lane in enumerate(self.state.lanes):
            rect = self.lane_rects[i]
            rd = self.renderers[i]
            col = LANE_COLORS[i]
            rrect(surf, rect, (16, 20, 32, 150), 22, col, 2)
            rd.draw_board(surf)
            if show_path:
                rd.draw_path(surf, self.paths[i], done=lane.index, palette=LANE_PATH[i])
            self._draw_lane_pieces(surf, i)
            rd.draw_particles(surf)

            # tiêu đề làn
            draw_text(surf, lane.label, theme.font(34, True), col, (rect.x + 24, rect.y + 16))
            cost = lane.row.get("cost", "-")
            draw_text(
                surf, f"step {lane.index}/{lane.total}    moves {lane.moves_done}    cost {cost}",
                theme.font(19), theme.TEXT_DIM, (rect.x + 26, rect.y + 62),
            )
            if lane.finished and self.tween[i] is None:
                rank = ranks.get(lane.label)
                tag = "FINISHED"
                if rank == 1 and len(set(ranks.values())) > 1:
                    tag = "FINISHED FIRST"
                elif rank == 2:
                    tag = "FINISHED SECOND"
                f = theme.font(17, True)
                chip = pygame.Rect(0, 0, f.size(tag)[0] + 30, 32)
                chip.topright = (rect.right - 22, rect.y + 20)
                rrect(surf, chip, (*theme.GOOD, 46), 16, theme.GOOD, 2)
                draw_text(surf, tag, f, theme.GOOD, chip.center, "center")
            # thanh tiến độ
            bar = pygame.Rect(rect.x + 26, rect.y + 92, rect.w - 52, 8)
            rrect(surf, bar, (44, 52, 76), 4)
            frac = lane.index / max(1, lane.total)
            rrect(surf, pygame.Rect(bar.x, bar.y, max(8, int(bar.w * frac)), bar.h), col, 4)

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
            piece = {"cells": (goal,), "kind": "block", "height": 2.0, "active": True}
            self._draw_piece(surf, i, piece, dz=-smoothstep(f / 0.7) * 2.1, alpha=1.0 - max(0.0, (f / 0.7 - 0.45) / 0.55))
            return
        for pc in sorted(pieces_of(lane.session.state), key=lambda q: self.renderers[i].iso.order(*q["cells"][0])):
            pc["frame"] = self.lane_frames[i]
            self._draw_piece(surf, i, pc)
