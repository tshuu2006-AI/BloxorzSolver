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
from typing import List, Optional, Sequence, Tuple

import pygame
import pygame.gfxdraw as gfx

from App.Components.features import SwitchType, TileType
from App.GUI import theme
from App.GUI.theme import mix, shade

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
                 min_fit: float = 24.0):
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
        self._fxbuf: Optional[pygame.Surface] = None
        self.set_camera(cam or Camera())

        n_bridges = len(self.problem.bridge_indices)
        self.bridge_color = [theme.TEXT_DIM] * n_bridges
        self.bridge_cell = [None] * n_bridges
        for cell, idx in self.problem.bridge_indices.items():
            g = level.bridge_group_of(cell)
            self.bridge_color[idx] = theme.BRIDGE_COLORS[g % len(theme.BRIDGE_COLORS)] if g >= 0 else theme.TEXT_DIM
            self.bridge_cell[idx] = cell
        self.bridge_v = [1.0 if b else 0.0 for b in self.problem.initial_state.bridges_state]
        self.bridge_target = list(self.bridge_v)

    # ------------------------------------------------------------------ cập nhật
    def set_camera(self, cam: Camera) -> None:
        """Dựng lại phép chiếu và thứ tự vẽ khi góc nhìn đổi."""
        self.iso = Iso(self.level.rows, self.level.cols, self.area, cam, self.min_fit)
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
        colors = colors or [theme.ACCENT, theme.GOAL_RING, (255, 255, 255), theme.GOOD]
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

    def _draw_cracks(self, surf, cell):
        p = self.iso.p
        r, c = cell
        dark = (112, 56, 20)
        for pts in (
            [(0.18, 0.30), (0.40, 0.46), (0.36, 0.70), (0.58, 0.82)],
            [(0.40, 0.46), (0.66, 0.40), (0.84, 0.54)],
            [(0.62, 0.22), (0.58, 0.50)],
        ):
            polyline(surf, dark, [p(r + a, c + b, 0.01) for a, b in pts], 2)

    def _draw_goal(self, surf, cell):
        self._draw_floor(surf, cell, TileType.FLOOR)
        rings = [(0.82, (46, 52, 74)), (0.68, (28, 32, 48)), (0.52, (14, 16, 26)), (0.34, (5, 6, 11))]
        for size, col in rings:
            poly(surf, col, self._diamond(cell, size / 2, 0.015))
        pulse = 0.5 + 0.5 * math.sin(self.time * 3.0)
        for grow, a in ((0.0, 210), (0.05, 120), (0.10, 60)):
            gfx.aapolygon(
                surf,
                [(int(x), int(y)) for x, y in self._diamond(cell, 0.41 + grow * (0.6 + pulse), 0.02)],
                (*theme.GOAL_RING, int(a * (0.55 + 0.45 * pulse))),
            )

    def _draw_bridge(self, surf, cell):
        idx = self.problem.bridge_indices[cell]
        v = self.bridge_v[idx]
        col = self.bridge_color[idx]
        r, c = cell
        if v < 0.98:
            ghost = [(int(x), int(y)) for x, y in self._diamond(cell, 0.5, 0.0)]
            gfx.filled_polygon(surf, ghost, (*col, int(34 * (1 - v))))
            gfx.aapolygon(surf, ghost, (*col, int(170 * (1 - v) + 30)))
            inner = [(int(x), int(y)) for x, y in self._diamond(cell, 0.26, 0.0)]
            gfx.aapolygon(surf, inner, (*col, int(90 * (1 - v))))
        if v > 0.03:
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
        p = self.iso.p
        cr, cc = cell[0] + 0.5, cell[1] + 0.5
        if sw.switch_type == SwitchType.SOFT:
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
    def draw_board(self, surf, show_hints: bool = True) -> None:
        grid = self.problem.grid
        # Bóng đổ nhẹ phía dưới bàn
        for cell in self.tile_order:
            if grid[cell] == TileType.BRIDGE and self.bridge_v[self.problem.bridge_indices[cell]] < 0.5:
                continue
            gfx.filled_polygon(
                surf,
                [(int(x), int(y)) for x, y in self._diamond(cell, 0.62, -self.iso.depth - 0.55, 0.08, 0.08)],
                (0, 0, 0, 38),
            )
        for cell in self.tile_order:
            tile = grid[cell]
            if tile == TileType.BRIDGE:
                self._draw_bridge(surf, cell)
            elif tile == TileType.GOAL:
                self._draw_goal(surf, cell)
            else:
                self._draw_floor(surf, cell, tile)
            sw = self.problem.switches.get(cell)
            if sw is not None:
                self._draw_switch(surf, cell, sw)
        if show_hints:
            for sw in self.problem.switches.values():
                if sw.split_targets:
                    self._draw_split_hint(surf, sw.split_targets)

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
        """
        iso = self.iso
        last = max((s["step"] for s in steps), default=1)
        size = max(11, int(iso.L * 0.24))
        for s in steps:
            t = (s["step"] - 1) / max(1, last - 1)
            col = mix(*(palette or (theme.INFO, theme.ACCENT)), t)
            reached = done is None or s["step"] <= done
            fill, line = (84 if done is None else 120, 200) if reached else (34, 96)
            for cell in s["cells"]:
                pts = [(int(x), int(y)) for x, y in self._diamond(cell, 0.41, 0.025)]
                gfx.filled_polygon(surf, pts, (*col, fill))
                gfx.aapolygon(surf, pts, (*col, line))
            r, c = s["cells"][0]
            x, y = iso.p(r + 0.5, c + 0.5, 0.04)
            img = self._label(str(s["step"]), size, col if reached else theme.TEXT_DIM)
            surf.blit(img, img.get_rect(center=(int(x), int(y))))
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
        roll: Optional[Tuple[Tuple[int, int], float]] = None,
        dz: float = 0.0,
        alpha: float = 1.0,
        active: bool = True,
        color=None,
        scale: float = 1.0,
        shadow: bool = True,
    ) -> None:
        """Vẽ một khối 3D phủ ``cells`` cao ``height`` (đơn vị ô).

        ``roll = (hướng, theta)`` xoay khối quanh cạnh đáy phía hướng lăn.
        """
        r0, c0, r1, c1 = box = piece_box(cells)
        if roll is None and dz == 0.0:
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
        verts = [(r, c, z + dz) for r, c, z in verts]

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
            p = self.iso.p
            gfx.filled_polygon(
                surf,
                [(int(x), int(y)) for x, y in (
                    p(min(rs), min(cs), 0.0), p(min(rs), max(cs), 0.0),
                    p(max(rs), max(cs), 0.0), p(max(rs), min(cs), 0.0))],
                (0, 0, 0, sh_alpha),
            )

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

        outline = cube and active and color is None and a255 >= 250
        for _, q, n in faces:
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

    def draw_swallow(self, surf, cells: Sequence[Cell], kind: str, height: float, p: float, color=None) -> None:
        """Khối chìm xuống hố đích (``p`` 0..1): hố nở ra, khối thu nhỏ và tối dần khi tụt vào trong.

        Phần khối còn trên mặt sàn vẽ bình thường; phần đã lọt xuống dưới mặt sàn chỉ hiện ra
        trong miệng hố (cắt bằng mặt nạ hình thoi) và tối đi theo độ sâu.
        """
        cell = cells[0]
        e = smoothstep(p)
        d = e * (height + 0.35)
        scale = 1.0 - 0.4 * smoothstep(p * 1.4)

        grow = math.sin(math.pi * min(1.0, p * 1.5))
        poly(surf, (2, 3, 6), self._diamond(cell, 0.27 + 0.10 * grow, 0.02))
        for k in range(3):  # các gợn co dần vào miệng hố, như bị hút xuống
            v = (p * 1.7 + k / 3.0) % 1.0
            pts = [(int(x), int(y)) for x, y in self._diamond(cell, 0.52 - 0.30 * v, 0.025)]
            gfx.aapolygon(surf, pts, (*theme.GOAL_RING, int(210 * (1 - v) * (1 - 0.5 * p))))

        if d < height:
            self.draw_piece(surf, cells, kind, height - d, color=color, scale=scale, shadow=False)
        lh = min(d, height)
        if lh > 0.01:
            rim = [(int(x), int(y)) for x, y in self._diamond(cell, 0.41, 0.0)]
            xs, ys = [q[0] for q in rim], [q[1] for q in rim]
            bb = pygame.Rect(min(xs) - 2, min(ys) - 2, max(xs) - min(xs) + 5, max(ys) - min(ys) + 5)
            if self._fxbuf is None or self._fxbuf.get_size() != surf.get_size():
                self._fxbuf = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
            bb = bb.clip(self._fxbuf.get_rect())
            if bb.w > 2 and bb.h > 2:
                sub = self._fxbuf.subsurface(bb)
                sub.fill((0, 0, 0, 0))
                self.draw_piece(self._fxbuf, cells, kind, lh, dz=-d, color=color, scale=scale, shadow=False)
                v = int(255 * max(0.1, 1.0 - 0.85 * min(1.0, d / max(height, 0.1))))
                sub.fill((v, v, v, 255), special_flags=pygame.BLEND_RGBA_MULT)
                mask = pygame.Surface(bb.size, pygame.SRCALPHA)
                local = [(x - bb.x, y - bb.y) for x, y in rim]
                gfx.filled_polygon(mask, local, (255, 255, 255, 255))
                sub.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                surf.blit(sub, bb.topleft)
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
    def _rotate(verts, box, direction, theta):
        r0, c0, r1, c1 = box
        dr, dc = direction
        cos, sin = math.cos(theta), math.sin(theta)
        out = []
        if dr:
            pivot = r1 if dr > 0 else r0
            for r, c, z in verts:
                u = dr * (r - pivot)
                out.append((pivot + dr * (u * cos + z * sin), c, -u * sin + z * cos))
        else:
            pivot = c1 if dc > 0 else c0
            for r, c, z in verts:
                u = dc * (c - pivot)
                out.append((r, pivot + dc * (u * cos + z * sin), -u * sin + z * cos))
        return out
