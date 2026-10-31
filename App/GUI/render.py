"""Vẽ bàn chơi dạng isometric (2.5D): ô sàn có độ dày, cầu, công tắc và khối 3D.

Toạ độ lưới ``(r, c, z)`` được chiếu bằng ``Iso.p``: trục cột ``c`` chạy gần như
Tây -> Đông (nghiêng 15 độ ngược chiều kim đồng hồ), trục hàng ``r`` chạy xuống
phía người chơi. Camera nhìn từ phía r lớn, c nhỏ và z cao, nên mặt "nam" (r + 1),
mặt "tây" (c) và mặt trên là các mặt nhìn thấy; ô có ``Iso.order`` lớn hơn nằm
gần camera hơn và phải được vẽ sau (painter's algorithm).
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

import pygame
import pygame.gfxdraw as gfx

from App.Components.features import SwitchMode, SwitchType, TileType
from App.GUI import theme
from App.GUI.models import Frame3D, INITIAL_FRAME, get_penguin_mesh, get_cactus_mesh
from App.Components.state import Orientation, State
from App.GUI.pieces import pieces_of
from App.GUI.theme import mix, shade
from App.GUI.widgets import draw_text, rrect

Cell = Tuple[int, int]

_FACES = ((0, 1, 2, 3), (4, 5, 6, 7), (0, 1, 5, 4), (3, 2, 6, 7), (0, 3, 7, 4), (1, 2, 6, 5))


def poly(surf, color, pts, outline=None):
    ipts = [(int(round(x)), int(round(y))) for x, y in pts]
    if len(color) == 3:
        color = (*color, 255)
    gfx.filled_polygon(surf, ipts, color)
    gfx.aapolygon(surf, ipts, outline or color)


def polyline(surf, color, pts, width=3):
    ipts = [(int(round(x)), int(round(y))) for x, y in pts]
    pygame.draw.lines(surf, color[:3], False, ipts, width)
    pygame.draw.aalines(surf, color[:3], False, ipts)


def smoothstep(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


LAND_DUR = 0.30


def squash_curve(u: float) -> float:
    """Ép dẹt khi chạm sàn rồi nảy lại có giảm chấn: dương = dẹt, âm = giãn nhẹ."""
    if u < 0.0 or u >= 1.0:
        return 0.0
    return 0.16 * math.exp(-3.5 * u) * math.cos(7.5 * u)


ELEV_MIN, ELEV_MAX = math.radians(18), math.radians(80)
ZOOM_MIN, ZOOM_MAX = 0.45, 3.2


class Camera:
    """Góc nhìn do người chơi điều khiển: xoay, độ cao, phóng to, dịch.

    ``alpha`` là góc xoay quanh trục đứng, ``elev`` là góc nâng so với mặt phẳng
    ngang. Mặc định trục cột ``c`` chạy Tây -> Đông, nghiêng
    ``theme.AXIS_TILT_DEG`` độ ngược chiều kim đồng hồ.
    """

    DEFAULT_ELEV = math.asin(0.5)  # 30 độ

    def __init__(self):
        self.reset()

    @classmethod
    def default_alpha(cls) -> float:
        tilt = math.radians(theme.AXIS_TILT_DEG)
        return -math.atan(math.tan(tilt) / math.sin(cls.DEFAULT_ELEV))

    def reset(self) -> None:
        self.alpha = self.default_alpha()
        self.elev = self.DEFAULT_ELEV
        self.zoom = 1.0
        self.target_zoom = 1.0
        self.pan = [0.0, 0.0]

    def rotate(self, d_alpha: float, d_elev: float = 0.0) -> None:
        self.alpha = (self.alpha + d_alpha + math.pi) % math.tau - math.pi
        self.elev = max(ELEV_MIN, min(ELEV_MAX, self.elev + d_elev))

    def zoom_by(self, factor: float) -> None:
        self.target_zoom = max(ZOOM_MIN, min(ZOOM_MAX, self.target_zoom * factor))

    def update(self, dt: float) -> bool:
        """Làm mượt zoom; trả về True nếu góc nhìn vừa thay đổi."""
        if abs(self.target_zoom - self.zoom) < 1e-3:
            changed = self.zoom != self.target_zoom
            self.zoom = self.target_zoom
            return changed
        self.zoom += (self.target_zoom - self.zoom) * min(1.0, dt * 14.0)
        return True

    def key(self):
        return (round(self.alpha, 5), round(self.elev, 5), round(self.zoom, 4), *map(round, self.pan))


def _axes(alpha: float, elev: float):
    """Vector màn hình (một đơn vị lưới, chưa nhân tỉ lệ) của +c, +r và +z."""
    s, uz = math.sin(elev), math.cos(elev)
    ca, sa = math.cos(alpha), math.sin(alpha)
    return (ca, s * sa), (-sa, s * ca), uz, (ca, sa, s / uz)


class Iso:
    """Phép chiếu từ lưới ``(r, c, z)`` ra màn hình theo ``Camera``.

    Tỉ lệ vừa khít được tính cho góc nhìn mặc định (nên không nhảy khi xoay),
    tâm bàn cờ luôn ở giữa vùng vẽ (cộng thêm ``cam.pan``).
    """

    def __init__(self, rows: int, cols: int, area: pygame.Rect, cam: Optional[Camera] = None,
                 min_fit: float = 24.0):
        cam = cam or Camera()
        self.depth = 0.42  # độ dày ô sàn (đơn vị chiều cao)

        # Tỉ lệ vừa khít theo góc nhìn mặc định.
        (dcx, dcy), (drx, dry), duz, _ = _axes(Camera.default_alpha(), Camera.DEFAULT_ELEV)
        xs = [c * dcx + r * drx for r in (0, rows) for c in (0, cols)]
        ys = [c * dcy + r * dry for r in (0, rows) for c in (0, cols)]
        w1 = max(xs) - min(xs)
        h1 = (max(ys) - min(ys)) + (2 + self.depth) * duz
        fit = max(min_fit, min(100.0, 0.95 * area.w / w1, 0.96 * area.h / h1))

        (cx, cy), (rx, ry), uz, view = _axes(cam.alpha, cam.elev)
        self.L = fit * cam.zoom
        self.hw = self.L * 0.5  # kích thước tham chiếu cho các chi tiết nhỏ
        self.U = self.L * uz
        self._cx, self._cy, self._rx, self._ry = cx * self.L, cy * self.L, rx * self.L, ry * self.L
        mid_r, mid_c = rows / 2, cols / 2
        self.ox = area.centerx + cam.pan[0] - (mid_c * self._cx + mid_r * self._rx)
        self.oy = (
            area.centery + cam.pan[1] - (mid_c * self._cy + mid_r * self._ry)
            + (2 - self.depth) * self.U / 2  # chừa chỗ cho khối đứng cao phía trên
        )

        # Tia nhìn về phía camera theo (r, c, z): các điểm trên tia trùng một điểm màn hình.
        self.ca, self.sa = view[0], view[1]
        self.view = view
        # Ánh sáng gắn với camera: từ trước-trái-trên.
        f, g = (self.ca, self.sa), (-self.sa, self.ca)
        light = (0.5 * f[0] - 0.25 * g[0], 0.5 * f[1] - 0.25 * g[1], 0.8)
        m = math.sqrt(light[0] ** 2 + light[1] ** 2 + light[2] ** 2)
        self.light = (light[0] / m, light[1] / m, light[2] / m)

    def p(self, r: float, c: float, z: float = 0.0) -> Tuple[float, float]:
        return (
            self.ox + c * self._cx + r * self._rx,
            self.oy + c * self._cy + r * self._ry - z * self.U,
        )

    def order(self, r: float, c: float) -> float:
        """Khoá vẽ painter: nhỏ hơn = xa camera hơn = vẽ trước."""
        return r * self.ca + c * self.sa


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    m = math.sqrt(_dot(a, a)) or 1.0
    return (a[0] / m, a[1] / m, a[2] / m)


def piece_box(cells: Sequence[Cell]):
    rs = [c[0] for c in cells]
    cs = [c[1] for c in cells]
    return min(rs), min(cs), max(rs) + 1, max(cs) + 1


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max", "color", "size")

    def __init__(self, x, y, vx, vy, life, color, size):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.life = self.max = life
        self.color, self.size = color, size


class BoardRenderer:
    def __init__(self, level, area: Optional[pygame.Rect] = None, cam: Optional[Camera] = None,
                 min_fit: float = 24.0, arctic_theme: bool = False, theme_name: Optional[str] = None):
        self.level = level
        self.min_fit = min_fit  # cạnh ô nhỏ nhất cho phép (ảnh xem trước cần nhỏ hơn mặc định)
        self.problem = level.problem
        self.area = area or theme.BOARD_VIEW
        self.time = 0.0
        self.particles: List[Particle] = []
        self.start_cell = self.problem.initial_state.get_occupied_cells()[0]
        self._labels = {}
        self.swap_pop = 0.0  # >0 ngay sau khi đổi khối điều khiển, làm mũi tên phình to
        self.landing: Optional[dict] = None  # {"cells", "t"}: khối vừa hạ xuống, bị ép dẹt một thoáng
        self.glows: List[dict] = []  # vầng sáng quanh công tắc / cầu vừa đổi trạng thái
        # Tấm sàn fragile hiện đang rơi cùng block; không vẽ lại ở mặt bàn.
        self.falling_fragile_cells: set[Cell] = set()
        self._fxbuf: Optional[pygame.Surface] = None
        # Lớp bàn tĩnh (bóng + ô sàn + cầu + công tắc) vẽ sẵn một lần, dùng lại tới khi
        # góc nhìn, theme hay trạng thái cầu đổi; chỉ phần nhấp nháy được vẽ lại mỗi khung.
        self._cam_gen = 0
        self._static_key = None
        self._static_layer: Optional[pygame.Surface] = None

        if theme_name is not None:
            self._theme_name = str(theme_name).lower()
        elif arctic_theme:
            self._theme_name = "arctic"
        else:
            self._theme_name = "arctic"

        self.set_camera(cam or Camera())

        n_bridges = len(self.problem.bridge_indices)
        self.bridge_color = [theme.TEXT_DIM] * n_bridges
        self.bridge_cell = [None] * n_bridges
        self._update_bridge_colors()
        self.bridge_v = [1.0 if b else 0.0 for b in self.problem.initial_state.bridges_state]
        self.bridge_target = list(self.bridge_v)

    @property
    def theme_name(self) -> str:
        return self._theme_name

    @property
    def is_arctic(self) -> bool:
        return self._theme_name == "arctic"

    @property
    def is_desert(self) -> bool:
        return self._theme_name == "desert"

    @property
    def arctic_theme(self) -> bool:
        return self._theme_name == "arctic"

    @arctic_theme.setter
    def arctic_theme(self, val: bool) -> None:
        self.set_theme("arctic" if val else "desert")

    def _update_bridge_colors(self) -> None:
        if self.is_desert:
            palette = theme.DESERT_BRIDGE_COLORS
        elif self.is_arctic:
            palette = theme.ARCTIC_BRIDGE_COLORS
        else:
            palette = theme.BRIDGE_COLORS
        for cell, idx in self.problem.bridge_indices.items():
            g = self.level.bridge_group_of(cell)
            self.bridge_color[idx] = palette[g % len(palette)] if g >= 0 else theme.TEXT_DIM
            self.bridge_cell[idx] = cell

    def set_theme(self, name: str) -> None:
        """Đổi phong cách chủ đề trực quan (arctic hoặc desert)."""
        self._theme_name = (str(name).lower() if name else "arctic")
        self._update_bridge_colors()

    def set_arctic_theme(self, on: bool) -> None:
        """Tương thích ngược: chuyển đổi giữa theme Bắc Cực và Sa Mạc."""
        self.set_theme("arctic" if on else "desert")

    # ------------------------------------------------------------------ cập nhật
    def set_camera(self, cam: Camera) -> None:
        """Dựng lại phép chiếu và thứ tự vẽ khi góc nhìn đổi."""
        self.iso = Iso(self.level.rows, self.level.cols, self.area, cam, self.min_fit)
        self._cam_gen = getattr(self, "_cam_gen", 0) + 1
        self.tile_order = sorted(
            self.problem.grid, key=lambda rc: (self.iso.order(*rc), rc[0], rc[1])
        )

    def set_bridges(self, bridges_state: Sequence[bool], snap: bool = False) -> None:
        self.bridge_target = [1.0 if b else 0.0 for b in bridges_state]
        if snap:
            self.bridge_v = list(self.bridge_target)

    def update(self, dt: float) -> None:
        self.time += dt
        self.swap_pop = max(0.0, self.swap_pop - dt * 3.5)
        if self.landing is not None:
            self.landing["t"] += dt
            if self.landing["t"] >= LAND_DUR:
                self.landing = None
        for g in self.glows:
            g["t"] += dt
        self.glows = [g for g in self.glows if g["t"] < g["dur"]]
        for i, target in enumerate(self.bridge_target):
            cur = self.bridge_v[i]
            step = dt * 3.2
            self.bridge_v[i] = min(target, cur + step) if target > cur else max(target, cur - step)
        for pt in self.particles:
            pt.life -= dt
            pt.vy += 520 * dt
            pt.x += pt.vx * dt
            pt.y += pt.vy * dt
        self.particles = [pt for pt in self.particles if pt.life > 0]

    def burst(self, cell: Cell, n: int = 46, colors=None, z: float = 0.2) -> None:
        x, y = self.iso.p(cell[0] + 0.5, cell[1] + 0.5, z)
        if colors is None:
            if self.is_desert:
                colors = [(255, 215, 60), (255, 140, 50), (245, 80, 120), (80, 240, 210)]
            elif self.is_arctic:
                colors = [(255, 255, 255), (180, 235, 255), theme.ARCTIC_GOAL_RING, (215, 245, 255)]
            else:
                colors = [theme.ACCENT, theme.GOAL_RING, (255, 255, 255), theme.GOOD]
        for _ in range(n):
            ang = random.uniform(0, math.tau)
            sp = random.uniform(120, 460)
            self.particles.append(
                Particle(x, y, math.cos(ang) * sp, math.sin(ang) * sp * 0.7 - 260,
                         random.uniform(0.6, 1.3), random.choice(colors), random.randint(3, 7))
            )

    def land_on(self, cells: Sequence[Cell]) -> None:
        """Bắt đầu hiệu ứng ép dẹt cho khối vừa hạ xuống ``cells``."""
        self.landing = {"cells": tuple(cells), "t": 0.0}

    def start_fragile_fall(self, cell: Cell) -> None:
        """Tấm sàn nguyên khối sẽ được vẽ trong animation rơi, không còn ở mặt bàn."""
        self.falling_fragile_cells.add(cell)

    def clear_fragile_falls(self) -> None:
        """Phục hồi mặt bàn khi undo/restart hoặc khi đổi màn."""
        self.falling_fragile_cells.clear()

    def glow(self, cell: Cell, color, strength: float = 1.0, dur: float = 0.9) -> None:
        """Vầng sáng mềm lan ra từ ô ``cell`` (công tắc vừa kích hoạt, cầu vừa đổi, hố đích)."""
        self.glows.append({"cell": cell, "color": color, "t": 0.0, "dur": dur, "k": strength})
        # vài tia sáng bay lên, vẽ cùng lớp hạt (nằm trên khối nên vẫn thấy khi khối đứng lên công tắc)
        x, y = self.iso.p(cell[0] + 0.5, cell[1] + 0.5, 0.1)
        hi = tuple(int(v) for v in mix(color, (255, 255, 255), 0.55))
        for _ in range(int(10 * strength)):
            self.particles.append(
                Particle(x + random.uniform(-14, 14), y, random.uniform(-40, 40), random.uniform(-420, -240),
                         random.uniform(0.5, 0.9), random.choice((color, hi)), random.randint(2, 4))
            )

    def squash_at(self, cells: Sequence[Cell]) -> float:
        """Độ ép dẹt hiện tại (>0 dẹt, <0 giãn nhẹ khi nảy lại) của khối đang phủ ``cells``."""
        if self.landing is None or self.landing["cells"] != tuple(cells):
            return 0.0
        return squash_curve(self.landing["t"] / LAND_DUR)

    def draw_glows(self, surf) -> None:
        for g in self.glows:
            u = g["t"] / g["dur"]
            fade = (1 - u) ** 1.5 * g["k"]
            col = g["color"]
            # lõi sáng mờ dần + các vòng lan rộng
            for half, a in ((0.34, 190), (0.5, 120), (0.7, 64)):
                h = half * (0.7 + 0.8 * u)
                pts = [(int(x), int(y)) for x, y in self._diamond(g["cell"], h, 0.04)]
                gfx.filled_polygon(surf, pts, (*col, min(255, int(a * fade))))
            ring = 0.3 + 0.9 * smoothstep(u)
            pts = [(int(x), int(y)) for x, y in self._ring(g["cell"], ring, 20, 0.0, 0.05)]
            hi = tuple(int(v) for v in mix(col, (255, 255, 255), 0.5))
            gfx.aapolygon(surf, pts, (*hi, min(255, int(220 * fade))))
            gfx.aapolygon(surf, [(int(x), int(y)) for x, y in self._ring(g["cell"], ring * 0.82, 20, 0.0, 0.05)],
                          (*col, min(255, int(120 * fade))))

    def draw_particles(self, surf) -> None:
        for pt in self.particles:
            a = max(0, min(255, int(255 * pt.life / pt.max)))
            gfx.filled_circle(surf, int(pt.x), int(pt.y), pt.size, (*pt.color, a))

    # ------------------------------------------------------------------ ô sàn
    def _side_color(self, top, normal):
        lum = 0.50 + 0.66 * max(0.0, _dot(normal, self.iso.light))
        return shade(top, 0.82 * lum)

    def _prism(self, surf, r, c, top, dz=0.0, alpha=255, depth=None):
        """Ô sàn dạng lăng trụ: mặt trên + hai mặt bên quay về phía camera."""
        iso = self.iso
        p = iso.p
        d = iso.depth if depth is None else depth
        z0, z1 = dz, dz - d
        top_pts = [p(r, c, z0), p(r, c + 1, z0), p(r + 1, c + 1, z0), p(r + 1, c, z0)]
        if iso.ca >= 0:  # mặt phía r + 1 quay về camera
            rr, nr = r + 1, (1.0, 0.0, 0.0)
        else:
            rr, nr = r, (-1.0, 0.0, 0.0)
        if iso.sa >= 0:  # mặt phía c + 1 quay về camera
            cc, nc = c + 1, (0.0, 1.0, 0.0)
        else:
            cc, nc = c, (0.0, -1.0, 0.0)
        rf = [p(rr, c, z0), p(rr, c + 1, z0), p(rr, c + 1, z1), p(rr, c, z1)]
        cf = [p(r, cc, z0), p(r + 1, cc, z0), p(r + 1, cc, z1), p(r, cc, z1)]
        poly(surf, (*self._side_color(top, nr), alpha), rf)
        poly(surf, (*self._side_color(top, nc), alpha), cf)
        poly(surf, (*top, alpha), top_pts)
        edge = shade(top, 1.22)
        gfx.aapolygon(surf, [(int(x), int(y)) for x, y in top_pts], (*edge, int(alpha * 0.85)))

    def _diamond(self, cell, half, z=0.0, dr=0.0, dc=0.0):
        r, c = cell[0] + 0.5 + dr, cell[1] + 0.5 + dc
        p = self.iso.p
        return [p(r - half, c - half, z), p(r - half, c + half, z),
                p(r + half, c + half, z), p(r + half, c - half, z)]

    def _ring(self, cell, radius, n=8, rot=0.0, z=0.02):
        r, c = cell[0] + 0.5, cell[1] + 0.5
        p = self.iso.p
        return [
            p(r + radius * math.sin(rot + k * math.tau / n),
              c + radius * math.cos(rot + k * math.tau / n), z)
            for k in range(n)
        ]

    def _draw_floor(self, surf, cell, tile):
        r, c = cell
        checker = (r + c) % 2 == 0
        if self.is_desert:
            if tile == TileType.FRAGILE:
                top = theme.DESERT_FRAGILE_TOP if checker else theme.DESERT_FRAGILE_TOP_ALT
                self._prism(surf, r, c, top)
                self._draw_cracks(surf, cell)
                return
            top = theme.DESERT_FLOOR_TOP if checker else theme.DESERT_FLOOR_TOP_ALT
            if cell == self.start_cell:
                top = theme.DESERT_START_TOP
            self._prism(surf, r, c, top)
            if cell == self.start_cell:
                gfx.aapolygon(
                    surf, [(int(x), int(y)) for x, y in self._diamond(cell, 0.36)],
                    (*theme.shade(theme.DESERT_START_TOP, 1.4), 180),
                )
            return

        if self.is_arctic:
            if tile == TileType.FRAGILE:
                top = theme.ARCTIC_FRAGILE_TOP if checker else theme.ARCTIC_FRAGILE_TOP_ALT
                self._prism(surf, r, c, top)
                self._draw_cracks(surf, cell)
                return
            top = theme.ARCTIC_FLOOR_TOP if checker else theme.ARCTIC_FLOOR_TOP_ALT
            if cell == self.start_cell:
                top = theme.ARCTIC_START_TOP
            self._prism(surf, r, c, top)
            if cell == self.start_cell:
                gfx.aapolygon(
                    surf, [(int(x), int(y)) for x, y in self._diamond(cell, 0.36)],
                    (*theme.shade(theme.ARCTIC_START_TOP, 1.4), 180),
                )
            return

        if tile == TileType.FRAGILE:
            top = theme.FRAGILE_TOP if checker else theme.FRAGILE_TOP_ALT
            self._prism(surf, r, c, top)
            self._draw_cracks(surf, cell)
            return
        top = theme.FLOOR_TOP if checker else theme.FLOOR_TOP_ALT
        if cell == self.start_cell:
            top = theme.START_TOP
        self._prism(surf, r, c, top)
        if cell == self.start_cell:
            gfx.aapolygon(
                surf, [(int(x), int(y)) for x, y in self._diamond(cell, 0.36)],
                (*theme.shade(theme.START_TOP, 1.5), 170),
            )

    def _draw_cracks(self, surf, cell, dz=0.01):
        p = self.iso.p
        r, c = cell
        if self.is_desert:
            dark = (145, 65, 35)
        elif self.is_arctic:
            dark = (42, 105, 148)
        else:
            dark = (112, 56, 20)
        for pts in (
            [(0.18, 0.30), (0.40, 0.46), (0.36, 0.70), (0.58, 0.82)],
            [(0.40, 0.46), (0.66, 0.40), (0.84, 0.54)],
            [(0.62, 0.22), (0.58, 0.50)],
        ):
            polyline(surf, dark, [p(r + a, c + b, dz) for a, b in pts], 2)
            if self.is_arctic:
                polyline(surf, (255, 255, 255), [p(r + a + 0.01, c + b + 0.01, dz + 0.004) for a, b in pts], 1)
            elif self.is_desert:
                polyline(surf, (255, 220, 160), [p(r + a + 0.01, c + b + 0.01, dz + 0.004) for a, b in pts], 1)

    def draw_falling_fragile_tile(self, surf, cell: Cell, progress: float) -> None:
        """Vẽ tấm fragile còn nguyên vẹn khi nó tụt xuống bên dưới block."""
        r, c = cell
        if self.is_desert:
            top = theme.DESERT_FRAGILE_TOP if (r + c) % 2 == 0 else theme.DESERT_FRAGILE_TOP_ALT
        elif self.is_arctic:
            top = theme.ARCTIC_FRAGILE_TOP if (r + c) % 2 == 0 else theme.ARCTIC_FRAGILE_TOP_ALT
        else:
            top = theme.FRAGILE_TOP if (r + c) % 2 == 0 else theme.FRAGILE_TOP_ALT
        dz = -(progress ** 2) * 6.0
        alpha = max(0, min(255, int(255 * (1.0 - progress ** 1.4))))
        self._prism(surf, r, c, top, dz=dz, alpha=alpha)
        if alpha > 20:
            self._draw_cracks(surf, cell, dz=dz + 0.01)

    def _draw_goal(self, surf, cell):
        self._draw_floor(surf, cell, TileType.FLOOR)
        if self.is_desert:
            # Lỗ đích sa mạc TRÒN hoàn hảo (Oasis Portal / Sand Vortex tròn cho Cây Xương Rồng)
            poly(surf, (185, 115, 60), self._ring(cell, 0.45, n=24, z=0.015))
            rings = [
                (0.40, (38, 76, 92)),
                (0.32, (20, 52, 68)),
                (0.22, (12, 34, 48)),
                (0.12, (4, 16, 26)),
            ]
            for rad, col in rings:
                poly(surf, col, self._ring(cell, rad, n=24, z=0.018))
            return

        rings = (
            [(0.82, (26, 48, 82)), (0.68, (14, 32, 60)), (0.52, (8, 18, 40)), (0.34, (2, 6, 18))]
            if self.is_arctic
            else [(0.82, (46, 52, 74)), (0.68, (28, 32, 48)), (0.52, (14, 16, 26)), (0.34, (5, 6, 11))]
        )
        for size, col in rings:
            poly(surf, col, self._diamond(cell, size / 2, 0.015))

    def _draw_goal_pulse(self, surf, cell):
        """Các vòng sáng nhấp nháy quanh hố đích (vẽ lại mỗi khung, không nằm trong lớp tĩnh)."""
        pulse = 0.5 + 0.5 * math.sin(self.time * 3.0)
        if self.is_desert:
            for grow, a in ((0.0, 220), (0.05, 130), (0.10, 65)):
                r_pts = self._ring(cell, 0.38 + grow * (0.08 + 0.04 * pulse), n=24, rot=self.time * 0.8, z=0.022)
                gfx.aapolygon(
                    surf,
                    [(int(x), int(y)) for x, y in r_pts],
                    (*theme.DESERT_GOAL_RING, int(a * (0.6 + 0.4 * pulse))),
                )
            return

        ring_col = theme.ARCTIC_GOAL_RING if self.is_arctic else theme.GOAL_RING
        for grow, a in ((0.0, 210), (0.05, 120), (0.10, 60)):
            gfx.aapolygon(
                surf,
                [(int(x), int(y)) for x, y in self._diamond(cell, 0.41 + grow * (0.6 + pulse), 0.02)],
                (*ring_col, int(a * (0.55 + 0.45 * pulse))),
            )

    def _draw_bridge(self, surf, cell):
        idx = self.problem.bridge_indices[cell]
        v = self.bridge_v[idx]
        col = self.bridge_color[idx]
        r, c = cell
        if v < 0.98:
            if self.is_desert:
                ghost_col = (255, 195, 120)
            elif self.is_arctic:
                ghost_col = (130, 220, 255)
            else:
                ghost_col = col
            ghost = [(int(x), int(y)) for x, y in self._diamond(cell, 0.5, 0.0)]
            gfx.filled_polygon(surf, ghost, (*ghost_col, int(34 * (1 - v))))
            gfx.aapolygon(surf, ghost, (*ghost_col, int(170 * (1 - v) + 30)))
            inner = [(int(x), int(y)) for x, y in self._diamond(cell, 0.26, 0.0)]
            gfx.aapolygon(surf, inner, (*ghost_col, int(90 * (1 - v))))
        if v > 0.03:
            if self.arctic_theme:
                # Cầu gỗ Bắc Cực: ván gỗ màu nâu ấm áp
                checker = (r + c) % 2 == 0
                wood_top = theme.ARCTIC_WOOD_TOP if checker else theme.ARCTIC_WOOD_TOP_ALT
                top = mix(wood_top, col, 0.25)
                self._prism(surf, r, c, top, dz=-(1 - v) * 0.6, alpha=int(255 * v))
                if v > 0.6:
                    a = int(220 * v)
                    p = self.iso.p
                    # Các thanh ván gỗ ngang và đinh tán ở hai đầu
                    for off in (0.28, 0.5, 0.72):
                        p1 = p(r + off, c + 0.08, 0.012)
                        p2 = p(r + off, c + 0.92, 0.012)
                        pygame.draw.line(surf, (64, 40, 20), (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])), 2)
                        gfx.filled_circle(surf, int(p1[0]), int(p1[1]), 2, (185, 145, 90, a))
                        gfx.filled_circle(surf, int(p2[0]), int(p2[1]), 2, (185, 145, 90, a))
            else:
                top = mix(theme.FLOOR_TOP, col, 0.62)
                self._prism(surf, r, c, top, dz=-(1 - v) * 0.6, alpha=int(255 * v))
                if v > 0.6:
                    a = int(200 * v)
                    for off in (0.28, 0.5, 0.72):
                        p = self.iso.p
                        gfx.line(
                            surf, *map(int, p(r + off, c + 0.16, 0.012)), *map(int, p(r + off, c + 0.84, 0.012)),
                            (*shade(col, 1.25), a),
                        )

    # ------------------------------------------------------------------ công tắc
    def _draw_switch(self, surf, cell, sw):
        if sw.linked_bridges:
            idx = self.problem.bridge_indices[sw.linked_bridges[0]]
            col = self.bridge_color[idx]
        else:
            col = theme.SPLIT_COLOR

        if self.arctic_theme:
            # Màu đá quý rực rỡ nổi bật trên nền tuyết trắng
            if sw.switch_type == SwitchType.SOFT:
                col = (255, 65, 105)  # Ruby đỏ
            elif sw.switch_type == SwitchType.HEAVY:
                col = (255, 190, 35)  # Hổ phách vàng
            else:
                col = (195, 105, 255)  # Thạch anh tím
        else:
            if sw.switch_type == SwitchType.SOFT:
                col = (235, 65, 85)

        p = self.iso.p
        cr, cc = cell[0] + 0.5, cell[1] + 0.5
        if sw.switch_type == SwitchType.SOFT:
            if sw.is_permanent:
                # Công tắc tròn đỏ Dạng Permanent (một chiều): hình tròn rỗng màu đỏ
                n = 24
                out_b = self._ring(cell, 0.36, n=n, z=0.010)
                in_b = self._ring(cell, 0.18, n=n, z=0.010)
                out_t = self._ring(cell, 0.33, n=n, z=0.035)
                in_t = self._ring(cell, 0.21, n=n, z=0.035)

                col_rim_out = shade(col, 0.45)
                col_rim_in = shade(col, 0.35)
                for k in range(n):
                    kn = (k + 1) % n
                    poly(surf, col_rim_out, [out_b[k], out_b[kn], out_t[kn], out_t[k]])
                    poly(surf, col_rim_in, [in_t[k], in_t[kn], in_b[kn], in_b[k]])

                for k in range(n):
                    kn = (k + 1) % n
                    poly(surf, col, [out_t[k], out_t[kn], in_t[kn], in_t[k]])

                ipts_out = [(int(round(x)), int(round(y))) for x, y in out_t]
                ipts_in = [(int(round(x)), int(round(y))) for x, y in in_t]
                gfx.aapolygon(surf, ipts_out, shade(col, 1.40))
                gfx.aapolygon(surf, ipts_in, shade(col, 0.80))
            else:
                # Công tắc tròn đỏ Dạng Toggle (hai chiều): hình tròn đặc
                poly(surf, shade(col, 0.55), self._ring(cell, 0.34, 8, math.pi / 8, 0.012))
                poly(surf, col, self._ring(cell, 0.26, 8, math.pi / 8, 0.03))
                poly(surf, shade(col, 1.25), self._ring(cell, 0.14, 8, math.pi / 8, 0.05))
        elif sw.switch_type == SwitchType.HEAVY:
            poly(surf, (26, 30, 44), self._ring(cell, 0.40, 4, math.pi / 4, 0.012), shade(col, 0.8))
            for a, b in (((-0.2, -0.2), (0.2, 0.2)), ((-0.2, 0.2), (0.2, -0.2))):
                pa, pb = p(cr + a[0], cc + a[1], 0.03), p(cr + b[0], cc + b[1], 0.03)
                pygame.draw.line(surf, col, pa, pb, 6)
                pygame.draw.aaline(surf, shade(col, 1.3), pa, pb)
        else:  # SPLIT
            poly(surf, (26, 30, 44), self._ring(cell, 0.40, 4, math.pi / 4, 0.012), shade(col, 0.8))
            for sign in (-1, 1):
                pts = [
                    p(cr + 0.27 * math.sin(a), cc + sign * (0.15 + 0.10 * math.cos(a)), 0.03)
                    for a in [i * math.pi / 14 - math.pi / 3 for i in range(9)]
                ]
                polyline(surf, col, pts, 5)
            gfx.filled_circle(surf, *map(int, p(cr, cc, 0.03)), max(3, int(self.iso.hw * 0.07)), col)

    def _draw_split_hint(self, surf, targets):
        pulse = 0.5 + 0.5 * math.sin(self.time * 3.2)
        for i, cell in enumerate(targets):
            pts = [(int(x), int(y)) for x, y in self._diamond(cell, 0.34 + 0.05 * pulse, 0.02)]
            gfx.aapolygon(surf, pts, (*theme.SPLIT_COLOR, int(90 + 110 * pulse)))
            gfx.filled_polygon(surf, pts, (*theme.SPLIT_COLOR, 26))

    # ------------------------------------------------------------------ vẽ bàn
    def draw_board(
        self,
        surf,
        show_hints: bool = True,
        min_order: Optional[float] = None,
        max_order: Optional[float] = None,
        force_include_cells: Optional[set] = None,
        exclude_cells: Optional[set] = None,
        background: Optional[pygame.Surface] = None,
    ) -> None:
        """Vẽ bàn cờ.

        Với ``background`` (ảnh nền cùng cỡ ``surf``), lần vẽ đầy đủ dùng một lớp tĩnh
        "nền + bóng + ô sàn" dựng sẵn: dán cả lớp lên ``surf`` thay cho việc tự dán nền,
        rồi chỉ vẽ lại phần nhấp nháy. Lớp được dựng lại khi góc nhìn, theme, trạng thái
        cầu hoặc nền đổi; trong lúc cầu đang chuyển động thì vẽ đầy đủ như cũ.
        """
        plain = (
            min_order is None and max_order is None and not force_include_cells
            and not exclude_cells and not self.falling_fragile_cells
        )
        if background is not None and not (plain and background.get_size() == surf.get_size()):
            surf.blit(background, (0, 0))
            background = None
        if background is not None and all(v in (0.0, 1.0) for v in self.bridge_v):
            surf.blit(self._get_static_layer(background), (0, 0))
            if self.problem.goal_pos in self.problem.grid:
                self._draw_goal_pulse(surf, self.problem.goal_pos)
        else:
            if background is not None:
                surf.blit(background, (0, 0))
            self._draw_tiles(surf, min_order, max_order, force_include_cells, exclude_cells, pulse=True)
        if show_hints and min_order is None:
            for sw in self.problem.switches.values():
                if sw.split_targets:
                    self._draw_split_hint(surf, sw.split_targets)

    def _get_static_layer(self, background: pygame.Surface) -> pygame.Surface:
        key = (self._cam_gen, self._theme_name, tuple(self.bridge_v), id(background), background.get_size())
        if key != self._static_key or self._static_layer is None:
            layer = background.copy()  # vẽ lên nền đục để pha màu bóng / viền khử răng cưa y như vẽ trực tiếp
            self._draw_tiles(layer, None, None, None, None, pulse=False)
            self._static_layer = layer
            self._static_key = key
        return self._static_layer

    def _draw_tiles(self, surf, min_order, max_order, force_include_cells, exclude_cells, pulse: bool) -> None:
        grid = self.problem.grid
        # Bóng đổ nhẹ phía dưới bàn: chỉ vẽ ở pass đầu (khi min_order is None)
        if min_order is None:
            for cell in self.tile_order:
                if cell in self.falling_fragile_cells:
                    continue
                if grid[cell] == TileType.BRIDGE and self.bridge_v[self.problem.bridge_indices[cell]] < 0.5:
                    continue
                gfx.filled_polygon(
                    surf,
                    [(int(x), int(y)) for x, y in self._diamond(cell, 0.62, -self.iso.depth - 0.55, 0.08, 0.08)],
                    (0, 0, 0, 38),
                )
        for cell in self.tile_order:
            if cell in self.falling_fragile_cells:
                continue
            if exclude_cells is not None and cell in exclude_cells:
                continue
            ord_val = self.iso.order(*cell)
            is_forced = force_include_cells is not None and cell in force_include_cells
            if not is_forced and max_order is not None and ord_val > max_order:
                continue
            if min_order is not None and ord_val <= min_order:
                continue
            tile = grid[cell]
            if tile == TileType.BRIDGE:
                self._draw_bridge(surf, cell)
            elif tile == TileType.GOAL:
                self._draw_goal(surf, cell)
                if pulse:
                    self._draw_goal_pulse(surf, cell)
            else:
                self._draw_floor(surf, cell, tile)
            sw = self.problem.switches.get(cell)
            if sw is not None:
                self._draw_switch(surf, cell, sw)

    def draw_direction_hints(self, surf, cells: Sequence[Cell], flash=None) -> None:
        """Mũi tên dẹt trên sàn quanh khối đang điều khiển: chỉ bốn hướng có thể lăn.

        ``flash`` là dict {"U"/"D"/"L"/"R": 0..1} để làm sáng hướng vừa bấm.
        """
        r0, c0, r1, c1 = piece_box(cells)
        mr, mc = (r0 + r1) / 2, (c0 + c1) / 2
        half_r, half_c = (r1 - r0) / 2, (c1 - c0) / 2
        pulse = 0.5 + 0.5 * math.sin(self.time * 4.0)
        p = self.iso.p
        for key, (dr, dc) in (("U", (-1, 0)), ("D", (1, 0)), ("L", (0, -1)), ("R", (0, 1))):
            cr = mr + dr * (half_r + 0.5)
            cc = mc + dc * (half_c + 0.5)
            pr, pc = dc, dr  # vuông góc với hướng lăn
            tip = (cr + dr * 0.34, cc + dc * 0.34)
            base = (cr - dr * 0.16, cc - dc * 0.16)
            notch = (cr - dr * 0.02, cc - dc * 0.02)
            left = (base[0] + pr * 0.26, base[1] + pc * 0.26)
            right = (base[0] - pr * 0.26, base[1] - pc * 0.26)
            hot = (flash or {}).get(key, 0.0)
            a = int(86 + 52 * pulse + 110 * hot)
            col = theme.mix(theme.ACCENT, (255, 255, 255), hot * 0.6)
            pts = [p(*tip, 0.03), p(*left, 0.03), p(*notch, 0.03), p(*right, 0.03)]
            ipts = [(int(x), int(y)) for x, y in pts]
            gfx.filled_polygon(surf, ipts, (*col, min(255, a)))
            gfx.aapolygon(surf, ipts, (*col, min(255, a + 60)))

    def screen_dir(self, key: str) -> Tuple[float, float]:
        """Vector đơn vị trên màn hình của một hướng lăn (U/D/L/R)."""
        iso = self.iso
        vx, vy = {
            "U": (-iso._rx, -iso._ry), "D": (iso._rx, iso._ry),
            "L": (-iso._cx, -iso._cy), "R": (iso._cx, iso._cy),
        }[key]
        m = math.hypot(vx, vy) or 1.0
        return vx / m, vy / m

    def _label(self, text: str, size: int, color):
        key = (text, size, tuple(color))
        img = self._labels.get(key)
        if img is None:
            img = theme.font(size, True).render(text, True, color)
            self._labels[key] = img
        return img

    def draw_link_lines(self, surf, segments) -> None:
        """Đường nét đứt chạy từ công tắc tới cầu / ô đích mà nó điều khiển (nét đứt "chảy" về phía đích).

        Đầu mút: chấm đặc = mở cầu, dấu x = đóng cầu, vòng tròn = đảo trạng thái, hình thoi = điểm tách khối.
        """
        iso = self.iso
        dash, gap = 12.0, 10.0
        shift = (self.time * 38.0) % (dash + gap)
        for s in segments:
            col = theme.SPLIT_COLOR if s.group < 0 else theme.BRIDGE_COLORS[s.group % len(theme.BRIDGE_COLORS)]
            ax, ay = iso.p(s.source[0] + 0.5, s.source[1] + 0.5, 0.06)
            bx, by = iso.p(s.target[0], s.target[1], 0.06)
            length = math.hypot(bx - ax, by - ay)
            if length < 2:
                continue
            ux, uy = (bx - ax) / length, (by - ay) / length
            pos = -(dash + gap) + shift
            while pos < length:
                s0, s1 = max(0.0, pos), min(length, pos + dash)
                if s1 > s0:
                    pygame.draw.line(
                        surf, col, (ax + ux * s0, ay + uy * s0), (ax + ux * s1, ay + uy * s1), 3
                    )
                pos += dash + gap
            pygame.draw.circle(surf, col, (int(ax), int(ay)), 4)
            end = (int(bx), int(by))
            if s.kind == "open":
                pygame.draw.circle(surf, col, end, 7)
            elif s.kind == "toggle":
                pygame.draw.circle(surf, col, end, 8, 3)
            elif s.kind == "close":
                for sx, sy in ((1, 1), (1, -1)):
                    pygame.draw.line(surf, col, (end[0] - 7 * sx, end[1] - 7 * sy), (end[0] + 7 * sx, end[1] + 7 * sy), 4)
            else:  # split
                pygame.draw.polygon(surf, col, [(end[0], end[1] - 8), (end[0] + 8, end[1]), (end[0], end[1] + 8), (end[0] - 8, end[1])])
    def draw_path(self, surf, steps, done: Optional[int] = None, palette=None) -> None:
        """Lớp phủ đường đi của lời giải: ô nào khối đáp xuống, đánh số theo thứ tự.

        ``done`` là số hành động đã chạy trong replay (các bước đã qua sáng hơn);
        ``None`` nghĩa là không đang replay, vẽ tất cả ở độ sáng vừa.

        Cơ chế hàng đợi số bước (tránh đè số):
        - Ô nào số bị đè nhau thì chỉ hiển thị số bé hơn (bước sớm nhất chưa hoàn thành).
        - Khi đã đi qua ô đó rồi (bước <= done), số tiếp theo mới hiện lên (như hàng đợi).
        """
        if not steps:
            return
        iso = self.iso
        last = max((s["step"] for s in steps), default=1)
        size = max(11, int(iso.L * 0.24))

        # 1. Vẽ các ô sàn (diamonds): tập hợp bước active cho từng ô để không bị chồng chéo màu
        cell_steps: Dict[Tuple[int, int], List[dict]] = {}
        for s in steps:
            for cell in s["cells"]:
                cell_steps.setdefault(cell, []).append(s)

        for cell, c_steps in cell_steps.items():
            if done is not None:
                active_s = next((s for s in c_steps if s["step"] > done), c_steps[-1])
            else:
                active_s = c_steps[0]

            t = (active_s["step"] - 1) / max(1, last - 1)
            col = mix(*(palette or (theme.INFO, theme.ACCENT)), t)
            reached = done is None or active_s["step"] <= done
            fill, line = (84 if done is None else 120, 200) if reached else (34, 96)

            pts = [(int(x), int(y)) for x, y in self._diamond(cell, 0.41, 0.025)]
            gfx.filled_polygon(surf, pts, (*col, fill))
            gfx.aapolygon(surf, pts, (*col, line))

        # 2. Vẽ nhãn số bước (labels) theo cơ chế hàng đợi
        label_steps: Dict[Tuple[int, int], List[dict]] = {}
        for s in steps:
            label_steps.setdefault(s["cells"][0], []).append(s)

        for cell, l_steps in label_steps.items():
            if done is not None:
                active_s = next((s for s in l_steps if s["step"] > done), l_steps[-1])
            else:
                active_s = l_steps[0]

            t = (active_s["step"] - 1) / max(1, last - 1)
            col = mix(*(palette or (theme.INFO, theme.ACCENT)), t)
            reached = done is None or active_s["step"] <= done

            r, c = cell
            x, y = iso.p(r + 0.5, c + 0.5, 0.04)
            img = self._label(str(active_s["step"]), size, col if reached else theme.TEXT_DIM)
            surf.blit(img, img.get_rect(center=(int(x), int(y))))

    def draw_ghost_step(self, surf, next_state, action: Optional[str] = None, current_state: Optional[State] = None) -> None:
        """Vẽ cái bóng của bước đi tiếp theo kèm hướng đi và nút bấm WASD."""
        is_desert = self.is_desert
        ghost_color = (255, 185, 75) if is_desert else (80, 225, 255)
        ghost_border = (255, 225, 140) if is_desert else (180, 245, 255)
        key_border = (255, 205, 95) if is_desert else (100, 230, 255)

        pulse = 0.5 + 0.5 * math.sin(self.time * 5.0)
        deltas = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}

        # Xác định vị trí đích và các khối ghost cần vẽ (xử lý chuẩn xác cả khi SPLIT)
        ghost_footprints = []
        ghost_pcs = []
        p_next_r, p_next_c, p_next_h = 0.0, 0.0, 1.0

        if current_state is not None:
            if current_state.is_split:
                idx = current_state.active_block
                cur_cells = (current_state.get_occupied_cells()[idx],)
                cur_h = 1.0
                if action == "SWITCH":
                    tgt_cell = current_state.get_occupied_cells()[1 - idx]
                    ghost_footprints = [tgt_cell]
                    p_next_r, p_next_c, p_next_h = tgt_cell[0] + 0.5, tgt_cell[1] + 0.5, 0.5
                elif next_state.is_split:
                    dr, dc = deltas.get(action, (0, 0))
                    dest_cell = (cur_cells[0][0] + dr, cur_cells[0][1] + dc)
                    ghost_footprints = [dest_cell]
                    ghost_pcs = [{"cells": [dest_cell], "kind": "cube", "height": 1.0}]
                    p_next_r, p_next_c, p_next_h = dest_cell[0] + 0.5, dest_cell[1] + 0.5, 0.5
                else:
                    # Hợp nhất (merge) thành 1 khối
                    nxt_cells = next_state.get_occupied_cells()
                    nxt_h = 2.0 if next_state.orientation == Orientation.STANDING else 1.0
                    ghost_footprints = list(nxt_cells)
                    ghost_pcs = [{"cells": list(nxt_cells), "kind": "block", "height": nxt_h}]
                    p_next_r = sum(r for r, c in nxt_cells) / len(nxt_cells) + 0.5
                    p_next_c = sum(c for r, c in nxt_cells) / len(nxt_cells) + 0.5
                    p_next_h = nxt_h * 0.5
            else:
                cur_cells = current_state.get_occupied_cells()
                cur_h = 2.0 if current_state.orientation == Orientation.STANDING else 1.0
                if next_state.is_split:
                    ghost_pcs = pieces_of(next_state)
                    ghost_footprints = list(next_state.get_occupied_cells())
                    act_cell = next_state.get_occupied_cells()[next_state.active_block]
                    p_next_r, p_next_c, p_next_h = act_cell[0] + 0.5, act_cell[1] + 0.5, 0.5
                else:
                    ghost_pcs = pieces_of(next_state)
                    ghost_footprints = list(next_state.get_occupied_cells())
                    nxt_cells = next_state.get_occupied_cells()
                    nxt_h = 2.0 if next_state.orientation == Orientation.STANDING else 1.0
                    p_next_r = sum(r for r, c in nxt_cells) / len(nxt_cells) + 0.5
                    p_next_c = sum(c for r, c in nxt_cells) / len(nxt_cells) + 0.5
                    p_next_h = nxt_h * 0.5
        else:
            cur_cells = next_state.get_occupied_cells()
            cur_h = 2.0 if next_state.orientation == Orientation.STANDING else 1.0
            ghost_pcs = pieces_of(next_state)
            ghost_footprints = list(next_state.get_occupied_cells())
            p_next_r = sum(r for r, c in cur_cells) / len(cur_cells) + 0.5
            p_next_c = sum(c for r, c in cur_cells) / len(cur_cells) + 0.5
            p_next_h = cur_h * 0.5

        # 1. Vẽ dấu sàn (floor footprint) nơi khối sẽ đáp xuống
        for cell in ghost_footprints:
            pts = [(int(x), int(y)) for x, y in self._diamond(cell, 0.44, 0.02)]
            gfx.filled_polygon(surf, pts, (*ghost_color, int(45 + 35 * pulse)))
            gfx.aapolygon(surf, pts, (*ghost_border, int(160 + 80 * pulse)))
            pts_ring = [(int(x), int(y)) for x, y in self._diamond(cell, 0.48 + 0.02 * pulse, 0.02)]
            gfx.aapolygon(surf, pts_ring, (*ghost_color, int(70 + 40 * pulse)))

        # 2. Vẽ khối bóng 3D mờ (Ghost Block)
        ghost_alpha = 0.36 + 0.12 * pulse
        for pc in ghost_pcs:
            self.draw_piece(
                surf,
                pc["cells"],
                pc["kind"],
                pc["height"],
                alpha=ghost_alpha,
                color=ghost_color,
                shadow=True,
                draw_penguin=False,
            )

        # 3. Tính tọa độ màn hình
        p_next = self.iso.p(p_next_r, p_next_c, p_next_h)

        p_curr = None
        if current_state is not None:
            r_c = sum(r for r, c in cur_cells) / len(cur_cells) + 0.5
            c_c = sum(c for r, c in cur_cells) / len(cur_cells) + 0.5
            p_curr = self.iso.p(r_c, c_c, cur_h * 0.5)

        # 4. Mũi tên chỉ hướng lăn
        if p_curr is not None:
            dx = p_next[0] - p_curr[0]
            dy = p_next[1] - p_curr[1]
            dist = math.hypot(dx, dy)
            if dist > 14:
                ux, uy = dx / dist, dy / dist
                px_norm, py_norm = -uy, ux
                p_start = (p_curr[0] + dx * 0.26, p_curr[1] + dy * 0.26)
                p_end = (p_next[0] - dx * 0.20, p_next[1] - dy * 0.20)
                # Đường nét phát sáng
                pygame.draw.line(surf, (*ghost_color, 220), (int(p_start[0]), int(p_start[1])), (int(p_end[0]), int(p_end[1])), 4)
                # Đầu mũi tên nhọn
                arrow_pts = [
                    (int(p_end[0] + ux * 8), int(p_end[1] + uy * 8)),
                    (int(p_end[0] - ux * 10 + px_norm * 8), int(p_end[1] - uy * 10 + py_norm * 8)),
                    (int(p_end[0] - ux * 10 - px_norm * 8), int(p_end[1] - uy * 10 - py_norm * 8)),
                ]
                gfx.filled_polygon(surf, arrow_pts, (*ghost_border, 240))
                gfx.aapolygon(surf, arrow_pts, (255, 255, 255, 255))

        # 5. Floating Key Badge (Nút WASD)
        if action:
            key_map = {"U": "W", "D": "S", "L": "A", "R": "D", "SWITCH": "SPACE"}
            dir_names = {"U": "UP", "D": "DOWN", "L": "LEFT", "R": "RIGHT", "SWITCH": "SWITCH"}
            is_switch = action == "SWITCH"
            key_text = key_map.get(action, "?")
            sub_text = dir_names.get(action, "")

            if p_curr is not None:
                bx = (p_curr[0] + p_next[0]) / 2.0
                by = min(p_curr[1], p_next[1]) - 36
            else:
                bx = p_next[0]
                by = p_next[1] - 46

            bw = 92 if is_switch else 54
            bh = 46 if is_switch else 50
            badge_r = pygame.Rect(0, 0, bw, bh)
            badge_r.center = (int(bx), int(by))

            # Bóng đổ của phím
            sh_r = pygame.Rect(badge_r.x, badge_r.y + 4, bw, bh)
            rrect(surf, sh_r, (0, 0, 0, 160), radius=10)

            # Thân phím (Key cap)
            key_bg = (34, 18, 28, 248) if is_desert else (16, 26, 44, 248)
            rrect(surf, badge_r, key_bg, radius=10, border=key_border, border_w=2)

            # Highlight mép trên phím
            pygame.draw.line(surf, (255, 255, 255, 180), (badge_r.x + 6, badge_r.y + 2), (badge_r.right - 6, badge_r.y + 2), 1)

            # Chữ phím (W, A, S, D, SPACE)
            font_sz = 16 if is_switch else 24
            draw_text(surf, key_text, theme.font(font_sz, True), (255, 255, 255), (badge_r.centerx, badge_r.y + (16 if sub_text else 22)), "center")
            if sub_text:
                draw_text(surf, sub_text, theme.font(11, True), key_border, (badge_r.centerx, badge_r.bottom - 10), "center")

            # Chỉ một vệt leader line mờ nối xuống tâm cái bóng
            pygame.draw.line(surf, (*key_border, 110), (badge_r.centerx, badge_r.bottom + 2), (int(p_next[0]), int(p_next[1] - 10)), 1)
    # ------------------------------------------------------------------ khối

    def draw_floor_ring(self, surf, cell, color, strength=1.0):
        pulse = 0.5 + 0.5 * math.sin(self.time * 5.0)
        pts = [(int(x), int(y)) for x, y in self._diamond(cell, 0.5 + 0.02 * pulse, 0.03)]
        gfx.filled_polygon(surf, pts, (*color, int(46 * strength)))
        gfx.aapolygon(surf, pts, (*color, min(255, int((140 + 115 * pulse) * strength))))
        for half, a in ((0.46, 120), (0.42, 70)):
            pts2 = [(int(x), int(y)) for x, y in self._diamond(cell, half, 0.03)]
            gfx.aapolygon(surf, pts2, (*color, int(a * strength)))

    def draw_piece(
        self,
        surf,
        cells: Sequence[Cell],
        kind: str,
        height: float,
        *,
        roll: Optional[Tuple] = None,
        frame: Optional[Frame3D] = None,
        dz: float = 0.0,
        dr_offset: float = 0.0,
        dc_offset: float = 0.0,
        alpha: float = 1.0,
        active: bool = True,
        color=None,
        scale: float = 1.0,
        shadow: bool = True,
        draw_penguin: bool = True,
    ) -> None:
        """Vẽ một khối 3D phủ ``cells`` cao ``height`` (đơn vị ô).

        ``roll = (hướng, theta)`` hoặc ``(hướng, theta, pivot)`` xoay khối quanh cạnh trục quay.
        ``frame = (head, front, right)`` xác định hướng 3D của chim cánh cụt bên trong.
        """
        r0, c0, r1, c1 = box = piece_box(cells)
        if roll is None and dz == 0.0 and dr_offset == 0.0 and dc_offset == 0.0:
            sq = self.squash_at(cells)  # vừa hạ xuống: ép dẹt rồi nảy lại
            if sq:
                height *= 1.0 - sq
                scale *= 1.0 + 0.5 * sq
        if scale != 1.0:
            mr, mc = (r0 + r1) / 2, (c0 + c1) / 2
            vr0, vr1 = mr + (r0 - mr) * scale, mr + (r1 - mr) * scale
            vc0, vc1 = mc + (c0 - mc) * scale, mc + (c1 - mc) * scale
        else:
            vr0, vr1, vc0, vc1 = r0, r1, c0, c1
        verts = [
            (vr0, vc0, 0.0), (vr0, vc1, 0.0), (vr1, vc1, 0.0), (vr1, vc0, 0.0),
            (vr0, vc0, height), (vr0, vc1, height), (vr1, vc1, height), (vr1, vc0, height),
        ]
        if roll is not None:
            verts = self._rotate(verts, box, *roll)
        verts = [(r + dr_offset, c + dc_offset, z + dz) for r, c, z in verts]

        cube = kind != "block"
        if color is not None:
            base = color
        elif not cube:
            base = theme.BLOCK
        else:
            base = theme.CUBE_ACTIVE if active else theme.CUBE_INACTIVE
        a255 = max(0, min(255, int(255 * alpha * (0.86 if (cube and not active and color is None) else 1.0))))
        if a255 <= 0:
            return

        # Bóng trên sàn
        rs = [v[0] for v in verts]
        cs = [v[1] for v in verts]
        zmin = min(v[2] for v in verts)
        sh_alpha = int(88 * alpha * max(0.0, min(1.0, 1 + zmin / 3.0)))
        if shadow and sh_alpha > 4:
            if self.is_desert:
                # Bóng tròn / oval mềm mại trên cát dưới chân cây xương rồng
                sh_cr = (min(rs) + max(rs)) / 2.0
                sh_cc = (min(cs) + max(cs)) / 2.0
                sh_rad_r = max(0.2, (max(rs) - min(rs)) / 2.0 * 0.95)
                sh_rad_c = max(0.2, (max(cs) - min(cs)) / 2.0 * 0.95)
                sh_pts = [
                    self.iso.p(sh_cr + sh_rad_r * math.cos(t), sh_cc + sh_rad_c * math.sin(t), 0.0)
                    for t in [k * math.tau / 16 for k in range(16)]
                ]
                gfx.filled_polygon(surf, [(int(x), int(y)) for x, y in sh_pts], (0, 0, 0, sh_alpha))
            else:
                p = self.iso.p
                gfx.filled_polygon(
                    surf,
                    [(int(x), int(y)) for x, y in (
                        p(min(rs), min(cs), 0.0), p(min(rs), max(cs), 0.0),
                        p(max(rs), max(cs), 0.0), p(max(rs), min(cs), 0.0))],
                    (0, 0, 0, sh_alpha),
                )

        # ----------------- VẼ CÂY XƯƠNG RỒNG (DESERT THEME) -----------------
        if self.is_desert and draw_penguin:
            # Vẽ trực tiếp nhân vật Cây Xương Rồng (KHÔNG có khối chữ nhật bao quanh)
            is_cube = kind != "block"
            orig_h = 1.0 if is_cube or len(cells) > 1 or kind != "block" else 2.0
            h_ratio = max(0.0, height / orig_h)
            p_scale = scale * min(1.0, h_ratio)
            if p_scale > 0.01:
                p_verts, p_faces, p_colors = get_cactus_mesh(is_cube=is_cube)
                if frame is None:
                    if is_cube or len(cells) == 1:
                        actual_frame = INITIAL_FRAME
                    else:
                        c_list = list(cells)
                        if c_list[0][0] != c_list[1][0]:
                            actual_frame = ((1, 0, 0), (0, 0, -1), (0, 1, 0))  # Dọc theo R
                        else:
                            actual_frame = ((0, 1, 0), (1, 0, 0), (0, 0, -1))  # Dọc theo C
                else:
                    actual_frame = frame

                head_vec, front_vec, right_vec = actual_frame
                box_cx = (r0 + r1) / 2.0
                box_cy = (c0 + c1) / 2.0
                box_cz = height / 2.0

                abs_pverts = []
                for vr, vc, vz in p_verts:
                    pr = box_cx + (vr * front_vec[0] + vc * right_vec[0] + vz * head_vec[0]) * p_scale
                    pc = box_cy + (vr * front_vec[1] + vc * right_vec[1] + vz * head_vec[1]) * p_scale
                    pz = box_cz + (vr * front_vec[2] + vc * right_vec[2] + vz * head_vec[2]) * p_scale
                    abs_pverts.append((pr, pc, pz))

                if roll is not None:
                    abs_pverts = self._rotate(abs_pverts, box, *roll)
                abs_pverts = [(r + dr_offset, c + dc_offset, z + dz) for r, c, z in abs_pverts]

                p_faces_to_draw = []
                for f_idx, f in enumerate(p_faces):
                    q = [abs_pverts[i] for i in f]
                    if len(q) < 3:
                        continue
                    n = _norm(_cross(_sub(q[1], q[0]), _sub(q[2], q[0])))
                    fc = (sum(v[0] for v in q) / len(q), sum(v[1] for v in q) / len(q), sum(v[2] for v in q) / len(q))
                    if _dot(n, self.iso.view) <= 1e-6:
                        continue
                    p_faces_to_draw.append((_dot(fc, self.iso.view), q, n, p_colors[f_idx]))

                p_faces_to_draw.sort(key=lambda item: item[0])
                for _, q, n, fcol in p_faces_to_draw:
                    lum = 0.52 + 0.62 * max(0.0, _dot(n, self.iso.light))
                    if color is not None and fcol == (245, 82, 130):
                        fcol = color
                    col = shade(fcol, lum)
                    pts = [self.iso.p(*v) for v in q]
                    poly(surf, (*col, a255), pts)
                    gfx.aapolygon(surf, [(int(x), int(y)) for x, y in pts], (*shade(col, 0.78), a255))

                if cube and active and color is None and a255 >= 250:
                    if roll is None and dz == 0.0:
                        self._draw_marker(surf, (r0 + r1) / 2, (c0 + c1) / 2, height)
                return

        centroid = (sum(v[0] for v in verts) / 8, sum(v[1] for v in verts) / 8, sum(v[2] for v in verts) / 8)
        faces = []
        for f in _FACES:
            q = [verts[i] for i in f]
            n = _norm(_cross(_sub(q[1], q[0]), _sub(q[3], q[0])))
            fc = (sum(v[0] for v in q) / 4, sum(v[1] for v in q) / 4, sum(v[2] for v in q) / 4)
            if _dot(n, _sub(fc, centroid)) < 0:
                n = (-n[0], -n[1], -n[2])
            if _dot(n, self.iso.view) <= 1e-6:
                continue
            faces.append((_dot(fc, self.iso.view), q, n))
        faces.sort(key=lambda item: item[0])

        # ----------------- VẼ CHIM CÁNH CỤT BÊN TRONG (ARCTIC THEME) -----------------
        if self.arctic_theme and draw_penguin:
            is_cube = kind != "block"
            orig_h = 1.0 if is_cube or len(cells) > 1 or kind != "block" else 2.0
            h_ratio = max(0.0, height / orig_h)
            p_scale = scale * min(1.0, h_ratio)
            if p_scale > 0.01:
                p_verts, p_faces, p_colors = get_penguin_mesh(is_cube=is_cube)
                if frame is None:
                    if is_cube or len(cells) == 1:
                        actual_frame = INITIAL_FRAME
                    else:
                        c_list = list(cells)
                        if c_list[0][0] != c_list[1][0]:
                            actual_frame = ((1, 0, 0), (0, 0, -1), (0, 1, 0))  # Vertical dọc theo R
                        else:
                            actual_frame = ((0, 1, 0), (1, 0, 0), (0, 0, -1))  # Horizontal dọc theo C
                else:
                    actual_frame = frame

                head_vec, front_vec, right_vec = actual_frame

                # Tâm của khối trong không gian thế giới (r, c, z)
                box_cx = (r0 + r1) / 2.0
                box_cy = (c0 + c1) / 2.0
                box_cz = height / 2.0

                # Biến đổi từng đỉnh của chim theo hệ trục 3D của khối:
                abs_pverts = []
                for vr, vc, vz in p_verts:
                    pr = box_cx + (vr * front_vec[0] + vc * right_vec[0] + vz * head_vec[0]) * p_scale
                    pc = box_cy + (vr * front_vec[1] + vc * right_vec[1] + vz * head_vec[1]) * p_scale
                    pz = box_cz + (vr * front_vec[2] + vc * right_vec[2] + vz * head_vec[2]) * p_scale
                    abs_pverts.append((pr, pc, pz))

                if roll is not None:
                    abs_pverts = self._rotate(abs_pverts, box, *roll)
                abs_pverts = [(r + dr_offset, c + dc_offset, z + dz) for r, c, z in abs_pverts]

                p_centroid = (
                    sum(v[0] for v in abs_pverts) / max(1, len(abs_pverts)),
                    sum(v[1] for v in abs_pverts) / max(1, len(abs_pverts)),
                    sum(v[2] for v in abs_pverts) / max(1, len(abs_pverts)),
                )
                p_faces_to_draw = []
                for f_idx, f in enumerate(p_faces):
                    q = [abs_pverts[i] for i in f]
                    if len(q) < 3:
                        continue
                    n = _norm(_cross(_sub(q[1], q[0]), _sub(q[2], q[0])))
                    fc = (sum(v[0] for v in q) / len(q), sum(v[1] for v in q) / len(q), sum(v[2] for v in q) / len(q))
                    if _dot(n, self.iso.view) <= 1e-6:
                        continue
                    p_faces_to_draw.append((_dot(fc, self.iso.view), q, n, p_colors[f_idx]))

                p_faces_to_draw.sort(key=lambda item: item[0])
                for _, q, n, fcol in p_faces_to_draw:
                    lum = 0.52 + 0.62 * max(0.0, _dot(n, self.iso.light))
                    col = shade(fcol, lum)
                    pts = [self.iso.p(*v) for v in q]
                    poly(surf, (*col, a255), pts)
                    gfx.aapolygon(surf, [(int(x), int(y)) for x, y in pts], (*shade(col, 0.78), a255))

        outline = cube and active and color is None and a255 >= 250
        for _, q, n in faces:
            if self.arctic_theme:
                # Khối băng trong suốt bao bọc bên ngoài
                lum = 0.60 + 0.55 * max(0.0, _dot(n, self.iso.light))
                ice_base = color if color is not None else (theme.ARCTIC_ICE_BLOCK if active else (150, 195, 225))
                col = shade(ice_base, lum)
                pts = [self.iso.p(*v) for v in q]
                poly(surf, (*col, int(130 * alpha)), pts)
                gfx.aapolygon(surf, [(int(x), int(y)) for x, y in pts], (255, 255, 255, int(220 * alpha)))
                polyline(surf, (255, 255, 255, int(180 * alpha)), pts, width=2)
                cx = sum(x for x, _ in pts) / 4
                cy = sum(y for _, y in pts) / 4
                glint = [(cx + (x - cx) * 0.72, cy + (y - cy) * 0.72) for x, y in pts]
                gfx.filled_polygon(surf, [(int(x), int(y)) for x, y in glint], (255, 255, 255, int(48 * alpha)))
                if outline:
                    pygame.draw.polygon(surf, (120, 240, 255), [(int(x), int(y)) for x, y in pts], 3)
            else:
                lum = 0.50 + 0.66 * max(0.0, _dot(n, self.iso.light))
                col = shade(base, lum)
                pts = [self.iso.p(*v) for v in q]
                poly(surf, (*col, a255), pts, (*shade(col, 0.72), a255))
                cx = sum(x for x, _ in pts) / 4
                cy = sum(y for _, y in pts) / 4
                inner = [(cx + (x - cx) * 0.80, cy + (y - cy) * 0.80) for x, y in pts]
                gfx.filled_polygon(
                    surf, [(int(x), int(y)) for x, y in inner], (*shade(col, 1.14), int(a255 * 0.42))
                )
                if outline:  # khối đang điều khiển: viền trắng dày để nổi bật
                    pygame.draw.polygon(surf, (255, 255, 255), [(int(x), int(y)) for x, y in pts], 3)
        if outline and roll is None and dz == 0.0:
            self._draw_marker(surf, (r0 + r1) / 2, (c0 + c1) / 2, height)

    def draw_swallow(
        self,
        surf,
        cells: Sequence[Cell],
        kind: str,
        height: float,
        p: float,
        color=None,
        frame: Optional[Frame3D] = None,
    ) -> None:
        """Khối lọt thỏm xuống hố đích (p 0..1): trượt thẳng xuống theo trục Z mà không bị thu nhỏ."""
        cell = cells[0]
        # Không thu nhỏ (scale giữ nguyên 1.0)
        scale = 1.0
        # Rơi lọt thỏm xuống hố gia tốc dần theo trọng trường
        d = (p ** 1.6) * (height + 0.6)

        if self.is_desert:
            poly(surf, (4, 16, 26), self._ring(cell, 0.44, n=24, z=0.015))
            for k in range(3):
                v = (p * 1.7 + k / 3.0) % 1.0
                r_pts = self._ring(cell, 0.42 - 0.26 * v, n=24, rot=self.time * 0.8, z=0.02)
                gfx.aapolygon(surf, [(int(x), int(y)) for x, y in r_pts], (*theme.DESERT_GOAL_RING, int(220 * (1 - v) * (1 - 0.5 * p))))
        else:
            grow = math.sin(math.pi * min(1.0, p * 1.5))
            poly(surf, (2, 3, 6), self._diamond(cell, 0.27 + 0.10 * grow, 0.02))
            for k in range(3):  # các gợn co dần vào miệng hố, như bị hút xuống
                v = (p * 1.7 + k / 3.0) % 1.0
                pts = [(int(x), int(y)) for x, y in self._diamond(cell, 0.52 - 0.30 * v, 0.025)]
                gfx.aapolygon(surf, pts, (*(theme.ARCTIC_GOAL_RING if self.is_arctic else theme.GOAL_RING), int(210 * (1 - v) * (1 - 0.5 * p))))

        # Vẽ khối nguyên vẹn (bao gồm chú chim cánh cụt hoặc cây xương rồng) trượt thẳng xuống hố
        if d < height + 0.5:
            self.draw_piece(
                surf, cells, kind, height, dz=-d, color=color,
                scale=scale, shadow=False, frame=frame, draw_penguin=True,
            )

        if self.is_desert:
            for drad, a in ((0.0, 255), (0.02, 160), (0.05, 80)):
                gfx.aapolygon(surf, [(int(x), int(y)) for x, y in self._ring(cell, 0.44 + drad, n=24, z=0.0)], (*theme.DESERT_GOAL_RING, a))
        else:
            pygame.draw.polygon(surf, (70, 78, 104), [(int(x), int(y)) for x, y in self._diamond(cell, 0.41, 0.0)], 2)

    def _draw_marker(self, surf, r: float, c: float, height: float) -> None:
        """Mũi tên nhún nhảy phía trên khối đang điều khiển (phình to một chút ngay sau khi bấm Space)."""
        bob = 0.14 * math.sin(self.time * 5.0)
        x, y = self.iso.p(r, c, height + 0.62 + bob)
        s = max(9.0, self.iso.L * 0.17) * (1.0 + 0.9 * self.swap_pop)
        pts = [(int(x - s), int(y - s * 1.25)), (int(x + s), int(y - s * 1.25)), (int(x), int(y))]
        gfx.filled_polygon(surf, pts, (*theme.ACCENT, 255))
        gfx.aapolygon(surf, pts, (255, 255, 255, 255))
        pygame.draw.polygon(surf, (255, 255, 255), pts, 2)

    @staticmethod
    def _rotate(verts, box, direction, theta, pivot=None):
        r0, c0, r1, c1 = box
        dr, dc = direction
        cos, sin = math.cos(theta), math.sin(theta)
        out = []
        if dr:
            if pivot is None:
                pivot = r1 if dr > 0 else r0
            for r, c, z in verts:
                u = dr * (r - pivot)
                out.append((pivot + dr * (u * cos + z * sin), c, -u * sin + z * cos))
        else:
            if pivot is None:
                pivot = c1 if dc > 0 else c0
            for r, c, z in verts:
                u = dc * (c - pivot)
                out.append((r, pivot + dc * (u * cos + z * sin), -u * sin + z * cos))
        return out
