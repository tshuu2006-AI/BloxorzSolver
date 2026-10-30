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
import time
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional

import pygame

from App.Components.features import TileType
from App.Components.level_loader import Level, load_levels
from App.GUI import theme
from App.GUI.audio import Audio
from App.GUI.compare_view import CompareView
from App.GUI.menu import MainMenu, PauseMenu, LevelSelectView, SettingsView, WinOverlay
from App.GUI.models import INITIAL_FRAME, frame_for_orientation, roll_frame
from App.GUI.pieces import pieces_of
from App.GUI.race import LANE_COLORS, Race
from App.GUI.render import BoardRenderer, Camera, smoothstep
from App.GUI.solver_panel import SolverDrawer
from App.GUI.widgets import (
    Button,
    Slider,
    draw_text,
    rrect,
    vgradient,
    wrap_text,
)
from App.Game.compare import CompareJob
from App.Game.experiment import compare_configs, write_csv
from App.Game.links import link_segments
from App.Components.problem import Problem
from App.Game.path import compute_step_guide, path_steps, replay_states
from App.Game.progress import Progress
from App.Game.session import DELTAS, GameSession, Outcome, Status, fired_switches
from App.Game.settings import Settings
from App.Game.solver_bridge import (
    SolveOutcome,
    SolverJob,
    available_heuristics,
    available_solvers,
    make_solver,
)
from App.Game.tips import TIPS, tip_for

LEVELS_DIR = Path(__file__).resolve().parents[2] / "levels"
CLASSIC_DIR = LEVELS_DIR / "classic"
PROGRESS_PATH = Path(__file__).resolve().parents[2] / ".bloxorz_progress.json"
SETTINGS_PATH = Path(__file__).resolve().parents[2] / ".bloxorz_settings.json"
SCREENSHOT_DIR = Path(__file__).resolve().parents[2] / "screenshots"

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

    def __init__(
        self,
        piece,
        fragile_tiles=(),
        tilt_roll=None,
        dpos=(0.0, 0.0),
        is_half_fall: bool = False,
        c_sup=None,
        c_void=None,
        **kw,
    ):
        dur = kw.pop("dur", 0.72 if is_half_fall else 0.60)
        super().__init__(dur, **kw)
        self.piece = piece
        self.fragile_tiles = tuple(fragile_tiles)
        self.tilt_roll = tilt_roll
        self.dpos = dpos
        self.is_half_fall = is_half_fall
        self.c_sup = c_sup
        self.c_void = c_void

    def get_transform(self, p: float):
        """Tính toán (roll_arg, dr_off, dc_off, dz) tại thời điểm p (0..1)."""
        if self.is_half_fall and self.tilt_roll is not None:
            tdir, max_theta, piv = self.tilt_roll
            p_tip = 0.35
            theta_mid = 0.95  # ~54 độ: bập bênh nhấc bổng nửa trên sàn
            theta_max = max_theta  # 1.8 (~103 độ)
            if p <= p_tip:
                u = p / p_tip
                theta = (u ** 1.8) * theta_mid
                dz = 0.0
                dr_off = 0.0
                dc_off = 0.0
            else:
                w = (p - p_tip) / (1.0 - p_tip)
                theta = theta_mid + (w * (2 - w)) * (theta_max - theta_mid)
                shift = w ** 1.3
                dr_off = shift * self.dpos[0]
                dc_off = shift * self.dpos[1]
                dz = -(w ** 2) * 6.5
            roll_arg = (tdir, theta, piv)
            return roll_arg, dr_off, dc_off, dz
        else:
            dz = -(p ** 2) * 6.0
            roll_arg = None
            if self.tilt_roll is not None:
                tdir, max_theta, piv = self.tilt_roll
                roll_arg = (tdir, smoothstep(p) * max_theta, piv)
            dr_off = (p ** 1.5) * self.dpos[0]
            dc_off = (p ** 1.5) * self.dpos[1]
            return roll_arg, dr_off, dc_off, dz


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
        self.settings = Settings(SETTINGS_PATH)
        theme.AXIS_TILT_DEG = self.settings.tilt_deg  # góc nhìn mặc định (trước khi tạo Camera)
        self.audio = Audio(self.settings.sound_on, self.settings.volume)
        self.panel_tab = "play"  # "play" | "settings"
        self._rebuild_background()
        self.reset_armed_until = 0.0
        self.picker_scroll = 0.0
        self.picker_sel = 0
        self.used_solver = False
        self.thumbs: Dict[int, pygame.Surface] = {}
        self.picker_open = False
        self.running = True

        self.toasts: List[dict] = []
        self.key_flash = {"U": 0.0, "D": 0.0, "L": 0.0, "R": 0.0}
        self.compare_job: Optional[CompareJob] = None
        self.compare_open = False
        self.compare_store: Dict[int, dict] = {}  # chỉ số màn -> kết quả lần so sánh gần nhất
        self.compare_skipped: List[str] = []
        self.compare_view = CompareView(
            self._replay_row, self.start_compare, self._save_compare_csv, self.close_compare, self.start_race
        )
        self.race: Optional[Race] = None
        self.race_paused = False
        self.show_path = self.settings.show_path
        self.show_step_guide = self.settings.get("show_step_guide", False)
        self.selected_solver: Optional[str] = None
        self.guide_solution: Optional[List[str]] = None
        self.guide_states: Optional[List[Any]] = None
        self.next_step_info: Optional[dict] = None
        self.tip: Optional[str] = None  # khoá gợi ý đang hiện
        self.tip_start_moves = 0
        self._tip_pending = True
        self.path_steps: List[dict] = []
        self.replay_done: List[str] = []
        self.step_req = 0
        self.block_frame = INITIAL_FRAME
        self.cube_frames = [INITIAL_FRAME, INITIAL_FRAME]
        self.frame_history = []
        self.cam = Camera()
        self.cam_dirty = False
        self.cam_drag = None  # "rotate" | "pan" khi đang kéo chuột
        self.heuristic_options = available_heuristics()
        default_heuristic = self.heuristic_options[0] if self.heuristic_options else "manhattan"
        self.heuristic = (
            self.settings.astar_heuristic
            if self.settings.astar_heuristic in self.heuristic_options
            else default_heuristic
        )
        self.heuristic_popup_open = False
        self.speed = self.settings.replay_speed
        self.job: Optional[SolverJob] = None
        self.stats: Optional[SolveOutcome] = None
        self.available = available_solvers()
        self._avail_timer = 0.0

        self._build_widgets()
        self.load_level(max(0, min(start_level, len(self.levels) - 1)))
        self.screen_state = "menu"
        self.screen_stack = ["menu"]
        self.menu = MainMenu(self)
        self.pause_menu = PauseMenu(self)
        self.level_select_view = LevelSelectView(self)
        self.settings_view = SettingsView(self)
        self.win_overlay = WinOverlay(self)
        self.show_ai_panel = False
        self.hud_rects = {}
        self.action_history = []
        self.solver_drawer = SolverDrawer(self)

    def push_screen(self, state: str):
        if not self.screen_stack or self.screen_stack[-1] != state:
            self.screen_stack.append(state)
        self.screen_state = state

    def pop_screen(self):
        if len(self.screen_stack) > 1:
            self.screen_stack.pop()
            self.screen_state = self.screen_stack[-1]
        else:
            self.screen_state = "menu"

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
        pr = theme.PANEL_RECT
        x0 = pr.x + 24
        w = pr.w - 48
        self.x0, self.pw = x0, w

        # Settings controls used by SettingsView
        S = self.settings
        self.tilt_slider = Slider((x0 + 4, 468, w - 8, 24), 0.0, 45.0, S.tilt_deg, "Default tilt", fmt="{:.0f} deg")
        self.volume_slider = Slider((x0 + 4, 814, w - 8, 24), 0.0, 1.0, S.volume, "Volume", fmt="{:.0%}")
        self.speed_slider = Slider((x0 + 4, 310, w - 8, 26), 0.25, 4.0, self.speed, "Replay speed", fmt="{:.2f}x")
        self.slider = self.speed_slider
        self.btn_cam_reset = Button((x0, 502, w, 44), "Reset camera  (C)", self._reset_camera, font_size=19)
        self.btn_tips_again = Button((x0, 630, w, 40), "Show all tips again", self._show_tips_again, font_size=18)
        self.btn_shot = Button((x0, 884, w, 50), "Save screenshot  (F12)", self.save_screenshot, font_size=17)
        self.btn_reset_progress = Button((x0, 884, w, 50), "Reset progress", self._reset_progress_click, font_size=17)

        # Nút trong banner thắng / thua
        cx = theme.BOARD_AREA.centerx
        self.banner_rect = pygame.Rect(cx - 330, 872, 660, 170)
        r = self.banner_rect
        self.btn_next = Button((r.x + 36, r.bottom - 70, 280, 50), "Next stage  (Enter)", self.next_level, "primary")
        self.btn_stages = Button((r.right - 316, r.bottom - 70, 280, 50), "Stage select  (N)", self.open_picker)
        self.btn_banner_undo = Button((r.x + 36, r.bottom - 70, 280, 50), "Undo  (Z)", self.undo, "primary")
        self.btn_banner_restart = Button((r.right - 316, r.bottom - 70, 280, 50), "Restart  (R / Enter)", self.restart)
        cx_race = 40 + 1380 // 2
        bw4 = 175
        gap4 = 14
        tot_w4 = 4 * bw4 + 3 * gap4
        bx_race = cx_race - tot_w4 // 2
        self.race_buttons = [
            Button((bx_race, 956, bw4, 46), "Pause  (Space)", self.toggle_race_pause, font_size=16),
            Button((bx_race + bw4 + gap4, 956, bw4, 46), "Restart  (R)", self.restart_race, font_size=16),
            Button((bx_race + (bw4 + gap4) * 2, 956, bw4, 46), "Path: ON  (V)", self.toggle_path, font_size=16),
            Button((bx_race + (bw4 + gap4) * 3, 956, bw4, 46), "Exit race  (Esc)", self.exit_race, "primary", font_size=16),
        ]
        self.tip_rect = pygame.Rect(cx - 330, 864, 660, 188)
        self.btn_tip_ok = Button(
            (self.tip_rect.right - 194, self.tip_rect.y + 18, 170, 40), "Got it  (Enter)",
            self.dismiss_tip, "primary", font_size=19,
        )
        self.paused = False
        self._layout_bottom_boxes()

    def _main_buttons(self) -> List[Button]:
        return []

    def _bottom_span(self):
        """Khoảng ngang còn trống ở đáy bàn cờ, bên phải các thẻ Move keys / Camera (nếu đang hiện)."""
        left = 28
        if self.settings.show_compass:
            left += 252 + 14
        if self.settings.show_camera_help:
            left += 372 + 14
        return left + 10, theme.BOARD_AREA.right - 20

    def _layout_bottom_boxes(self):
        """Đặt hộp banner thắng/thua và thẻ gợi ý nằm gọn trong khoảng trống, không đè lên thẻ camera."""
        lo, hi = self._bottom_span()
        cx = (lo + hi) // 2
        width = max(300, min(640, hi - lo))
        r = self.banner_rect
        r.update(cx - width // 2, 872, width, 170)
        half = (width - 24 * 2 - 16) // 2
        for b in (self.btn_next, self.btn_banner_undo):
            b.rect.update(r.x + 24, r.bottom - 70, half, 50)
        for b in (self.btn_stages, self.btn_banner_restart):
            b.rect.update(r.right - 24 - half, r.bottom - 70, half, 50)
        t = self.tip_rect
        t.update(cx - width // 2, 864, width, 188)
        self.btn_tip_ok.rect.update(t.right - 24 - 170, t.y + 18, 170, 40)

    def _reset_camera(self):
        self.cam.reset()
        self.cam_dirty = True
        self.toast("Camera reset", theme.INFO, 1.4)

    def _set_tilt(self, deg: float):
        theme.AXIS_TILT_DEG = deg
        self.settings.set("tilt_deg", deg)
        self.thumbs.clear()
        self.cam.reset()
        self.cam_dirty = True

    @property
    def current_theme(self) -> str:
        th = self.settings.theme
        return th if th in ("arctic", "desert") else "arctic"

    def _rebuild_background(self):
        if self.current_theme == "desert":
            top, bot = theme.DESERT_BG_TOP, theme.DESERT_BG_BOTTOM
        else:
            top, bot = theme.BG_TOP, theme.BG_BOTTOM
        self.bg = vgradient((theme.WIDTH, theme.HEIGHT), top, bot)

    def set_theme(self, theme_name: str):
        self.settings.set("theme", theme_name)
        if hasattr(self, "renderer"):
            self.renderer.set_theme(theme_name)
        if hasattr(self, "race") and self.race is not None:
            self.race.set_theme(theme_name)
        self.thumbs.clear()
        self._rebuild_background()
        theme_title = "Arctic Expedition" if theme_name == "arctic" else "Desert Oasis"
        self.toast(f"Theme switched to {theme_title}", theme.GOOD, 2.0)
        self.audio.play("switch")

    def toggle_theme(self) -> str:
        new_theme = "desert" if self.current_theme == "arctic" else "arctic"
        self.set_theme(new_theme)
        return new_theme

    def _set_sound(self, on: bool, toast: bool = True):
        self.audio.set_enabled(on)
        self.settings.set("sound_on", on)
        if toast:
            self.toast("Sound on" if on else "Sound muted (M)", theme.INFO, 1.4)
        if on:
            self.audio.play("switch")

    def _show_tips_again(self):
        self.settings.reset_tips()
        self.toast("Tips will show again on the next stage", theme.INFO, 2.6)

    def _reset_progress_click(self):
        now = pygame.time.get_ticks() / 1000.0
        if now < self.reset_armed_until:
            self.progress.reset()
            self.reset_armed_until = 0.0
            self.toast("Progress cleared", theme.GOOD, 2.2)
        else:
            self.reset_armed_until = now + 3.0
            self.toast("Click Reset progress again to confirm", theme.BAD, 3.0)

    def save_screenshot(self):
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOT_DIR / time.strftime("bloxorz_%Y%m%d_%H%M%S.png")
        try:
            pygame.image.save(self.screen, str(path))
            self.toast(f"Saved screenshots/{path.name}", theme.GOOD, 3.0)
        except (pygame.error, OSError) as exc:
            self.toast(f"Could not save screenshot: {exc}", theme.BAD, 4.0)

    def set_heuristic(self, name: str):
        self.heuristic = name
        self.settings.set("astar_heuristic", name)

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
        self.renderer = BoardRenderer(self.level, cam=self.cam, theme_name=self.current_theme)
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
        self.cancel_solver(quiet=True)  # đổi màn: dừng tiến trình giải của màn cũ
        self.stats = None
        self.path_steps = []
        self.replay_done = []
        self.selected_solver = None
        self.guide_solution = None
        self.guide_states = None
        self.next_step_info = None
        self.link_segs = link_segments(self.level)
        self.tip = None
        self._tip_pending = True
        self.toasts.clear()
        self.picker_open = False
        self.action_history = []
        self.block_frame = frame_for_orientation(self.level.problem.initial_state.orientation)
        self.cube_frames = [INITIAL_FRAME, INITIAL_FRAME]
        self.frame_history.clear()
        self.toast(self.level.name, theme.group_color(self.level.group), 2.0)

    def restart(self):
        self._reset_play()
        self.session.reset()
        self.selected_solver = None
        self.show_step_guide = False
        self.guide_solution = None
        self.guide_states = None
        self.next_step_info = None
        self.path_steps = []
        self.block_frame = frame_for_orientation(self.level.problem.initial_state.orientation)
        self.cube_frames = [INITIAL_FRAME, INITIAL_FRAME]
        self.frame_history.clear()
        self.renderer.set_bridges(self.session.state.bridges_state)

    def _reset_play(self):
        self.used_solver = False
        self.replay_done = []
        self.anims.clear()
        self.queued = None
        self.replay.clear()
        self.paused = False
        self.lost_cells = None
        self.renderer.clear_fragile_falls()

    def undo(self):
        if self.anims:
            self.anims.clear()
        self.replay.clear()
        self.replay_done = []
        if self.session.status == Status.LOST:
            self.session.status = Status.PLAYING
            self.session.fail_reason = ""
            if self.action_history:
                entry = self.action_history.pop()
                self.session.state = entry["prev_state"]
                self.session.moves = entry["prev_moves"]
                self.block_frame = entry["block_frame"]
                self.cube_frames = list(entry["cube_frames"])
                self.renderer.set_bridges(entry["prev_state"].bridges_state)
            else:
                self.block_frame = frame_for_orientation(self.session.state.orientation)
                self.cube_frames = [INITIAL_FRAME, INITIAL_FRAME]
            if self.frame_history:
                self.frame_history.pop()
            self.lost_cells = None
            self.renderer.clear_fragile_falls()
            self.toast("Recovered from fall", theme.INFO)
            pcs = pieces_of(self.session.state)
            for idx, pc in enumerate(pcs):
                if pc["kind"] == "cube" and len(pcs) == 2:
                    pc["frame"] = self.cube_frames[idx]
                else:
                    pc["frame"] = self.block_frame
            self.anims.append(SpawnAnim(
                pcs,
                on_start=lambda: self.audio.play("swap"),
                on_finish=lambda: (self.renderer.squash_at(self.session.state.get_occupied_cells()), self.audio.play("roll")),
            ))
            return
        if not self.action_history:
            if self.session.undo():
                self.lost_cells = None
                self.renderer.set_bridges(self.session.state.bridges_state)
                self.renderer.clear_fragile_falls()
                self._recalculate_guide_from_current()
            return

        entry = self.action_history.pop()
        if self.frame_history:
            self.frame_history.pop()
        act = entry["action"]
        prev_st = entry["prev_state"]

        if act == "SWITCH" or prev_st.is_split != self.session.state.is_split:
            self.session.state = prev_st
            self.session.moves = entry["prev_moves"]
            self.block_frame = entry["block_frame"]
            self.cube_frames = entry["cube_frames"]
            self.renderer.set_bridges(prev_st.bridges_state)
            self.renderer.clear_fragile_falls()
            self.audio.play("swap")
            self.is_action_from_replay = False
            self._on_player_moved()
            return

        rev_act = {"U": "D", "D": "U", "L": "R", "R": "L"}.get(act, "D")
        direction = DELTAS[rev_act]
        pcs = pieces_of(self.session.state)
        if self.session.state.is_split:
            i = self.session.state.active_block
            moving = pcs[i]
            statics = [pcs[1 - i]]
            moving["frame"] = self.cube_frames[i]
            statics[0]["frame"] = self.cube_frames[1 - i]
        else:
            moving = pcs[0]
            statics = []
            moving["frame"] = self.block_frame

        def after_undo_roll():
            self.session.state = prev_st
            self.session.moves = entry["prev_moves"]
            self.block_frame = entry["block_frame"]
            self.cube_frames = entry["cube_frames"]
            self.renderer.set_bridges(prev_st.bridges_state)
            self.renderer.clear_fragile_falls()
            self.lost_cells = None
            self.audio.play("roll")
            self.is_action_from_replay = False
            self._on_player_moved()

        self.anims.append(RollAnim(moving, direction, statics=statics, on_finish=after_undo_roll))

    def next_level(self):
        self.load_level((self.level_idx + 1) % len(self.levels))

    def open_picker(self):
        self.screen_state = "level_select"
        self.level_select_view.active_tab = self.level.section
        self.level_select_view.page = self.level_idx // self.level_select_view.levels_per_page

    def toast(self, text: str, color=None, ttl: float = 2.6):
        self.toasts.append({"text": text, "color": color or theme.TEXT, "ttl": ttl, "age": 0.0})
        self.toasts = self.toasts[-3:]

    # ------------------------------------------------------------------ hành động
    def do_action(self, action: str, from_replay: bool = False):
        if action in self.key_flash:
            self.key_flash[action] = 1.0  # làm sáng hướng này trên la bàn / mũi tên sàn
        elif action == "SWITCH":
            self.renderer.swap_pop = 1.0
        if self.anims:
            if not from_replay:
                self.queued = action
            return None
        self.is_action_from_replay = from_replay
        if not from_replay:
            self.paused = True  # người chơi can thiệp: tạm dừng auto replay
            if not self.selected_solver:
                self.replay.clear()
                self.replay_done.clear()
        saved_block_frame = self.block_frame
        saved_cube_frames = list(self.cube_frames)
        prev_st = self.session.state
        prev_moves = self.session.moves
        ev = self.session.apply(action)
        if ev.outcome not in (Outcome.IGNORED, Outcome.BLOCKED):
            self.frame_history.append((saved_block_frame, saved_cube_frames))
            self.action_history.append({
                "action": action,
                "prev_state": prev_st,
                "prev_moves": prev_moves,
                "block_frame": saved_block_frame,
                "cube_frames": saved_cube_frames,
            })
        self._present(ev)
        if ev.outcome == Outcome.SWITCHED:
            self._on_player_moved()
        return ev

    def _present(self, ev):
        o = ev.outcome
        if o == Outcome.IGNORED:
            return
        if o == Outcome.BLOCKED:
            self.toast(ev.reason, theme.BAD)
            self.audio.play("blocked")
            return
        if o == Outcome.SWITCHED:
            self.audio.play("swap")
            return

        prev = ev.prev
        pcs = pieces_of(prev)
        if prev.is_split:
            i = prev.active_block
            moving, statics = pcs[i], [pcs[1 - i]]
            moving["frame"] = self.cube_frames[i]
            statics[0]["frame"] = self.cube_frames[1 - i]
        else:
            moving, statics = pcs[0], []
            moving["frame"] = self.block_frame
        direction = DELTAS[ev.action]

        def after_roll():
            if ev.new is not None:
                self.renderer.set_bridges(ev.new.bridges_state)
                self._landing_fx(ev)
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

            if ev.merged:
                self.block_frame = frame_for_orientation(ev.new.orientation)
            elif ev.teleported:
                self.cube_frames = [INITIAL_FRAME, INITIAL_FRAME]
            elif prev.is_split and ev.new is not None and ev.new.is_split:
                unmoved_frame = self.cube_frames[1 - prev.active_block]
                moved_frame = roll_frame(self.cube_frames[prev.active_block], ev.action)
                unmoved_pos = prev.get_occupied_cells()[1 - prev.active_block]
                if ev.new._b1 == unmoved_pos:
                    self.cube_frames = [unmoved_frame, moved_frame]
                else:
                    self.cube_frames = [moved_frame, unmoved_frame]
            elif prev.is_split:
                self.cube_frames[prev.active_block] = roll_frame(self.cube_frames[prev.active_block], ev.action)
            else:
                self.block_frame = roll_frame(self.block_frame, ev.action)

        anims: List[Anim] = [RollAnim(moving, direction, statics=statics, on_finish=after_roll)]
        if o == Outcome.FELL:
            cells = ev.fall_cells
            fell_frame = (
                roll_frame(self.cube_frames[prev.active_block], ev.action)
                if prev.is_split
                else roll_frame(self.block_frame, ev.action)
            )
            if prev.is_split:
                piece = {"cells": cells, "kind": "cube", "height": 1.0, "active": True, "frame": fell_frame}
            else:
                piece = {
                    "cells": cells, "kind": "block",
                    "height": 2.0 if len(cells) == 1 else 1.0, "active": True,
                    "frame": fell_frame,
                }
            self.lost_cells = moving["cells"]
            fragile_tiles = ev.fragile_fall_cells

            tilt_roll = None
            dpos = (0.0, 0.0)
            is_half_fall = False
            c_sup_cell = None
            c_void_cell = None
            if not fragile_tiles:
                pb = self.level.problem
                st_prev = prev

                def is_sup(c):
                    t = pb.grid.get(c, TileType.VOID)
                    if t == TileType.VOID:
                        return False
                    if t == TileType.BRIDGE:
                        b_idx = pb.bridge_indices.get(c)
                        if b_idx is not None and not st_prev.bridges_state[b_idx]:
                            return False
                    return True
                if len(cells) == 2:
                    c0, c1 = cells[0], cells[1]
                    s0, s1 = is_sup(c0), is_sup(c1)
                    if s0 != s1:
                        # 1 ô trên sàn, 1 ô rơi ra ngoài khoảng không -> bập bênh chuẩn xác từ mép giữa
                        c_sup_cell = c0 if s0 else c1
                        c_void_cell = c1 if s0 else c0
                        dr = c_void_cell[0] - c_sup_cell[0]
                        dc = c_void_cell[1] - c_sup_cell[1]
                        pivot = max(c_sup_cell[0], c_void_cell[0]) if dr != 0 else max(c_sup_cell[1], c_void_cell[1])
                        tilt_roll = ((dr, dc), 1.8, pivot)
                        dpos = (dr * 0.85, dc * 0.85)
                        is_half_fall = True
                    else:
                        # Cả 2 ô đều lăn ra ngoài sàn: trôi chéo theo quán tính hướng lăn
                        dr, dc = DELTAS.get(ev.action, (0, 0))
                        tilt_roll = ((dr, dc), 0.55, None)
                        dpos = (dr * 0.65, dc * 0.65)
                else:
                    # Khối đứng hoặc khối 1x1 bước ra khoảng không: rơi chéo theo quán tính
                    dr, dc = DELTAS.get(ev.action, (0, 0))
                    tilt_roll = ((dr, dc), 0.45, None)
                    dpos = (dr * 0.5, dc * 0.5)

            def start_fall(fragile_tiles=fragile_tiles):
                for cell in fragile_tiles:
                    self.renderer.start_fragile_fall(cell)
                    if self.renderer.arctic_theme:
                        fragile_colors = [(180, 235, 255), (140, 210, 240), (240, 250, 255), (100, 180, 220)]
                    else:
                        fragile_colors = [theme.FRAGILE_TOP, theme.FRAGILE_SIDE_R, (180, 90, 40), (240, 160, 90)]
                    self.renderer.burst(cell, n=28, colors=fragile_colors, z=0.05)
                self.audio.play("fall")

            anims.append(
                FallAnim(
                    piece,
                    fragile_tiles,
                    tilt_roll=tilt_roll,
                    dpos=dpos,
                    is_half_fall=is_half_fall,
                    c_sup=c_sup_cell,
                    c_void=c_void_cell,
                    statics=statics,
                    on_start=start_fall,
                )
            )
        elif o == Outcome.WON:
            goal = self.level.problem.goal_pos
            new_best = not self.used_solver and self.progress.record_win(self.level.name, self.session.moves)
            if new_best:
                self.toast(f"New best: {self.session.moves} moves", theme.GOOD, 3.0)
            won_frame = roll_frame(self.block_frame, ev.action) if ev.action else self.block_frame
            piece = {"cells": (goal,), "kind": "block", "height": 2.0, "active": True, "frame": won_frame}

            def swallowed():
                self.renderer.burst(goal)
                self.renderer.glow(goal, theme.GOAL_RING, 1.3, dur=1.2)
                self.audio.play("sink")
                self.audio.play("win")
                if new_best:
                    self.audio.play("best")

            anims.append(SinkAnim(piece, on_start=swallowed))
        elif ev.teleported:
            spawn_pcs = pieces_of(ev.new)
            for pc in spawn_pcs:
                pc["frame"] = INITIAL_FRAME
            anims.append(SpawnAnim(
                spawn_pcs,
                on_start=lambda: self.toast("Split! Press Space to swap cubes", theme.SPLIT_COLOR, 3.2),
            ))
        self.anims.extend(anims)

    def _landing_fx(self, ev):
        """Hiệu ứng lúc khối chạm sàn: ép dẹt, vầng sáng ở công tắc / cầu vừa đổi, và âm thanh."""
        pb, rd = self.level.problem, self.renderer
        if ev.outcome == Outcome.MOVED and not ev.teleported:
            pcs = pieces_of(ev.new)
            k = ev.prev.active_block if (ev.prev.is_split and ev.new.is_split) else 0
            rd.land_on(pcs[k]["cells"])
        if ev.outcome == Outcome.WON:
            return
        self.audio.play("roll")
        fired = fired_switches(pb, ev)
        for cell in fired:
            sw = pb.switches[cell]
            col = rd.bridge_color[pb.bridge_indices[sw.linked_bridges[0]]] if sw.linked_bridges else theme.SPLIT_COLOR
            rd.glow(cell, col)
        for idx in ev.bridge_changes:
            if rd.bridge_cell[idx] is not None:
                rd.glow(rd.bridge_cell[idx], rd.bridge_color[idx], 0.8)
        if fired:
            self.audio.play("switch")
        if any(ev.bridge_changes.values()):
            self.audio.play("bridge_open")
        if not all(ev.bridge_changes.values()):
            self.audio.play("bridge_close")
        if ev.teleported:
            self.audio.play("split")
        elif ev.merged:
            self.audio.play("merge")

    # ------------------------------------------------------------------ solver
    def start_solver(self, name: str):
        if self.job is not None and not self.job.done:
            return
        self.selected_solver = name
        self.stats = None
        # Giải bài toán bắt đầu từ vị trí hiện tại thay vì reset về đầu màn
        current_problem = Problem(
            grid=self.level.problem.grid,
            goal_pos=self.level.problem.goal_pos,
            initial_state=self.session.state,
            bridge_indices=self.level.problem.bridge_indices,
            switches=self.level.problem.switches,
        )
        self.job = SolverJob(name, current_problem, self.heuristic if name == "A*" else None)
        self.job.start()

    def cancel_solver(self, quiet: bool = False):
        """Dừng lần giải đang chạy (nút Stop trong bảng AI, hoặc khi đổi màn)."""
        job = getattr(self, "job", None)
        self.job = None
        if job is not None and not job.done:
            job.cancel()
            if not quiet:
                self.toast(f"{job.label} stopped", theme.INFO, 2.0)

    def toggle_pause(self):
        self.paused = not self.paused

    def toggle_path(self):
        self.show_path = not self.show_path
        self.settings.set("show_path", self.show_path)

    def toggle_step_guide(self):
        if self.selected_solver is None:
            self.toast("Please select an algorithm first (TAB)", theme.BAD, 2.0)
            return
        self.show_step_guide = not self.show_step_guide
        self.settings.set("show_step_guide", self.show_step_guide)
        if self.show_step_guide:
            self._update_step_guide()
        self.toast("Step Guide: ON" if self.show_step_guide else "Step Guide: OFF", theme.INFO, 1.8)

    def _update_step_guide(self):
        if self.session.status != Status.PLAYING or not self.selected_solver:
            self.next_step_info = None
            return

        st = self.session.state
        if self.guide_states and len(self.guide_states) > 1 and self.guide_states[0] == st and self.guide_solution:
            act = self.guide_solution[0]
            nxt = self.guide_states[1]
            self.next_step_info = {"action": act, "next_state": nxt}
            return

        res = compute_step_guide(
            self.level.problem,
            st,
            self.guide_solution,
            self.guide_states,
            solver_name=self.selected_solver,
            heuristic=self.heuristic if self.selected_solver == "A*" else None,
        )
        if res:
            self.guide_solution = res["solution"]
            self.guide_states = res["states"]
            self.next_step_info = {"action": res["action"], "next_state": res["next_state"]}
        else:
            self.next_step_info = None

    def _recalculate_guide_from_current(self):
        """Tính lại Step Guide và Path từ ô hiện tại theo thuật giải user đang chọn khi lỡ đi sai ô."""
        if not self.selected_solver or self.session.status != Status.PLAYING:
            return
        st = self.session.state
        sub_problem = Problem(
            grid=self.level.problem.grid,
            goal_pos=self.level.problem.goal_pos,
            initial_state=st,
            bridge_indices=self.level.problem.bridge_indices,
            switches=self.level.problem.switches,
        )
        try:
            solver = make_solver(self.selected_solver, self.heuristic if self.selected_solver == "A*" else None)
            actions = solver.solve(sub_problem)
            if actions is not None:
                self.guide_solution = actions
                self.guide_states = replay_states(sub_problem, actions)
                self.path_steps = path_steps(sub_problem, actions)
                self.replay = deque(actions)
                self.replay_done = []
                self.replay_total = len(actions)
                self._update_step_guide()
            else:
                self.guide_solution = None
                self.guide_states = None
                self.path_steps = []
                self.next_step_info = None
        except Exception:
            traceback.print_exc()

    def _on_player_moved(self):
        """Khi người chơi hoặc auto-replay vừa hoàn thành một bước lăn trên bàn cờ."""
        if not self.selected_solver or self.session.status != Status.PLAYING:
            return
        from_replay = getattr(self, "is_action_from_replay", False)
        st = self.session.state
        if self.guide_solution and self.guide_states:
            if len(self.guide_states) > 0 and st == self.guide_states[0]:
                self._update_step_guide()
                return
            if len(self.guide_states) > 1 and st == self.guide_states[1]:
                # Đúng ô theo lộ trình! Tiến lên 1 bước:
                act_done = self.guide_solution[0] if self.guide_solution else None
                if not from_replay and self.replay:
                    self.replay_done.append(self.replay.popleft())
                self.guide_solution = self.guide_solution[1:]
                self.guide_states = self.guide_states[1:]
                self._update_step_guide()
                return
        if from_replay:
            return
        # Lỡ đi sai ô hoặc chệch lộ trình: tính lại từ ô hiện tại theo thuật giải đang chọn!
        self._recalculate_guide_from_current()

    def _request_step(self, direction: int):
        self.step_req = direction

    # ------------------------------------------------------------------ so sánh nhiều thuật toán
    def open_compare(self):
        """Mở bảng so sánh: lần đầu thì chạy tất cả solver, các lần sau xem lại kết quả đã có."""
        if self.level_idx in self.compare_store and self.compare_job is None:
            self.compare_open = True
        else:
            self.start_compare()

    def start_compare(self):
        if self.compare_job is not None and not self.compare_job.finished:
            return
        avail = available_solvers()
        all_cfgs = compare_configs()
        configs = [c for c in all_cfgs if avail.get(c.solver)]
        self.compare_skipped = sorted({c.solver for c in all_cfgs if not avail.get(c.solver)})
        if not configs:
            self.toast("No solver is implemented yet", theme.BAD)
            return
        self.compare_store.pop(self.level_idx, None)
        self.compare_job = CompareJob(self.level, configs)
        self.compare_job_level = self.level_idx
        self.compare_job.start()
        self.compare_open = True

    def close_compare(self):
        if self.compare_job is not None and not self.compare_job.finished:
            self.compare_job.cancel()
            self.compare_job = None
        self.compare_open = False

    def _compare_data(self) -> dict:
        job = self.compare_job
        if job is not None:
            return {
                "title": self.level.name,
                "labels": [c.label for c in job.configs],
                "rows": {r["solver"]: r for r in list(job.results)},
                "running_label": job.current.label if (job.current and not job.finished) else None,
                "total": job.total,
                "skipped": self.compare_skipped,
            }
        stored = self.compare_store.get(self.level_idx, {"labels": [], "rows": {}})
        return {"title": self.level.name, "running_label": None, "total": len(stored["labels"]),
                "skipped": self.compare_skipped, **stored}

    def _poll_compare(self):
        job = self.compare_job
        if job is None or not job.finished:
            return
        self.compare_job = None
        self.compare_store[self.compare_job_level] = {
            "labels": [c.label for c in job.configs],
            "rows": {r["solver"]: r for r in job.results},
        }

    def _replay_row(self, row: dict):
        """Bấm một dòng trong bảng so sánh: phát lại lời giải của thuật toán đó trên bàn cờ."""
        self.compare_open = False
        self.restart()
        metrics = {
            "search_time_sec": row["time_ms"] / 1000.0,
            "peak_memory_kb": row["memory_kb"],
            "expanded_nodes": row["expanded"],
            "solution_length": row["length"],
            "solution_cost": row["cost"],
        }
        out = SolveOutcome(row["solver"], row["solver"], list(row["actions"]), metrics)
        self.stats = out
        self._begin_replay(out.label, out.actions)

    def _begin_replay(self, label: str, actions: List[str], problem: Optional[Problem] = None):
        pb = problem or self.level.problem
        self.path_steps = path_steps(pb, actions)
        self.replay_done = []
        self.replay = deque(actions)
        self.used_solver = True
        self.replay_total = len(actions)
        self.replay_label = label
        self.replay_timer = 0.5
        self.paused = True  # Mặc định là PAUSE, không tự chạy luôn!
        self.guide_solution = list(actions)
        self.guide_states = replay_states(pb, actions)
        self._update_step_guide()

    def _save_compare_csv(self):
        data = self._compare_data()
        rows = [data["rows"][l] for l in data["labels"] if l in data["rows"]]
        if not rows:
            return
        safe = "".join(ch if ch.isalnum() else "_" for ch in self.level.name).strip("_")
        path = Path(__file__).resolve().parents[2] / "results" / f"compare_{safe}.csv"
        try:
            write_csv(rows, path)
            self.toast(f"Saved {path.parent.name}/{path.name}", theme.GOOD, 3.5)
        except OSError as exc:
            self.toast(f"Could not save CSV: {exc}", theme.BAD, 4.0)

    def _poll_solver(self):
        job = self.job
        if job is None or not job.done:
            return
        self.job = None
        if job.problem.grid is not self.level.problem.grid or job.problem.goal_pos != self.level.problem.goal_pos:
            return
        out = job.outcome
        if out.cancelled:
            return
        self.stats = out
        sub_problem = job.problem
        self.path_steps = path_steps(sub_problem, out.actions) if out.found else []
        self.replay_done = []
        if out.error:
            self.toast(f"{job.label} failed: {out.error}", theme.BAD, 5.0)
        elif not out.found:
            self.toast(f"{job.label}: no solution found", theme.BAD, 4.0)
        else:
            self._begin_replay(job.label, out.actions, problem=sub_problem)
            self.toast(f"{job.label}: found {len(out.actions)} actions (Paused)", theme.INFO, 3.0)

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
                if self.frame_history:
                    self.block_frame, self.cube_frames = self.frame_history.pop()
                self.renderer.set_bridges(self.session.state.bridges_state)
                self.renderer.clear_fragile_falls()

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
        if self.screen_state == "menu":
            self.menu.handle(event, mouse)
            return
        if self.screen_state == "level_select":
            self.level_select_view.handle(event, mouse)
            return
        if self.screen_state == "settings":
            self.settings_view.handle(event, mouse)
            return
        if self.screen_state == "paused":
            self.pause_menu.handle(event, mouse)
            return
        if self.session.status == Status.WON and not self.anims and not self.replay:
            if self.win_overlay.handle(event, mouse):
                return
        if event.type == pygame.KEYDOWN:
            self._key(event)
            return
        if self.compare_open:
            self.compare_view.handle(event, mouse, self._compare_data())
            return
        if self.race is not None:
            if self._camera_event(event, mouse):
                return
            for btn in self.race_buttons:
                if btn.handle(event, mouse):
                    return
            return
        if self.tip is not None and self.btn_tip_ok.handle(event, mouse):
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

        # Khi mở AI Drawer, chuyển giao toàn quyền xử lý cho SolverDrawer
        if self.show_ai_panel:
            if self.solver_drawer.handle(event, mouse):
                return
            return

        for btn in self._banner_buttons():
            if btn.handle(event, mouse):
                return

        # Nút Action trên thanh HUD
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for hk, hr in self.hud_rects.items():
                if hr.collidepoint(mouse):
                    if hk == "undo":
                        self.undo()
                    elif hk == "restart":
                        self.restart()
                    elif hk == "solver":
                        self.show_ai_panel = True
                        self.audio.play("switch")
                    elif hk == "pause":
                        self.push_screen("paused")
                    return

        # Camera rotation / zoom
        if self._camera_event(event, mouse):
            return

    def _key(self, event):
        k = event.key
        if k == pygame.K_F11:
            pygame.display.toggle_fullscreen()
        elif k == pygame.K_F12:
            self.save_screenshot()
        elif k == pygame.K_m:
            self._set_sound(not self.audio.enabled)
        elif k == pygame.K_TAB:
            self.show_ai_panel = not self.show_ai_panel
            self.audio.play("switch")
        elif k == pygame.K_ESCAPE:
            if self.race is not None:
                self.exit_race()
            elif self.compare_open:
                self.close_compare()
            elif self.picker_open:
                self.picker_open = False
            elif self.show_ai_panel:
                self.show_ai_panel = False
                self.audio.play("switch")
            else:
                self.push_screen("paused")
        elif self.race is not None:
            self._race_key(k)
        elif self.compare_open:
            pass
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
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.tip is not None:
            self.dismiss_tip()
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.session.status == Status.WON:
            self.next_level()
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.session.status == Status.LOST:
            self.restart()
        elif k == pygame.K_p:
            self.toggle_pause()
        elif k == pygame.K_v:
            self.toggle_path()
        elif k in (pygame.K_b, pygame.K_h):
            self.toggle_step_guide()
        elif k == pygame.K_PERIOD:
            self._request_step(1)
        elif k == pygame.K_COMMA:
            self._request_step(-1)
        elif k == pygame.K_c:
            self._reset_camera()

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
            if self.race is not None:
                self.race.set_camera(self.cam)

    # ------------------------------------------------------------------ cập nhật
    def update(self, dt: float, mouse):
        if self.screen_state == "menu":
            self.menu.update(dt, mouse)
            return
        if self.screen_state == "level_select":
            self.level_select_view.update(dt, mouse)
            return
        if self.screen_state == "settings":
            self.settings_view.update(dt, mouse)
            return
        if self.screen_state == "paused":
            self.pause_menu.update(dt, mouse)
            return
        self._layout_bottom_boxes()
        for btn in self._banner_buttons():
            btn.update(dt, mouse)
        if self.show_ai_panel:
            self.solver_drawer.update(dt, mouse)
        self._avail_timer -= dt
        if self._avail_timer <= 0:
            self.available = available_solvers()
            self._avail_timer = 2.0

        self._poll_solver()
        self._poll_compare()
        if self.race is not None:
            self.race.update(dt, self.speed, self.race_paused)
            for btn in self.race_buttons:
                btn.update(dt, mouse)
        self._maybe_show_tip()
        if self.tip is not None:
            self.btn_tip_ok.update(dt, mouse)
            if self.session.moves - self.tip_start_moves >= 2 or not self.settings.show_tips:
                self.dismiss_tip(chain=False)  # người chơi đã bắt đầu chơi: không bật thẻ khác giữa chừng
        compare_busy = self.compare_job is not None
        data = self._compare_data() if self.compare_open else {"rows": {}}
        self.compare_view.update(dt, mouse, compare_busy, bool(data["rows"]))
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
                if not self.anims and not self.queued:
                    self._on_player_moved()
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
        frame = kw.pop("frame", piece.get("frame"))
        self.renderer.draw_piece(
            surf, piece["cells"], piece["kind"], piece["height"],
            active=piece["active"], frame=frame, **kw,
        )

    def _draw_pieces(self, surf, static_filter=None):
        rd = self.renderer
        st = self.session.state
        if self.anims:
            anim = self.anims[0]
            p = min(1.0, anim.t / anim.dur)
            for s in anim.statics:
                if static_filter is None or static_filter(s):
                    self.draw_piece(surf, s)
            if anim.kind == "roll":
                self.draw_piece(surf, anim.piece, roll=(anim.direction, smoothstep(p) * math.pi / 2))
            elif anim.kind == "fall":
                for cell in anim.fragile_tiles:
                    rd.draw_falling_fragile_tile(surf, cell, p)
                alpha = max(0.0, 1.0 - p ** 1.4)
                roll_arg, dr_off, dc_off, dz = anim.get_transform(p)
                self.draw_piece(
                    surf, anim.piece, roll=roll_arg, dz=dz, alpha=alpha,
                    dr_offset=dr_off, dc_offset=dc_off, shadow=False,
                )
            elif anim.kind == "sink":
                pc = anim.piece
                rd.draw_swallow(surf, pc["cells"], pc["kind"], pc["height"], p, frame=pc.get("frame"))
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
        if (self.session.status == Status.PLAYING and not self.replay and not self.picker_open
                and self.settings.show_floor_arrows):
            controlled = (st.get_occupied_cells()[st.active_block],) if st.is_split else st.get_occupied_cells()
            rd.draw_direction_hints(surf, controlled, self.key_flash)
        for pc in sorted(pieces, key=lambda q: rd.iso.order(*q["cells"][0])):
            if pc["kind"] == "cube" and len(pieces) == 2:
                idx = 0 if pc["cells"][0] == st.get_occupied_cells()[0] else 1
                pc["frame"] = self.cube_frames[idx]
            else:
                pc["frame"] = self.block_frame
            if pc["kind"] == "cube" and pc["active"] and len(pieces) == 2:
                rd.draw_floor_ring(surf, pc["cells"][0], theme.TEXT)
            self.draw_piece(surf, pc)

    def _draw_hud(self, surf):
        lv = self.level
        name = self._level_title(self.level_idx)
        draw_text(surf, name, theme.font(42, True), (242, 248, 255), (56, 36))
        chip_col = theme.group_color(lv.group)
        label = lv.group.upper()
        f = theme.font(16, True)
        tw = f.size(label)[0]
        chip = pygame.Rect(58, 96, tw + 28, 28)
        rrect(surf, chip, (*chip_col, 50), 14, chip_col, 2)
        draw_text(surf, label, f, chip_col, chip.center, "center")
        for i, line in enumerate(wrap_text(lv.description, theme.font(20), 650)[:2]):
            draw_text(surf, line, theme.font(20), (160, 185, 215), (58, 136 + i * 26))

        # Moves & Record Pill (giữa trên)
        best = self.progress.best(lv.name)
        best_str = f"{best}" if best is not None else "-"
        moves_pill = pygame.Rect(self.screen.get_width() // 2 - 120, 36, 240, 42)
        rrect(surf, moves_pill, (14, 22, 38, 210), radius=10, border=(55, 90, 135), border_w=1)
        moves_txt = f"MOVES: {self.session.moves}   |   BEST: {best_str}"
        draw_text(surf, moves_txt, theme.font(17, True), (220, 240, 255), moves_pill.center, "center")

        # Top-Right Action Pills
        self.hud_rects = {}
        mouse = pygame.mouse.get_pos()
        if not self.show_ai_panel:
            actions = [
                ("undo", "[Z] Undo", self.session.can_undo),
                ("restart", "[R] Restart", True),
                ("solver", "[TAB] AI Solver", True),
                ("pause", "[ESC] Pause", True),
            ]
            curr_right = self.screen.get_width() - 56
            for key, act_lbl, is_enabled in reversed(actions):
                act_w = 125 if key != "solver" else 150
                rect = pygame.Rect(curr_right - act_w, 36, act_w, 42)
                self.hud_rects[key] = rect
                is_hover = is_enabled and rect.collidepoint(mouse)
                if is_hover:
                    bg = (32, 48, 75)
                    b_col = (90, 160, 230)
                    t_col = (255, 255, 255)
                elif is_enabled:
                    bg = (14, 22, 38, 210)
                    b_col = (45, 75, 115)
                    t_col = (190, 215, 240)
                else:
                    bg = (12, 18, 30, 150)
                    b_col = (30, 45, 70)
                    t_col = (90, 110, 135)
                rrect(surf, rect, bg, radius=10, border=b_col, border_w=1)
                draw_text(surf, act_lbl, theme.font(15, bold=True), t_col, rect.center, "center")
                curr_right -= (act_w + 14)

    def _draw_compass(self, surf):
        """Thẻ chỉ hướng: mỗi phím lăn khối về hướng nào trên màn hình."""
        card = pygame.Rect(28, 826, 252, 224)
        if not self.settings.show_compass:
            self._draw_camera_help(surf, 28)
            return
        rrect(surf, card, (*theme.PANEL, 214), 20, theme.PANEL_EDGE, 2)
        draw_text(surf, "MOVE KEYS", theme.font(14, True), theme.TEXT_FAINT, (card.x + 18, card.y + 14))
        cx, cy = card.centerx, card.y + 130
        pygame.draw.circle(surf, theme.TEXT_FAINT, (cx, cy), 5)
        labels = {"U": "W ^", "D": "S v", "L": "A <", "R": "D >"}
        for key, label in labels.items():
            dx, dy = self.renderer.screen_dir(key)
            hot = self.key_flash[key]
            if self.show_step_guide and self.next_step_info and self.next_step_info.get("action") == key:
                hot = max(hot, 0.70 + 0.30 * math.sin(self.renderer.time * 5.0))
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

        self._draw_camera_help(surf, card.right + 14)

    def _draw_camera_help(self, surf, x: int):
        if not self.settings.show_camera_help:
            return
        cam_card = pygame.Rect(x, 826 + 224 - 98, 372, 98)
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
        y = 100  # dưới thanh nút HUD (Undo / Restart / AI Solver / Pause) ở y 36-78
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

    # ------------------------------------------------------------------ Race: hai thuật toán cạnh nhau
    def start_race(self, row_a: dict, row_b: dict):
        self.compare_open = False
        self.restart()
        self.tip = None
        self.race = Race(
            self.level,
            [row_a, row_b],
            self.cam,
            area=pygame.Rect(40, 110, 1380, 820),
            theme_name=self.current_theme,
        )
        self.race_paused = False

    def exit_race(self):
        self.race = None
        self.compare_open = self.level_idx in self.compare_store  # quay lại bảng so sánh

    def restart_race(self):
        if self.race is not None:
            self.race.restart()
            self.race_paused = False

    def toggle_race_pause(self):
        self.race_paused = not self.race_paused

    def _race_key(self, k: int):
        if k == pygame.K_SPACE:
            self.toggle_race_pause()
        elif k == pygame.K_r:
            self.restart_race()
        elif k == pygame.K_v:
            self.toggle_path()
        elif k in (pygame.K_b, pygame.K_h):
            self.toggle_step_guide()
        elif k == pygame.K_ESCAPE:
            self.exit_race()

    def _draw_race_panel(self, surf):
        """Panel bên phải khi đua: số liệu của hai thuật toán đặt cạnh nhau (nhìn là so sánh được ngay)."""
        is_desert = (self.current_theme == "desert")
        panel_rect = pygame.Rect(1444, 28, 448, 1024)
        panel_bg = (34, 18, 28, 248) if is_desert else (14, 22, 38, 248)
        panel_bdr = (215, 140, 60) if is_desert else (75, 145, 225)
        top_glow = (255, 205, 80) if is_desert else (120, 240, 255)
        accent_title = (255, 215, 120) if is_desert else (120, 240, 255)

        rrect(surf, panel_rect, panel_bg, radius=18, border=panel_bdr, border_w=2)
        pygame.draw.line(surf, top_glow, (panel_rect.x + 20, panel_rect.y + 2), (panel_rect.right - 20, panel_rect.y + 2), 2)

        x0 = panel_rect.x + 20
        pw = panel_rect.w - 40

        draw_text(surf, "[ REAL-TIME BENCHMARK ]", theme.font(13, True), accent_title, (x0, panel_rect.y + 16))
        draw_text(surf, "TELEMETRY STATS", theme.font(24, True), (245, 252, 255), (x0, panel_rect.y + 36))
        draw_text(surf, f"Stage: {self.level.name}", theme.font(14), theme.TEXT_DIM, (x0, panel_rect.y + 68))

        pygame.draw.line(surf, (60, 40, 52) if is_desert else (45, 75, 115), (x0, panel_rect.y + 92), (x0 + pw, panel_rect.y + 92), 1)

        from App.GUI.compare_view import fmt_value

        rows = (
            ("Actions", "length", "{}"),
            ("Moves", "moves", "{}"),
            ("Cost", "cost", "{}"),
            ("Expanded nodes", "expanded", None),
            ("Search time", "time_ms", None),
            ("Peak memory", "memory_kb", None),
        )

        for i, lane in enumerate(self.race.state.lanes):
            card_y = panel_rect.y + 104 + i * 376
            card = pygame.Rect(x0, card_y, pw, 360)
            col = LANE_COLORS[i]
            card_bg = (44, 24, 30, 210) if (is_desert and i == 0) else ((36, 18, 42, 210) if is_desert else ((24, 34, 54, 210) if i == 0 else (28, 22, 50, 210)))
            rrect(surf, card, card_bg, radius=14, border=col, border_w=1)

            # Header thẻ
            draw_text(surf, lane.label, theme.font(22, True), col, (card.x + 16, card.y + 12))
            pill_rect = pygame.Rect(card.right - 88, card.y + 12, 72, 24)
            rrect(surf, pill_rect, (*col, 40), radius=6, border=col, border_w=1)
            draw_text(surf, f"LANE {i + 1}", theme.font(12, True), col, pill_rect.center, "center")

            # Tiến độ
            draw_text(surf, f"Step {lane.index} / {lane.total}", theme.mono(15, True), (240, 250, 255), (card.x + 16, card.y + 44))
            bar = pygame.Rect(card.x + 16, card.y + 66, pw - 32, 5)
            rrect(surf, bar, (32, 20, 28) if is_desert else (20, 30, 48), radius=2)
            frac = lane.index / max(1, lane.total)
            rrect(surf, pygame.Rect(bar.x, bar.y, max(4, int(bar.w * frac)), bar.h), col, radius=2)

            pygame.draw.line(surf, (60, 38, 48) if is_desert else (40, 56, 82), (card.x + 16, card.y + 80), (card.right - 16, card.y + 80), 1)

            for j, (name, key, fmt) in enumerate(rows):
                v = lane.row.get(key)
                text = fmt.format(v) if fmt else fmt_value(key, v)
                ry = card.y + 88 + j * 44
                if j % 2 == 1:
                    rrect(surf, (card.x + 8, ry - 3, pw - 16, 38), (40, 25, 35, 120) if is_desert else (20, 32, 52, 120), radius=6)
                draw_text(surf, name, theme.font(14), theme.TEXT_DIM, (card.x + 16, ry + 5))
                draw_text(surf, text, theme.mono(15, True), (245, 252, 255), (card.right - 16, ry + 5), "topright")

        # Thẻ kết quả / trạng thái cuộc đua ở đáy panel
        verdict_y = panel_rect.y + 864
        verdict_rect = pygame.Rect(x0, verdict_y, pw, 140)
        verdict_bg = (28, 16, 24, 230) if is_desert else (18, 26, 44, 230)
        verdict_bdr = (100, 58, 50) if is_desert else (50, 80, 125)
        rrect(surf, verdict_rect, verdict_bg, radius=12, border=verdict_bdr, border_w=1)

        if not self.race.state.done:
            draw_text(surf, "RACE IN PROGRESS", theme.font(15, True), accent_title, (verdict_rect.centerx, verdict_y + 24), "center")
            draw_text(surf, "Both solvers executing lockstep.", theme.font(13), theme.TEXT_DIM, (verdict_rect.centerx, verdict_y + 54), "center")
            draw_text(surf, "Shortest path reaches goal first!", theme.font(13), theme.TEXT_FAINT, (verdict_rect.centerx, verdict_y + 80), "center")
            draw_text(surf, "[Space] Pause   |   [R] Restart", theme.font(12), (160, 185, 215), (verdict_rect.centerx, verdict_y + 110), "center")
        else:
            draw_text(surf, "RACE FINISHED", theme.font(15, True), theme.GOOD, (verdict_rect.centerx, verdict_y + 22), "center")
            draw_text(surf, self.race.state.headline(), theme.font(16, True), (245, 252, 255), (verdict_rect.centerx, verdict_y + 54), "center")
            draw_text(surf, "Click 'Exit race' or press Esc to return.", theme.font(13), theme.TEXT_DIM, (verdict_rect.centerx, verdict_y + 92), "center")

    def _draw_race(self, mouse):
        surf = self.screen
        race = self.race
        surf.blit(self.bg, (0, 0))
        a, b = race.state.lanes
        draw_text(surf, f"{a.label}   VS   {b.label}", theme.font(38, True), (245, 252, 255), (48, 28))
        sub_txt = f"Real-Time Algorithm Race  |  Stage: {self._level_title(self.level_idx)}"
        draw_text(surf, sub_txt, theme.font(16), theme.TEXT_DIM, (50, 74))

        race.draw(surf, mouse, self.show_path)
        self._draw_race_panel(surf)

        # Banner chiến thắng giữa 2 làn
        if race.state.done:
            banner_r = pygame.Rect(0, 0, 742, 44)
            banner_r.centerx = 40 + 1380 // 2
            banner_r.y = 896
            rrect(surf, banner_r, (*theme.PANEL, 245), radius=14, border=theme.GOOD, border_w=2)
            draw_text(surf, race.state.headline(), theme.font(19, True), theme.GOOD, banner_r.center, "center")

        # 4 nút điều khiển đua bên dưới 2 làn
        self.race_buttons[0].label = "Resume  (Space)" if self.race_paused else "Pause  (Space)"
        self.race_buttons[2].label = "Path: ON  (V)" if self.show_path else "Path: OFF  (V)"
        for btn in self.race_buttons:
            btn.draw(surf)

        self._draw_toasts(surf)
    # ------------------------------------------------------------------ gợi ý hướng dẫn
    def _maybe_show_tip(self):
        """Hiện gợi ý đến lượt (nếu có) khi màn mới nạp xong và không có lớp phủ nào đang mở."""
        if not self._tip_pending or self.tip is not None:
            return
        if self.picker_open or self.compare_open or self.session.status != Status.PLAYING:
            return
        self._tip_pending = False
        if not self.settings.show_tips:
            return
        key = tip_for(self.level, self.settings.tips_seen)
        if key is not None:
            self.tip = key
            self.tip_start_moves = self.session.moves
            self.settings.mark_tip_seen(key)

    def dismiss_tip(self, chain: bool = True):
        """Đóng thẻ gợi ý. ``chain``: nếu màn còn gợi ý khác đến lượt thì hiện tiếp ngay."""
        self.tip = None
        self._tip_pending = chain

    def _draw_tip(self, surf):
        if self.tip is None or self.session.status != Status.PLAYING or self.compare_open:
            return
        title, body = TIPS[self.tip]
        r = self.tip_rect
        rrect(surf, r, theme.PANEL, 22, theme.ACCENT, 2)
        draw_text(surf, "NEW", theme.font(14, True), theme.ACCENT_DARK, (r.x + 28, r.y + 16))
        draw_text(surf, title, theme.font(28, True), theme.ACCENT, (r.x + 28, r.y + 34))
        for i, line in enumerate(wrap_text(body, theme.font(18), r.w - 56)[:5]):
            draw_text(surf, line, theme.font(18), theme.TEXT, (r.x + 28, r.y + 72 + i * 23))
        self.btn_tip_ok.draw(surf)

    # ------------------------------------------------------------------ chọn màn
    PICK_COLS, PICK_W, PICK_H, PICK_GAP = 5, 320, 212, 22
    TABS = (("classic", "CLASSIC"), ("custom", "CUSTOM"))

    def _tab_ids(self, tab: Optional[str] = None) -> List[int]:
        tab = tab or self.picker_tab
        return [i for i, lv in enumerate(self.levels) if lv.section == tab]

    def _section_position(self, idx: int) -> int:
        """Số thứ tự (từ 1) của màn trong nhóm của nó (Classic hoặc Custom)."""
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
    def _thumb(self, i: int, size=(276, 170)) -> pygame.Surface:
        key = (i, size, self.current_theme)
        if key in self.thumbs:
            return self.thumbs[key]
        # Cùng bộ vẽ isometric với bàn chơi, thu nhỏ vào ô ảnh: bố cục, cầu và công tắc giống hệt khi chơi.
        surf = pygame.Surface(size, pygame.SRCALPHA)
        rd = BoardRenderer(
            self.levels[i], area=pygame.Rect(10, 8, size[0] - 20, size[1] - 16), cam=Camera(), min_fit=4.0,
            theme_name=self.current_theme,
        )
        rd.draw_board(surf, show_hints=False)
        self.thumbs[key] = surf
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
        pass

    def draw(self, mouse):
        if self.screen_state == "menu":
            self.menu.draw(self.screen, mouse)
            return
        if self.screen_state == "level_select":
            self.level_select_view.draw(self.screen, mouse)
            return
        if self.screen_state == "settings":
            self.settings_view.draw(self.screen, mouse)
            return
        if self.race is not None:
            self._draw_race(mouse)
            return
        surf = self.screen

        falling_anim = self.anims[0] if (self.anims and self.anims[0].kind == "fall") else None
        sink_anim = self.anims[0] if (self.anims and self.anims[0].kind == "sink") else None
        if falling_anim:
            p = min(1.0, falling_anim.t / falling_anim.dur)
            roll_arg, dr_off, dc_off, dz = falling_anim.get_transform(p)
            fall_cells = falling_anim.piece["cells"]
            mid_r = sum(c[0] for c in fall_cells) / len(fall_cells) + dr_off
            mid_c = sum(c[1] for c in fall_cells) / len(fall_cells) + dc_off
            center_order = self.renderer.iso.order(mid_r, mid_c)
            tan_elev = self.renderer.iso.view[2]
            height = falling_anim.piece["height"]

            if falling_anim.is_half_fall and p <= 0.35:
                # Trong pha bập bênh ở mép sàn: khối tựa trên c_sup và nhấc bổng trên sàn
                # Giữ c_sup và các ô sàn lân cận ở Pass 1 để không cắt xén khối
                sup_order = self.renderer.iso.order(*falling_anim.c_sup)
                cut_order = sup_order + 0.5
                force_p1 = {falling_anim.c_sup}
                exclude_p2 = {falling_anim.c_sup}
            else:
                # Pha rơi chìm (hoặc rơi tự do / ô vỡ): cut_order hạ sâu theo dz
                # Khi khối rơi phía sau sàn, các ô mép sàn/vách hố phía trước có thứ tự lớn hơn
                # sẽ được vẽ ở Pass 2 đè lên khối, che khuất khối rơi tự nhiên
                cut_order = center_order + (dz + 0.2 * height) * tan_elev
                force_p1 = None
                exclude_p2 = None

            surf.blit(self.bg, (0, 0))
            self.renderer.draw_board(surf, max_order=cut_order, force_include_cells=force_p1)
            self._draw_pieces(surf, static_filter=lambda s: self.renderer.iso.order(*s["cells"][0]) <= cut_order)
            self.renderer.draw_board(surf, min_order=cut_order, show_hints=False, exclude_cells=exclude_p2)
            for s in falling_anim.statics:
                if self.renderer.iso.order(*s["cells"][0]) > cut_order:
                    self.draw_piece(surf, s)
            self.renderer.draw_glows(surf)
            if self.settings.show_link_lines and self.link_segs:
                self.renderer.draw_link_lines(surf, self.link_segs)
            if self.show_path and self.path_steps:
                done = len(self.replay_done) if (self.replay or self.replay_done) else None
                self.renderer.draw_path(surf, self.path_steps, done)
        elif sink_anim:
            goal = sink_anim.piece["cells"][0]
            cut_order = self.renderer.iso.order(*goal)
            surf.blit(self.bg, (0, 0))
            self.renderer.draw_board(surf, max_order=cut_order, force_include_cells={goal})
            self._draw_pieces(surf)
            self.renderer.draw_board(surf, min_order=cut_order, show_hints=False, exclude_cells={goal})
            self.renderer.draw_glows(surf)
            if self.settings.show_link_lines and self.link_segs:
                self.renderer.draw_link_lines(surf, self.link_segs)
        else:
            self.renderer.draw_board(surf, background=self.bg)  # dán luôn nền + lớp bàn tĩnh
            self.renderer.draw_glows(surf)
            if self.settings.show_link_lines and self.link_segs:
                self.renderer.draw_link_lines(surf, self.link_segs)
            if self.show_path and self.path_steps:
                done = len(self.replay_done) if (self.replay or self.replay_done) else None
                self.renderer.draw_path(surf, self.path_steps, done)
            self._draw_pieces(surf)
            if self.show_step_guide and self.next_step_info and self.session.status == Status.PLAYING and not self.anims:
                self.renderer.draw_ghost_step(
                    surf,
                    self.next_step_info["next_state"],
                    action=self.next_step_info.get("action"),
                    current_state=self.session.state,
                )
        self.renderer.draw_particles(surf)
        self._draw_hud(surf)  # HUD vẽ sau bàn cờ để luôn nằm trên cùng
        self._draw_compass(surf)
        self._draw_toasts(surf)
        if self.show_ai_panel:
            self.solver_drawer.draw(surf, mouse)
        self._draw_banner(surf)
        self._draw_tip(surf)
        if self.picker_open:
            self._draw_picker(surf, mouse)
        if self.compare_open:
            self.compare_view.draw(surf, mouse, self._compare_data())
        self._draw_tooltip(surf, mouse)
        if self.session.status == Status.WON and not self.anims and not self.replay:
            self.win_overlay.draw(surf, mouse)
        if self.screen_state == "paused":
            self.pause_menu.draw(surf, mouse)

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
    # python play.py [classic|custom] [số màn]: số màn tính trong nhóm đã chọn (mặc định: nhóm Classic)
    section, number = "classic", 1
    for a in argv:
        if a.isdigit():
            number = int(a)
        elif a.lower() in ("classic", "custom", "ours"):
            section = "custom" if a.lower() in ("custom", "ours") else "classic"
    app = App(0)
    ids = [i for i, lv in enumerate(app.levels) if lv.section == section] or [0]
    app.load_level(ids[max(0, min(number - 1, len(ids) - 1))])
    if argv:
        app.screen_state = "playing" 
    app.run()


if __name__ == "__main__":
    main()
