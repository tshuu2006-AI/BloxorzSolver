"""Cửa sổ chính của game Bloxorz (pygame, canvas logic 1920x1080).

Phím: mũi tên / WASD lăn khối, Space đổi khối đơn, R chơi lại, Z hoàn tác,
N chọn màn, Enter sang màn kế khi thắng, F11 toàn màn hình.
Các phím mũi tên khớp với trục của bàn: Right = sang phải (Tây -> Đông),
Left = sang trái, Up = lên-trái (về phía trục hàng ``r`` giảm), Down = xuống-phải.
"""

from __future__ import annotations

import ctypes
import math
import os
import sys
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional

import pygame

from App.Components.features import SwitchType, TileType
from App.Components.level_loader import Level, load_levels
from App.Components.state import Orientation, State
from App.Game.path import path_steps
from App.Game.progress import Progress
from App.Game.session import DELTAS, GameSession, Outcome, Status
from App.Game.solver_bridge import (
    HEURISTICS,
    SOLVER_ORDER,
    SolveOutcome,
    SolverJob,
    available_solvers,
)
from App.GUI import theme
from App.GUI.render import BoardRenderer, Camera, smoothstep
from App.GUI.widgets import (
    Button,
    Segmented,
    Slider,
    draw_text,
    rrect,
    vgradient,
    wrap_text,
)

LEVELS_DIR = Path(__file__).resolve().parents[2] / "levels"
CLASSIC_DIR = LEVELS_DIR / "classic"
PROGRESS_PATH = Path(__file__).resolve().parents[2] / ".bloxorz_progress.json"

KEY_ACTIONS = {
    pygame.K_UP: "U", pygame.K_w: "U",
    pygame.K_DOWN: "D", pygame.K_s: "D",
    pygame.K_LEFT: "L", pygame.K_a: "L",
    pygame.K_RIGHT: "R", pygame.K_d: "R",
}
SOLVER_SUB = {
    "BFS": "breadth-first",
    "DFS": "depth-first",
    "UCS": "uniform-cost",
    "A*": "heuristic",
}
SOLVER_COLORS = {
    "BFS": (92, 190, 236),
    "DFS": (236, 120, 210),
    "UCS": (140, 218, 92),
    "A*": (255, 196, 64),
}


# ---------------------------------------------------------------------------
# Khối hiển thị
# ---------------------------------------------------------------------------
def pieces_of(state: State) -> List[dict]:
    cells = state.get_occupied_cells()
    if state.is_split:
        return [
            {"cells": (cells[i],), "kind": "cube", "height": 1.0, "active": i == state.active_block}
            for i in range(2)
        ]
    height = 2.0 if state.orientation == Orientation.STANDING else 1.0
    return [{"cells": tuple(cells), "kind": "block", "height": height, "active": True}]


class Anim:
    kind = ""

    def __init__(self, dur, on_start=None, on_finish=None, statics=None):
        self.dur = dur
        self.t = 0.0
        self.started = False
        self.on_start = on_start
        self.on_finish = on_finish
        self.statics = statics or []


class RollAnim(Anim):
    kind = "roll"

    def __init__(self, piece, direction, **kw):
        super().__init__(0.24, **kw)
        self.piece, self.direction = piece, direction


class FallAnim(Anim):
    kind = "fall"

    def __init__(self, piece, **kw):
        super().__init__(0.55, **kw)
        self.piece = piece


class SinkAnim(Anim):
    kind = "sink"

    def __init__(self, piece, **kw):
        super().__init__(0.7, **kw)
        self.piece = piece


class SpawnAnim(Anim):
    kind = "spawn"

    def __init__(self, pieces, **kw):
        super().__init__(0.45, **kw)
        self.pieces = pieces


# ---------------------------------------------------------------------------
class App:
    def __init__(self, start_level: int = 0):
        try:  # giữ nét trên màn hình có scale DPI
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
        # Canvas 1920x1080 được GPU phóng ra màn hình thật. Mặc định pygame dùng lọc
        # "nearest" nên khi tỉ lệ không nguyên (vd 1.5x trên 2880x1800) các nét bị vỡ
        # răng cưa; lọc tuyến tính cho ảnh mượt.
        os.environ.setdefault("PYGAME_FORCE_SCALE", "photo")
        os.environ.setdefault("SDL_RENDER_SCALE_QUALITY", "linear")
        pygame.init()
        pygame.display.set_caption("Bloxorz")
        self._open_window()
        self.clock = pygame.time.Clock()
        self.bg = vgradient((theme.WIDTH, theme.HEIGHT), theme.BG_TOP, theme.BG_BOTTOM)

        # Classic = 33 màn gốc của game; custom = các màn nhóm tự thiết kế.
        self.levels: List[Level] = load_levels(CLASSIC_DIR, "classic") if CLASSIC_DIR.exists() else []
        self.levels += load_levels(LEVELS_DIR, "custom")
        if not self.levels:
            raise SystemExit(f"Không tìm thấy màn chơi trong {LEVELS_DIR}")
        self.picker_tab = self.levels[0].section
        self.progress = Progress(PROGRESS_PATH)
        self.picker_scroll = 0.0
        self.picker_sel = 0
        self.used_solver = False
        self.thumbs: Dict[int, pygame.Surface] = {}
        self.picker_open = False
        self.running = True

        self.toasts: List[dict] = []
        self.key_flash = {"U": 0.0, "D": 0.0, "L": 0.0, "R": 0.0}
        self.show_path = True
        self.path_steps: List[dict] = []
        self.replay_done: List[str] = []
        self.step_req = 0
        self.cam = Camera()
        self.cam_dirty = False
        self.cam_drag = None  # "rotate" | "pan" khi đang kéo chuột
        self.heuristic = "relaxed"
        self.speed = 1.5
        self.job: Optional[SolverJob] = None
        self.stats: Optional[SolveOutcome] = None
        self.available = available_solvers()
        self._avail_timer = 0.0

        self._build_widgets()
        self.load_level(max(0, min(start_level, len(self.levels) - 1)))

    # ------------------------------------------------------------------ cửa sổ
    def _open_window(self):
        size = (theme.WIDTH, theme.HEIGHT)
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except Exception:
            dw, dh = size
        flags = pygame.SCALED | pygame.RESIZABLE
        if dw < theme.WIDTH + 40 or dh < theme.HEIGHT + 120:
            flags = pygame.SCALED | pygame.FULLSCREEN  # màn nhỏ: toàn màn hình, F11 để thoát
        self.screen = pygame.display.set_mode(size, flags)

    # ------------------------------------------------------------------ widget
    def _build_widgets(self):
        x0 = theme.PANEL_RECT.x + 28
        w = theme.PANEL_RECT.w - 56
        self.x0, self.pw = x0, w
        bw = (w - 24) // 3
        self.btn_new = Button((x0, 346, bw, 56), "New Game", self.open_picker, "primary")
        self.btn_restart = Button((x0 + bw + 12, 346, bw, 56), "Restart", self.restart)
        self.btn_undo = Button((x0 + 2 * (bw + 12), 346, bw, 56), "Undo", self.undo)

        self.solver_buttons: Dict[str, Button] = {}
        sw = (w - 12) // 2
        for i, name in enumerate(SOLVER_ORDER):
            rect = (x0 + (i % 2) * (sw + 12), 452 + (i // 2) * 76, sw, 64)
            self.solver_buttons[name] = Button(
                rect, name, lambda n=name: self.start_solver(n), "secondary",
                accent=SOLVER_COLORS[name], sublabel=SOLVER_SUB[name],
            )
        self.heur_seg = Segmented(
            (x0, 640, w, 40), HEURISTICS, HEURISTICS.index(self.heuristic), self._set_heuristic
        )
        right = x0 + w
        self.btn_fwd = Button((right - 60, 704, 60, 52), "", lambda: self._request_step(1), tooltip="Step forward  (.)", icon="fwd")
        self.btn_pause = Button((right - 60 - 8 - 100, 704, 100, 52), "Pause", self.toggle_pause)
        self.btn_back = Button((right - 60 - 8 - 100 - 8 - 60, 704, 60, 52), "", lambda: self._request_step(-1), tooltip="Step back  (,)", icon="back")
        self.slider = Slider((x0, 736, self.btn_back.rect.x - 20 - x0, 24), 0.5, 4.0, self.speed, "Replay speed")
        self.btn_path = Button((x0 + w - 148, 816, 128, 34), "Path: on", self.toggle_path, font_size=17)

        # nút trong banner thắng / thua
        cx = theme.BOARD_AREA.centerx
        self.banner_rect = pygame.Rect(cx - 330, 872, 660, 170)
        r = self.banner_rect
        self.btn_next = Button((r.x + 36, r.bottom - 70, 280, 50), "Next stage  (Enter)", self.next_level, "primary")
        self.btn_stages = Button((r.right - 316, r.bottom - 70, 280, 50), "Stage select  (N)", self.open_picker)
        self.btn_banner_undo = Button((r.x + 36, r.bottom - 70, 280, 50), "Undo  (Z)", self.undo, "primary")
        self.btn_banner_restart = Button((r.right - 316, r.bottom - 70, 280, 50), "Restart  (R)", self.restart)
        self.paused = False

    def _set_heuristic(self, name: str):
        self.heuristic = name

    def _main_buttons(self) -> List[Button]:
        return [
            self.btn_new, self.btn_restart, self.btn_undo, *self.solver_buttons.values(),
            self.btn_back, self.btn_pause, self.btn_fwd, self.btn_path,
        ]

    def _banner_buttons(self) -> List[Button]:
        if self.anims:
            return []
        if self.session.status == Status.WON:
            return [self.btn_next, self.btn_stages]
        if self.session.status == Status.LOST:
            return [self.btn_banner_undo, self.btn_banner_restart]
        return []

    # ------------------------------------------------------------------ màn chơi
    def load_level(self, index: int):
        self.level_idx = index
        self.level = self.levels[index]
        self.session = GameSession(self.level)
        self.renderer = BoardRenderer(self.level, cam=self.cam)
        self.renderer.set_bridges(self.session.state.bridges_state, snap=True)
        self.anims: Deque[Anim] = deque()
        self.queued: Optional[str] = None
        self.replay: Deque[str] = deque()
        self.replay_timer = 0.0
        self.replay_total = 0
        self.replay_label = ""
        self.paused = False
        self.used_solver = False
        self.lost_cells = None
        self.job = None
        self.stats = None
        self.path_steps = []
        self.replay_done = []
        self.toasts.clear()
        self.picker_open = False
        self.toast(self.level.name, theme.group_color(self.level.group), 2.0)

    def restart(self):
        self._reset_play()
        self.session.reset()
        self.renderer.set_bridges(self.session.state.bridges_state)

    def _reset_play(self):
        self.used_solver = False
        self.replay_done = []
        self.anims.clear()
        self.queued = None
        self.replay.clear()
        self.paused = False
        self.lost_cells = None

    def undo(self):
        if self.anims:
            self.anims.clear()
        self.replay.clear()
        self.replay_done = []
        if self.session.undo():
            self.lost_cells = None
            self.renderer.set_bridges(self.session.state.bridges_state)

    def next_level(self):
        self.load_level((self.level_idx + 1) % len(self.levels))

    def open_picker(self):
        self.picker_tab = self.level.section
        self.picker_sel = self.level_idx
        self.picker_scroll = 0.0
        self._picker_scroll_to(self.picker_sel)
        self.picker_open = True

    def toast(self, text: str, color=None, ttl: float = 2.6):
        self.toasts.append({"text": text, "color": color or theme.TEXT, "ttl": ttl, "age": 0.0})
        self.toasts = self.toasts[-3:]

    # ------------------------------------------------------------------ hành động
    def do_action(self, action: str, from_replay: bool = False):
        if action in self.key_flash:
            self.key_flash[action] = 1.0  # làm sáng hướng này trên la bàn / mũi tên sàn
        if self.anims:
            if not from_replay:
                self.queued = action
            return None
        if not from_replay:
            self.replay.clear()  # người chơi can thiệp: dừng replay
            self.replay_done.clear()
        ev = self.session.apply(action)
        self._present(ev)
        return ev

    def _present(self, ev):
        o = ev.outcome
        if o == Outcome.IGNORED:
            return
        if o == Outcome.BLOCKED:
            self.toast(ev.reason, theme.BAD)
            return
        if o == Outcome.SWITCHED:
            return

        prev = ev.prev
        pcs = pieces_of(prev)
        if prev.is_split:
            i = prev.active_block
            moving, statics = pcs[i], [pcs[1 - i]]
        else:
            moving, statics = pcs[0], []
        direction = DELTAS[ev.action]

        def after_roll():
            if ev.new is not None:
                self.renderer.set_bridges(ev.new.bridges_state)
                opened = [i for i, v in ev.bridge_changes.items() if v]
                closed = [i for i, v in ev.bridge_changes.items() if not v]
                if opened and closed:
                    self.toast("Bridges toggled", theme.INFO)
                elif opened:
                    self.toast("Bridge opened", theme.GOOD)
                elif closed:
                    self.toast("Bridge closed", theme.BAD)
                if ev.merged:
                    self.toast("Cubes merged back into a block", theme.CUBE)

        anims: List[Anim] = [RollAnim(moving, direction, statics=statics, on_finish=after_roll)]
        if o == Outcome.FELL:
            cells = ev.fall_cells
            if prev.is_split:
                piece = {"cells": cells, "kind": "cube", "height": 1.0, "active": True}
            else:
                piece = {
                    "cells": cells, "kind": "block",
                    "height": 2.0 if len(cells) == 1 else 1.0, "active": True,
                }
            self.lost_cells = moving["cells"]
            anims.append(FallAnim(piece, statics=statics))
        elif o == Outcome.WON:
            goal = self.level.problem.goal_pos
            if not self.used_solver and self.progress.record_win(self.level.name, self.session.moves):
                self.toast(f"New best: {self.session.moves} moves", theme.GOOD, 3.0)
            piece = {"cells": (goal,), "kind": "block", "height": 2.0, "active": True}
            anims.append(SinkAnim(piece, on_start=lambda: self.renderer.burst(goal)))
        elif ev.teleported:
            anims.append(SpawnAnim(
                pieces_of(ev.new),
                on_start=lambda: self.toast("Split! Press Space to swap cubes", theme.SPLIT_COLOR, 3.2),
            ))
        self.anims.extend(anims)

    # ------------------------------------------------------------------ solver
    def start_solver(self, name: str):
        if self.job is not None and not self.job.done:
            return
        self.restart()
        self.stats = None
        self.job = SolverJob(name, self.level.problem, self.heuristic if name == "A*" else None)
        self.job.start()

    def toggle_pause(self):
        self.paused = not self.paused

    def toggle_path(self):
        self.show_path = not self.show_path

    def _request_step(self, direction: int):
        self.step_req = direction

    def _poll_solver(self):
        job = self.job
        if job is None or not job.done:
            return
        self.job = None
        if job.problem is not self.level.problem:  # đã đổi màn trong lúc giải
            return
        out = job.outcome
        self.stats = out
        self.path_steps = path_steps(self.level.problem, out.actions) if out.found else []
        self.replay_done = []
        if out.error:
            self.toast(f"{job.label} failed: {out.error}", theme.BAD, 5.0)
        elif not out.found:
            self.toast(f"{job.label}: no solution found", theme.BAD, 4.0)
        else:
            self.replay = deque(out.actions)
            self.used_solver = True
            self.replay_total = len(out.actions)
            self.replay_label = job.label
            self.replay_timer = 0.5
            self.toast(f"{job.label}: replaying {len(out.actions)} actions", theme.INFO, 3.0)

    def _step_replay(self, dt: float):
        if not self.replay or self.paused or self.anims:
            return
        self.replay_timer -= dt
        if self.replay_timer > 0:
            return
        self._run_replay_action()

    def _process_step_request(self):
        """Nút / phím ``,`` ``.``: đi một hành động tới hoặc lùi trong replay."""
        direction, self.step_req = self.step_req, 0
        if not direction or self.anims:
            return
        self.paused = True
        if direction > 0 and self.replay:
            self._run_replay_action()
        elif direction < 0 and self.replay_done:
            action = self.replay_done.pop()
            if self.session.undo():
                self.replay.appendleft(action)
                self.lost_cells = None
                self.renderer.set_bridges(self.session.state.bridges_state)

    def _run_replay_action(self):
        action = self.replay.popleft()
        step = self.replay_total - len(self.replay)
        ev = self.do_action(action, from_replay=True)
        self.replay_timer = 0.12 / self.speed
        if ev is not None and ev.outcome in (Outcome.MOVED, Outcome.WON, Outcome.SWITCHED):
            self.replay_done.append(action)
        if ev is None or ev.outcome in (Outcome.FELL, Outcome.IGNORED, Outcome.BLOCKED):
            self.replay.clear()
            self.toast(
                f"{self.replay_label} returned an illegal action '{action}' at step {step}",
                theme.BAD, 6.0,
            )
        elif not self.replay and ev.outcome != Outcome.WON:
            self.toast("Replay finished without reaching the goal", theme.BAD, 4.0)

    # ------------------------------------------------------------------ sự kiện
    def handle(self, event, mouse):
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.KEYDOWN:
            self._key(event)
            return
        if self._camera_event(event, mouse):
            return
        if self.picker_open:
            if event.type == pygame.MOUSEWHEEL:
                self.picker_scroll = max(
                    0.0, min(float(self._picker_max_scroll()), self.picker_scroll - event.y * 70)
                )
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for key, rect in self._picker_tab_rects().items():
                    if rect.collidepoint(mouse):
                        self._set_picker_tab(key)
                        return
                if self._picker_view().collidepoint(mouse):
                    for i, rect in self._picker_cards().items():
                        if rect.collidepoint(mouse):
                            self.load_level(i)
                            return
                if not self._picker_panel().collidepoint(mouse):
                    self.picker_open = False
            return
        for btn in self._banner_buttons():
            if btn.handle(event, mouse):
                return
        for btn in self._main_buttons():
            if btn.handle(event, mouse):
                return
        if self.slider.handle(event, mouse):
            self.speed = self.slider.value
            return
        self.heur_seg.handle(event, mouse)

    def _key(self, event):
        k = event.key
        if k == pygame.K_F11:
            pygame.display.toggle_fullscreen()
        elif k == pygame.K_ESCAPE:
            self.picker_open = False
        elif self.picker_open:
            self._picker_key(k)
        elif k in KEY_ACTIONS:
            self.do_action(KEY_ACTIONS[k])
        elif k == pygame.K_SPACE:
            self.do_action("SWITCH")
        elif k == pygame.K_r:
            self.restart()
        elif k in (pygame.K_z, pygame.K_BACKSPACE):
            self.undo()
        elif k == pygame.K_n:
            self.open_picker()
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.session.status == Status.WON:
            self.next_level()
        elif k == pygame.K_p:
            self.toggle_pause()
        elif k == pygame.K_v:
            self.toggle_path()
        elif k == pygame.K_PERIOD:
            self._request_step(1)
        elif k == pygame.K_COMMA:
            self._request_step(-1)
        elif k == pygame.K_c:
            self.cam.reset()
            self.cam_dirty = True
            self.toast("Camera reset", theme.INFO, 1.4)

    # ------------------------------------------------------------------ camera
    def _in_board(self, mouse) -> bool:
        return mouse[0] < theme.PANEL_RECT.x - 6 and not self.picker_open

    def _camera_event(self, event, mouse) -> bool:
        """Zoom bằng cuộn chuột, xoay/nghiêng bằng kéo chuột phải, dịch bằng chuột giữa."""
        if event.type == pygame.MOUSEWHEEL and self._in_board(mouse):
            self.cam.zoom_by(1.12 ** event.y)
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (2, 3) and self._in_board(mouse):
            self.cam_drag = "rotate" if event.button == 3 else "pan"
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button in (2, 3) and self.cam_drag:
            self.cam_drag = None
            return True
        if event.type == pygame.MOUSEMOTION and self.cam_drag:
            dx, dy = event.rel
            if self.cam_drag == "rotate":
                self.cam.rotate(dx * 0.007, dy * 0.005)
            else:
                self.cam.pan[0] += dx
                self.cam.pan[1] += dy
            self.cam_dirty = True
            return True
        return False

    def _update_camera(self, dt: float) -> None:
        if not self.picker_open:
            keys = pygame.key.get_pressed()
            zoom = (keys[pygame.K_e] - keys[pygame.K_q]) * 1.5 * dt
            if zoom:
                self.cam.zoom_by(math.exp(zoom))
            spin = (keys[pygame.K_RIGHTBRACKET] - keys[pygame.K_LEFTBRACKET]) * 1.3 * dt
            tilt = (keys[pygame.K_PAGEUP] - keys[pygame.K_PAGEDOWN]) * 0.9 * dt
            if spin or tilt:
                self.cam.rotate(spin, tilt)
                self.cam_dirty = True
        if self.cam.update(dt) or self.cam_dirty:
            self.cam_dirty = False
            self.renderer.set_camera(self.cam)

    # ------------------------------------------------------------------ cập nhật
    def update(self, dt: float, mouse):
        for btn in self._main_buttons() + self._banner_buttons():
            btn.update(dt, mouse)
        self._avail_timer -= dt
        if self._avail_timer <= 0:
            self.available = available_solvers()
            self._avail_timer = 2.0
        busy_job = self.job is not None and not self.job.done
        for name, btn in self.solver_buttons.items():
            ok = self.available.get(name, False)
            btn.enabled = ok and not busy_job
            btn.sublabel = SOLVER_SUB[name] if ok else "not implemented"
        self.btn_undo.enabled = self.session.can_undo
        self.btn_pause.enabled = bool(self.replay)
        self.btn_pause.label = "Resume" if (self.paused and self.replay) else "Pause"
        self.btn_fwd.enabled = bool(self.replay)
        self.btn_back.enabled = bool(self.replay_done)
        self.btn_path.enabled = bool(self.path_steps)
        self.btn_path.label = "Path: on" if self.show_path else "Path: off"

        self._poll_solver()
        self._update_camera(dt)
        self.renderer.update(dt)

        replaying = bool(self.replay)
        speed = self.speed if replaying else 1.0
        if self.anims:
            anim = self.anims[0]
            if not anim.started:
                anim.started = True
                if anim.on_start:
                    anim.on_start()
            anim.t += dt * speed
            if anim.t >= anim.dur:
                self.anims.popleft()
                if anim.on_finish:
                    anim.on_finish()
        elif self.queued:
            action, self.queued = self.queued, None
            self.do_action(action)
        self._process_step_request()
        self._step_replay(dt)

        for k in self.key_flash:
            self.key_flash[k] = max(0.0, self.key_flash[k] - dt * 4.0)
        for t in self.toasts:
            t["age"] += dt
        self.toasts = [t for t in self.toasts if t["age"] < t["ttl"]]

    # ------------------------------------------------------------------ vẽ
    def draw_piece(self, surf, piece, **kw):
        self.renderer.draw_piece(
            surf, piece["cells"], piece["kind"], piece["height"],
            active=piece["active"], **kw,
        )

    def _draw_pieces(self, surf):
        rd = self.renderer
        st = self.session.state
        if self.anims:
            anim = self.anims[0]
            p = min(1.0, anim.t / anim.dur)
            for s in anim.statics:
                self.draw_piece(surf, s)
            if anim.kind == "roll":
                self.draw_piece(surf, anim.piece, roll=(anim.direction, smoothstep(p) * math.pi / 2))
            elif anim.kind == "fall":
                self.draw_piece(surf, anim.piece, dz=-(p ** 2) * 6.0, alpha=max(0.0, 1.0 - p ** 1.4))
            elif anim.kind == "sink":
                self.draw_piece(
                    surf, anim.piece, dz=-smoothstep(p) * 2.1, alpha=1.0 - max(0.0, (p - 0.45) / 0.55)
                )
            elif anim.kind == "spawn":
                e = smoothstep(p)
                for piece in anim.pieces:
                    self.draw_piece(surf, piece, dz=(1 - e) * 3.0, alpha=smoothstep(min(1.0, p * 2)))
            return
        if self.session.status == Status.WON:
            return
        pieces = pieces_of(st)
        if self.session.status == Status.LOST and self.lost_cells is not None:
            pieces = [pc for pc in pieces if pc["cells"] != self.lost_cells]
        if self.session.status == Status.PLAYING and not self.replay and not self.picker_open:
            controlled = (st.get_occupied_cells()[st.active_block],) if st.is_split else st.get_occupied_cells()
            rd.draw_direction_hints(surf, controlled, self.key_flash)
        for pc in sorted(pieces, key=lambda q: rd.iso.order(*q["cells"][0])):
            if pc["kind"] == "cube" and pc["active"] and len(pieces) == 2:
                rd.draw_floor_ring(surf, pc["cells"][0], theme.TEXT)
            self.draw_piece(surf, pc)

    def _draw_hud(self, surf):
        lv = self.level
        name = self._level_title(self.level_idx)
        draw_text(surf, name, theme.font(46, True), theme.TEXT, (56, 40))
        chip_col = theme.group_color(lv.group)
        label = lv.group.upper()
        f = theme.font(17, True)
        tw = f.size(label)[0]
        chip = pygame.Rect(58, 104, tw + 28, 30)
        rrect(surf, chip, (*chip_col, 46), 15, chip_col, 2)
        draw_text(surf, label, f, chip_col, chip.center, "center")
        for i, line in enumerate(wrap_text(lv.description, theme.font(22), 720)[:3]):
            draw_text(surf, line, theme.font(22), theme.TEXT_DIM, (58, 150 + i * 30))

    def _draw_compass(self, surf):
        """Thẻ chỉ hướng: mỗi phím lăn khối về hướng nào trên màn hình."""
        card = pygame.Rect(28, 826, 252, 224)
        rrect(surf, card, (*theme.PANEL, 214), 20, theme.PANEL_EDGE, 2)
        draw_text(surf, "MOVE KEYS", theme.font(14, True), theme.TEXT_FAINT, (card.x + 18, card.y + 14))
        cx, cy = card.centerx, card.y + 130
        pygame.draw.circle(surf, theme.TEXT_FAINT, (cx, cy), 5)
        labels = {"U": "W  ↑", "D": "S  ↓", "L": "A  ←", "R": "D  →"}
        for key, label in labels.items():
            dx, dy = self.renderer.screen_dir(key)
            hot = self.key_flash[key]
            col = theme.mix(theme.TEXT_DIM, theme.ACCENT, min(1.0, 0.45 + hot))
            tip = (cx + dx * 46, cy + dy * 46)
            pygame.draw.line(surf, col, (cx, cy), tip, 4)
            px, py = -dy, dx
            head = [
                (tip[0] + dx * 12, tip[1] + dy * 12),
                (tip[0] + px * 8, tip[1] + py * 8),
                (tip[0] - px * 8, tip[1] - py * 8),
            ]
            pygame.draw.polygon(surf, col, head)
            cap = pygame.Rect(0, 0, 64, 32)
            cap.center = (cx + dx * 80, cy + dy * 80)
            fill = theme.mix(theme.CARD, theme.ACCENT_DARK, hot)
            rrect(surf, cap, fill, 9, col, 2)
            draw_text(surf, label, theme.font(17, True), theme.TEXT if hot < 0.5 else (28, 22, 8), cap.center, "center")

        cam_card = pygame.Rect(card.right + 14, card.bottom - 98, 372, 98)
        rrect(surf, cam_card, (*theme.PANEL, 214), 20, theme.PANEL_EDGE, 2)
        draw_text(surf, "CAMERA", theme.font(14, True), theme.TEXT_FAINT, (cam_card.x + 18, cam_card.y + 12))
        rows = [
            ("Zoom", "Q / E  or  mouse wheel"),
            ("Rotate / tilt", "right-drag   or   [ ]  PgUp PgDn"),
            ("Pan", "middle-drag        Reset:  C"),
        ]
        for i, (k, v) in enumerate(rows):
            y = cam_card.y + 34 + i * 20
            draw_text(surf, k, theme.font(15, True), theme.TEXT_DIM, (cam_card.x + 18, y))
            draw_text(surf, v, theme.font(15), theme.TEXT, (cam_card.x + 122, y))

    def _draw_toasts(self, surf):
        y = 40
        for t in self.toasts:
            life = t["ttl"] - t["age"]
            a = int(255 * max(0.0, min(1.0, life / 0.4, t["age"] / 0.15)))
            f = theme.font(24, True)
            w = f.size(t["text"])[0] + 56
            r = pygame.Rect(0, 0, w, 48)
            r.topright = (theme.BOARD_AREA.right - 36, y)
            rrect(surf, r, (*theme.PANEL, int(a * 0.92)), 24, (*t["color"], a), 2)
            draw_text(surf, t["text"], f, t["color"], r.center, "center", alpha=a)
            y += 60

    def _draw_banner(self, surf):
        status = self.session.status
        if self.anims or status == Status.PLAYING:
            return
        r = self.banner_rect
        rrect(surf, r, (*theme.PANEL, 238), 22, theme.PANEL_EDGE, 2)
        if status == Status.WON:
            draw_text(surf, "Stage clear!", theme.font(46, True), theme.GOOD, (r.centerx, r.y + 36), "center")
            n = self.session.moves
            draw_text(
                surf, f"Solved in {n} move{'s' if n != 1 else ''}", theme.font(24),
                theme.TEXT_DIM, (r.centerx, r.y + 82), "center",
            )
        else:
            draw_text(surf, "You fell!", theme.font(46, True), theme.BAD, (r.centerx, r.y + 36), "center")
            draw_text(
                surf, self.session.fail_reason, theme.font(22), theme.TEXT_DIM,
                (r.centerx, r.y + 82), "center",
            )
        for btn in self._banner_buttons():
            btn.draw(surf)

    def _stat_rows(self):
        s = self.stats
        if s is None or not s.found:
            return None
        m = s.metrics
        t = m.get("search_time_sec", 0.0)
        kb = m.get("peak_memory_kb", 0.0)
        return [
            ("Solution length", f"{m.get('solution_length', len(s.actions))} actions"),
            ("Solution cost", f"{m.get('solution_cost', '-')}"),
            ("Expanded nodes", f"{m.get('expanded_nodes', 0):,}"),
            ("Search time", f"{t * 1000:.2f} ms" if t < 1 else f"{t:.3f} s"),
            ("Peak memory", f"{kb / 1024:.2f} MB" if kb >= 1024 else f"{kb:.1f} KB"),
        ]

    def _draw_panel(self, surf, mouse):
        pr = theme.PANEL_RECT
        rrect(surf, pr, (*theme.PANEL, 232), 26, theme.PANEL_EDGE, 2)
        x0, w = self.x0, self.pw
        draw_text(surf, "BLOXORZ", theme.font(58, True), theme.ACCENT, (x0, 52))
        draw_text(surf, "Project 1  -  Fundamentals of AI", theme.font(18), theme.TEXT_DIM, (x0 + 2, 120))

        # thẻ màn chơi
        card = pygame.Rect(x0, 160, w, 172)
        rrect(surf, card, theme.CARD, 18)
        lv = self.level
        draw_text(surf, "MOVES", theme.font(15, True), theme.TEXT_FAINT, (card.right - 24, card.y + 18), "topright")
        draw_text(surf, str(self.session.moves), theme.font(60, True), theme.TEXT, (card.right - 24, card.y + 34), "topright")
        name_font = theme.font(30, True)
        draw_text(surf, lv.name, name_font, theme.TEXT, (card.x + 24, card.y + 22))
        col = theme.group_color(lv.group)
        draw_text(surf, lv.group.upper(), theme.font(16, True), col, (card.x + 24, card.y + 66))
        for i, line in enumerate(wrap_text(lv.description, theme.font(17), card.w - 48)[:3]):
            draw_text(surf, line, theme.font(17), theme.TEXT_DIM, (card.x + 24, card.y + 94 + i * 21))

        for b in (self.btn_new, self.btn_restart, self.btn_undo):
            b.draw(surf)

        draw_text(surf, "SOLVERS", theme.font(15, True), theme.TEXT_FAINT, (x0 + 2, 424))
        for b in self.solver_buttons.values():
            b.draw(surf)
        draw_text(surf, "A* HEURISTIC", theme.font(14, True), theme.TEXT_FAINT, (x0 + 2, 614))
        self.heur_seg.draw(surf)

        self.slider.draw(surf)
        self.btn_back.draw(surf)
        self.btn_pause.draw(surf)
        self.btn_fwd.draw(surf)
        if self.replay:
            done = self.replay_total - len(self.replay)
            draw_text(
                surf, f"{self.replay_label}: step {done}/{self.replay_total}",
                theme.font(16), theme.INFO, (x0 + 2, 776),
            )

        # thẻ số liệu
        box = pygame.Rect(x0, 804, w, 190)
        rrect(surf, box, theme.CARD, 18)
        if self.job is not None and not self.job.done:
            ang = pygame.time.get_ticks() / 140
            c = (box.x + 38, box.y + 36)
            for k in range(8):
                a = ang + k * math.tau / 8
                pygame.draw.circle(
                    surf, theme.mix(theme.CARD, theme.ACCENT, (k + 1) / 8),
                    (int(c[0] + 14 * math.cos(a)), int(c[1] + 14 * math.sin(a))), 3,
                )
            draw_text(surf, f"{self.job.label} is searching...", theme.font(22, True), theme.TEXT, (box.x + 70, box.y + 22))
        elif self.stats is None:
            draw_text(surf, "Solver results", theme.font(22, True), theme.TEXT, (box.x + 24, box.y + 18))
            for i, line in enumerate(wrap_text(
                "Pick BFS, DFS, UCS or A* to solve this stage and watch the solution replay.",
                theme.font(17), box.w - 48,
            )):
                draw_text(surf, line, theme.font(17), theme.TEXT_DIM, (box.x + 24, box.y + 56 + i * 24))
        elif self.stats.error:
            draw_text(surf, f"{self.stats.label} crashed", theme.font(22, True), theme.BAD, (box.x + 24, box.y + 18))
            for i, line in enumerate(wrap_text(self.stats.error, theme.font(16), box.w - 48)[:4]):
                draw_text(surf, line, theme.font(16), theme.TEXT_DIM, (box.x + 24, box.y + 56 + i * 22))
        elif not self.stats.found:
            draw_text(surf, self.stats.label, theme.font(22, True), theme.TEXT, (box.x + 24, box.y + 18))
            draw_text(surf, "No solution found", theme.font(20), theme.BAD, (box.x + 24, box.y + 56))
        else:
            draw_text(surf, self.stats.label, theme.font(22, True), theme.ACCENT, (box.x + 24, box.y + 16))
            self.btn_path.draw(surf)
            for i, (k, v) in enumerate(self._stat_rows()):
                y = box.y + 52 + i * 27
                draw_text(surf, k, theme.font(18), theme.TEXT_DIM, (box.x + 24, y))
                draw_text(surf, v, theme.mono(18, True), theme.TEXT, (box.right - 24, y), "topright")

        hint = "Arrows / WASD roll   Space swap cube   Z undo   R restart   N stages   F11 fullscreen"
        for i, line in enumerate(wrap_text(hint, theme.font(15), w)):
            draw_text(surf, line, theme.font(15), theme.TEXT_FAINT, (x0 + 2, 1004 + i * 19))

    # ------------------------------------------------------------------ chọn màn
    PICK_COLS, PICK_W, PICK_H, PICK_GAP = 5, 320, 212, 22
    TABS = (("classic", "CLASSIC"), ("custom", "OUR STAGES"))

    def _tab_ids(self, tab: Optional[str] = None) -> List[int]:
        tab = tab or self.picker_tab
        return [i for i, lv in enumerate(self.levels) if lv.section == tab]

    def _section_position(self, idx: int) -> int:
        """Số thứ tự (từ 1) của màn trong nhóm của nó (Classic hoặc Our stages)."""
        ids = self._tab_ids(self.levels[idx].section)
        return ids.index(idx) + 1

    def _level_title(self, idx: int) -> str:
        lv = self.levels[idx]
        return lv.name if lv.section == "classic" else f"{self._section_position(idx)}.  {lv.name}"

    @staticmethod
    def _level_tags(lv: Level) -> str:
        pb = lv.problem
        tags = []
        if any(t == TileType.FRAGILE for t in pb.grid.values()):
            tags.append("FRAGILE")
        if pb.bridge_indices:
            tags.append("BRIDGES")
        if any(sw.split_targets for sw in pb.switches.values()):
            tags.append("SPLIT")
        if any(sw.split_targets is None for sw in pb.switches.values()):
            tags.append("SWITCHES")
        return "  \u00b7  ".join(tags) if tags else "PLAIN"

    def _picker_panel(self) -> pygame.Rect:
        return pygame.Rect(80, 60, theme.WIDTH - 160, theme.HEIGHT - 120)

    def _picker_view(self) -> pygame.Rect:
        panel = self._picker_panel()
        return pygame.Rect(panel.x + 20, panel.y + 176, panel.w - 40, panel.h - 176 - 24)

    def _picker_tab_rects(self) -> Dict[str, pygame.Rect]:
        panel = self._picker_panel()
        w, h, gap = 300, 46, 16
        x = panel.centerx - (len(self.TABS) * w + (len(self.TABS) - 1) * gap) // 2
        return {
            key: pygame.Rect(x + i * (w + gap), panel.y + 80, w, h)
            for i, (key, _) in enumerate(self.TABS)
        }

    def _picker_max_scroll(self) -> int:
        n = len(self._tab_ids())
        rows = (n + self.PICK_COLS - 1) // self.PICK_COLS
        content = rows * (self.PICK_H + self.PICK_GAP) - self.PICK_GAP
        return max(0, content - self._picker_view().h)

    def _picker_cards(self) -> Dict[int, pygame.Rect]:
        """Hình chữ nhật (toạ độ màn hình, đã trừ cuộn) của từng thẻ, khoá là chỉ số màn toàn cục."""
        view = self._picker_view()
        total = self.PICK_COLS * self.PICK_W + (self.PICK_COLS - 1) * self.PICK_GAP
        x = view.centerx - total // 2
        return {
            gid: pygame.Rect(
                x + (pos % self.PICK_COLS) * (self.PICK_W + self.PICK_GAP),
                view.y + (pos // self.PICK_COLS) * (self.PICK_H + self.PICK_GAP) - int(self.picker_scroll),
                self.PICK_W, self.PICK_H,
            )
            for pos, gid in enumerate(self._tab_ids())
        }

    def _picker_scroll_to(self, gid: int) -> None:
        view = self._picker_view()
        ids = self._tab_ids()
        pos = ids.index(gid) if gid in ids else 0
        top = (pos // self.PICK_COLS) * (self.PICK_H + self.PICK_GAP)
        if top < self.picker_scroll:
            self.picker_scroll = float(top)
        elif top + self.PICK_H > self.picker_scroll + view.h:
            self.picker_scroll = float(top + self.PICK_H - view.h)
        self.picker_scroll = max(0.0, min(float(self._picker_max_scroll()), self.picker_scroll))

    def _set_picker_tab(self, tab: str) -> None:
        if tab == self.picker_tab:
            return
        self.picker_tab = tab
        self.picker_scroll = 0.0
        ids = self._tab_ids()
        if self.picker_sel not in ids and ids:
            self.picker_sel = ids[0]

    def _picker_key(self, k: int) -> None:
        ids = self._tab_ids()
        n = len(ids)
        if k == pygame.K_TAB:
            keys = [key for key, _ in self.TABS]
            self._set_picker_tab(keys[(keys.index(self.picker_tab) + 1) % len(keys)])
            return
        pos = ids.index(self.picker_sel) if self.picker_sel in ids else 0
        step = {
            pygame.K_LEFT: -1, pygame.K_RIGHT: 1,
            pygame.K_UP: -self.PICK_COLS, pygame.K_DOWN: self.PICK_COLS,
        }.get(k)
        if step is not None:
            self.picker_sel = ids[max(0, min(n - 1, pos + step))]
            self._picker_scroll_to(self.picker_sel)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.load_level(self.picker_sel)
        elif pygame.K_1 <= k <= pygame.K_9 and k - pygame.K_1 < n:
            self.load_level(ids[k - pygame.K_1])
    def _thumb(self, i: int, size) -> pygame.Surface:
        if i in self.thumbs:
            return self.thumbs[i]
        level = self.levels[i]
        pb = level.problem
        w, h = size
        surf = pygame.Surface(size, pygame.SRCALPHA)
        cell = max(6, min(36, (w - 24) // level.cols, (h - 24) // level.rows))
        ox = (w - cell * level.cols) // 2
        oy = (h - cell * level.rows) // 2
        start = pb.initial_state.get_occupied_cells()[0]
        for (r, c), tile in pb.grid.items():
            rect = pygame.Rect(ox + c * cell, oy + r * cell, cell - 2, cell - 2)
            if tile == TileType.FRAGILE:
                col = theme.FRAGILE_TOP
            elif tile == TileType.BRIDGE:
                g = level.bridge_group_of((r, c))
                col = theme.BRIDGE_COLORS[g % len(theme.BRIDGE_COLORS)] if g >= 0 else theme.TEXT_DIM
            elif (r, c) == start:
                col = theme.START_TOP
            else:
                col = theme.FLOOR_TOP
            pygame.draw.rect(surf, col, rect, border_radius=max(2, cell // 6))
            if tile == TileType.GOAL:
                pygame.draw.rect(surf, (8, 9, 14), rect.inflate(-cell // 3, -cell // 3), border_radius=3)
            sw = pb.switches.get((r, c))
            if sw is not None:
                if sw.linked_bridges:
                    g = level.bridge_group_of(sw.linked_bridges[0])
                    scol = theme.BRIDGE_COLORS[g % len(theme.BRIDGE_COLORS)]
                else:
                    scol = theme.SPLIT_COLOR
                pygame.draw.circle(surf, scol, rect.center, max(2, cell // 4))
        self.thumbs[i] = surf
        return surf

    def _draw_picker(self, surf, mouse):
        dim = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        dim.fill((6, 8, 16, 214))
        surf.blit(dim, (0, 0))
        panel = self._picker_panel()
        rrect(surf, panel, theme.PANEL, 28, theme.PANEL_EDGE, 2)
        draw_text(surf, "Select a stage", theme.font(48, True), theme.TEXT, (panel.centerx, panel.y + 42), "center")
        for key, label in self.TABS:
            rect = self._picker_tab_rects()[key]
            ids = self._tab_ids(key)
            cleared = sum(1 for i in ids if self.progress.is_cleared(self.levels[i].name))
            active = key == self.picker_tab
            hot = rect.collidepoint(mouse)
            rrect(
                surf, rect, theme.mix(theme.CARD, theme.ACCENT_DARK, 0.9 if active else (0.25 if hot else 0.0)), 14,
                theme.ACCENT if active else theme.PANEL_EDGE, 2,
            )
            draw_text(
                surf, f"{label}   {cleared}/{len(ids)}", theme.font(21, True),
                (28, 22, 8) if active else theme.TEXT_DIM, rect.center, "center",
            )
        draw_text(
            surf, "click or arrows + Enter   -   Tab switches section   -   wheel to scroll   -   Esc to close",
            theme.font(18), theme.TEXT_DIM, (panel.centerx, panel.y + 148), "center",
        )
        view = self._picker_view()
        surf.set_clip(view)
        view_mouse = view.collidepoint(mouse)
        for i, rect in self._picker_cards().items():
            if rect.bottom < view.y or rect.y > view.bottom:
                continue
            lv = self.levels[i]
            hot = view_mouse and rect.collidepoint(mouse)
            col = theme.group_color(lv.group)
            selected = i == self.picker_sel or i == self.level_idx
            rrect(surf, rect, theme.CARD_HI if hot else theme.CARD, 18, col if (hot or selected) else theme.PANEL_EDGE, 2)
            thumb = self._thumb(i, (rect.w - 24, 118))
            surf.blit(thumb, (rect.x + 12, rect.y + 10))
            draw_text(surf, self._level_title(i), theme.font(23, True), theme.TEXT, (rect.x + 18, rect.y + 138))
            chip = self._level_tags(lv) if lv.section == "classic" else lv.group.upper()
            draw_text(surf, chip, theme.font(13, True), col, (rect.x + 20, rect.y + 177))
            best = self.progress.best(lv.name)
            if best is not None:
                draw_text(surf, f"CLEARED  -  best {best}", theme.font(13, True), theme.GOOD, (rect.right - 18, rect.y + 192), "topright")
        surf.set_clip(None)
        max_scroll = self._picker_max_scroll()
        if max_scroll:
            track = pygame.Rect(view.right - 8, view.y, 6, view.h)
            rrect(surf, track, (40, 48, 70), 3)
            bar_h = max(40, int(view.h * view.h / (view.h + max_scroll)))
            bar_y = view.y + int((view.h - bar_h) * self.picker_scroll / max_scroll)
            rrect(surf, pygame.Rect(track.x, bar_y, 6, bar_h), theme.TEXT_DIM, 3)
    def _draw_tooltip(self, surf, mouse):
        for btn in (self.btn_back, self.btn_fwd):
            if btn.enabled and btn.tooltip and btn.rect.collidepoint(mouse):
                f = theme.font(16)
                r = pygame.Rect(0, 0, f.size(btn.tooltip)[0] + 24, 34)
                r.midbottom = (btn.rect.centerx, btn.rect.y - 8)
                rrect(surf, r, (14, 17, 28, 240), 9, theme.PANEL_EDGE, 2)
                draw_text(surf, btn.tooltip, f, theme.TEXT, r.center, "center")
                return
        for name, btn in self.solver_buttons.items():
            if not self.available.get(name) and btn.rect.collidepoint(mouse):
                module = f"App/Solvers/{name.replace('*', '_star').replace('A_star', 'A_star')}_solver.py"
                text = f"{name} solver not found - add {module} (class {name}Solver)"
                if name == "A*":
                    text = "A* solver not found - App/Solvers/A_star_solver.py (class AstarSolver)"
                f = theme.font(17)
                r = pygame.Rect(0, 0, f.size(text)[0] + 28, 40)
                r.topright = (mouse[0], mouse[1] + 24)
                r.right = min(r.right, theme.WIDTH - 12)
                rrect(surf, r, (14, 17, 28, 240), 10, theme.PANEL_EDGE, 2)
                draw_text(surf, text, f, theme.TEXT, r.center, "center")
                return

    def draw(self, mouse):
        surf = self.screen
        surf.blit(self.bg, (0, 0))
        self._draw_hud(surf)
        self.renderer.draw_board(surf)
        if self.show_path and self.path_steps:
            done = len(self.replay_done) if (self.replay or self.replay_done) else None
            self.renderer.draw_path(surf, self.path_steps, done)
        self._draw_pieces(surf)
        self.renderer.draw_particles(surf)
        self._draw_compass(surf)
        self._draw_toasts(surf)
        self._draw_panel(surf, mouse)
        self._draw_banner(surf)
        if self.picker_open:
            self._draw_picker(surf, mouse)
        self._draw_tooltip(surf, mouse)

    # ------------------------------------------------------------------ vòng lặp
    def run(self):
        while self.running:
            focused = pygame.display.get_active()
            dt = min(self.clock.tick(60 if focused else 10) / 1000.0, 0.05)
            mouse = pygame.mouse.get_pos()
            for event in pygame.event.get():
                self.handle(event, mouse)
            self.update(dt, mouse)
            self.draw(mouse)
            pygame.display.flip()
        pygame.quit()


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    # python play.py [classic|ours] [số màn]: số màn tính trong nhóm đã chọn (mặc định: nhóm Classic)
    section, number = "classic", 1
    for a in argv:
        if a.isdigit():
            number = int(a)
        elif a.lower() in ("classic", "custom", "ours"):
            section = "custom" if a.lower() in ("custom", "ours") else "classic"
    app = App(0)
    ids = [i for i, lv in enumerate(app.levels) if lv.section == section] or [0]
    app.load_level(ids[max(0, min(number - 1, len(ids) - 1))])
    app.run()


if __name__ == "__main__":
    main()
