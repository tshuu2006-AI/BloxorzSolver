"""Menu và các màn hình giao diện chuẩn Steam Indie Game cho Bloxorz.

Bao gồm:
- MainMenu: Bầu không khí Nam Cực tươi sáng huyền ảo, cực quang, tuyết rơi, chú chim
  cánh cụt 3D lạch bạch chạy vòng quanh trên tảng băng (đầu, thân, mỏ 100% hiển thị chuẩn 3D),
  nút bấm phản hồi tức thì không delay, font chữ tương thích hoàn toàn (không lỗi ô vuông).
- LevelSelectView: Quần đảo băng tuyết phân chia Classic / Custom, hiển thị số sao,
  kỷ lục bước đi, trạng thái hoàn thành.
- SettingsView: Cài đặt toàn diện chuẩn PC chia 3 Tab:
  + Audio & Display: Toàn màn hình, Âm thanh, Âm lượng, Góc nghiêng Camera.
  + Gameplay & Hints: Đường đi giải đố, La bàn, Gợi ý Camera, Mũi tên sàn, Dây nối cầu, Mẹo chơi.
  + Data & Replay: Tốc độ replay, Xóa tiến độ.
- PauseMenu: Tạm dừng với phím ESC bảo lưu nguyên vẹn trạng thái bàn cờ.
- WinOverlay: Chúc mừng chiến thắng rực rỡ với cúp vàng và kỷ lục.
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple

import pygame
import pygame.gfxdraw as gfx

from App.GUI import theme
from App.GUI.models import get_cactus_mesh
from App.GUI.render import poly
from App.GUI.widgets import draw_text, rrect


# ---------------------------------------------------------------------------
# Hạt tuyết khí quyển (Theme Bắc Cực)
# ---------------------------------------------------------------------------
class SnowParticle:
    def __init__(self, w: int, h: int, rng: random.Random):
        self.w = w
        self.h = h
        self.x = rng.uniform(0, w)
        self.y = rng.uniform(0, h)
        self.size = rng.choice([1, 1, 2, 2, 3, 4])
        self.speed_y = rng.uniform(22.0, 55.0) * (self.size / 2.0)
        self.drift_freq = rng.uniform(0.5, 1.8)
        self.drift_amp = rng.uniform(15.0, 45.0)
        self.phase = rng.uniform(0, math.tau)
        self.alpha = int(rng.uniform(140, 255) * (self.size / 4.0))

    def update(self, dt: float):
        self.y += self.speed_y * dt
        self.phase += self.drift_freq * dt
        if self.y > self.h + 10:
            self.y = -10
            self.x = random.uniform(0, self.w)

    def draw(self, surf: pygame.Surface, base_t: float):
        curr_x = self.x + math.sin(self.phase + base_t) * self.drift_amp
        ix, iy = int(curr_x), int(self.y)
        if 0 <= ix < self.w and 0 <= iy < self.h:
            col = (235, 250, 255, self.alpha)
            if self.size <= 2:
                surf.set_at((ix, iy), col[:3])
            else:
                pts = [(ix, iy - self.size), (ix + self.size, iy), (ix, iy + self.size), (ix - self.size, iy)]
                gfx.filled_polygon(surf, pts, col)


# ---------------------------------------------------------------------------
# Hạt bụi cát vàng hoàng hôn (Theme Sa Mạc)
# ---------------------------------------------------------------------------
class SandParticle:
    def __init__(self, w: int, h: int, rng: random.Random):
        self.w = w
        self.h = h
        self.x = rng.uniform(0, w)
        self.y = rng.uniform(0, h)
        self.size = rng.choice([1, 1, 2, 2, 3])
        self.speed_x = rng.uniform(35.0, 90.0)
        self.speed_y = rng.uniform(8.0, 28.0)
        self.drift_freq = rng.uniform(0.6, 2.0)
        self.drift_amp = rng.uniform(8.0, 22.0)
        self.phase = rng.uniform(0, math.tau)
        self.alpha = int(rng.uniform(120, 240) * (self.size / 3.0))

    def update(self, dt: float):
        self.x += self.speed_x * dt
        self.y += self.speed_y * dt
        self.phase += self.drift_freq * dt
        if self.x > self.w + 10 or self.y > self.h + 10:
            self.x = -10
            self.y = random.uniform(0, self.h)

    def draw(self, surf: pygame.Surface, base_t: float):
        curr_y = self.y + math.sin(self.phase + base_t) * self.drift_amp
        ix, iy = int(self.x), int(curr_y)
        if 0 <= ix < self.w and 0 <= iy < self.h:
            col = (255, 215, 120, self.alpha)
            if self.size <= 2:
                surf.set_at((ix, iy), col[:3])
            else:
                pts = [(ix, iy - self.size), (ix + self.size, iy), (ix, iy + self.size), (ix - self.size, iy)]
                gfx.filled_polygon(surf, pts, col)


# ---------------------------------------------------------------------------
# Main Menu
# ---------------------------------------------------------------------------

class MainMenu:
    def __init__(self, app):
        self.app = app
        self.w, self.h = theme.WIDTH, theme.HEIGHT
        self.time = 0.0

        self.items = [
            ("play", "PLAY"),
            ("level_select", "LEVEL SELECT"),
            ("settings", "SETTINGS"),
            ("credits", "CREDITS"),
            ("quit", "QUIT"),
        ]
        self.selected_idx = 0
        self.hovered_idx = -1
        self.keyboard_mode = False
        self.hover_progress = [0.0] * len(self.items)

        rng = random.Random(42)
        self.snow_particles = [SnowParticle(self.w, self.h, rng) for _ in range(80)]
        self.sand_particles = [SandParticle(self.w, self.h, rng) for _ in range(80)]
        self.btn_theme_rect = pygame.Rect(self.w - 380, 42, 330, 48)

        # Ambient lighting
        self.alpha = math.radians(-32)
        self.elev = math.radians(28)

        self.credits_open = False
        self.credits_anim = 0.0
        self.item_rects: List[pygame.Rect] = []

    def handle(self, event: pygame.event.Event, mouse: Tuple[int, int]) -> bool:
        if self.credits_open:
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                self.credits_open = False
                self.credits_anim = 0.0
                self.app.audio.play("swap")
                return True
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.credits_open = False
                self.credits_anim = 0.0
                self.app.audio.play("swap")
                return True
            return True

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_t:
                self.app.toggle_theme()
                return True
            self.keyboard_mode = True
            if event.key in (pygame.K_UP, pygame.K_w):
                self.selected_idx = (self.selected_idx - 1) % len(self.items)
                self.app.audio.play("swap")
                return True
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected_idx = (self.selected_idx + 1) % len(self.items)
                self.app.audio.play("swap")
                return True
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._activate_item(self.items[self.selected_idx][0])
                return True
            elif event.key == pygame.K_ESCAPE:
                self._activate_item("quit")
                return True

        if event.type == pygame.MOUSEMOTION:
            found = -1
            for idx, r in enumerate(self.item_rects):
                if r.collidepoint(mouse):
                    found = idx
                    break
            if found != self.hovered_idx:
                if found != -1:
                    self.selected_idx = found
                    self.keyboard_mode = False
                    self.app.audio.play("swap")
                self.hovered_idx = found

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.btn_theme_rect.collidepoint(mouse):
                self.app.toggle_theme()
                return True
            for idx, r in enumerate(self.item_rects):
                if r.collidepoint(mouse):
                    self.selected_idx = idx
                    self._activate_item(self.items[idx][0])
                    return True

        return False

    def _activate_item(self, action_id: str):
        self.app.audio.play("switch")
        if action_id == "play":
            self.app.push_screen("playing")
        elif action_id == "level_select":
            self.app.push_screen("level_select")
        elif action_id == "settings":
            self.app.push_screen("settings")
        elif action_id == "credits":
            self.credits_open = True
            self.credits_anim = 1.0
        elif action_id == "quit":
            self.app.running = False

    def update(self, dt: float, mouse: Tuple[int, int]):
        self.time += dt

        if self.app.current_theme == "desert":
            for p in self.sand_particles:
                p.update(dt)
        else:
            for p in self.snow_particles:
                p.update(dt)

        mouse_over_any = any(r.collidepoint(mouse) for r in self.item_rects)
        if not mouse_over_any and not self.keyboard_mode:
            self.hovered_idx = -1

        for i in range(len(self.items)):
            if self.credits_open:
                target = 0.0
            elif self.keyboard_mode:
                target = 1.0 if (i == self.selected_idx) else 0.0
            else:
                target = 1.0 if (i == self.hovered_idx) else 0.0

            speed = 28.0 if target > self.hover_progress[i] else 24.0
            self.hover_progress[i] += (target - self.hover_progress[i]) * min(1.0, dt * speed)

        if not self.credits_open:
            self.credits_anim = 0.0
        else:
            self.credits_anim = min(1.0, self.credits_anim + dt * 25.0)

    def draw(self, surf: pygame.Surface, mouse: Tuple[int, int]):
        self._draw_background(surf)
        self._draw_aurora(surf)

        if self.app.current_theme == "desert":
            for p in self.sand_particles:
                p.draw(surf, self.time)
        else:
            for p in self.snow_particles:
                p.draw(surf, self.time)

        self._draw_branding(surf)
        self._draw_menu_buttons(surf)
        self._draw_theme_toggle(surf, mouse)
        self._draw_footer(surf)

        if self.credits_open and self.credits_anim > 0.01:
            self._draw_credits_modal(surf)

    def _draw_theme_toggle(self, surf: pygame.Surface, mouse: Tuple[int, int]):
        r = self.btn_theme_rect
        is_hover = r.collidepoint(mouse)
        is_desert = (self.app.current_theme == "desert")
        bg_col = (72, 36, 48, 230) if is_desert else (22, 36, 60, 230)
        if is_hover:
            bg_col = (95, 48, 64, 255) if is_desert else (34, 56, 92, 255)
        border_col = (255, 195, 75) if is_desert else (120, 245, 255)
        rrect(surf, r, bg_col, radius=12, border=border_col, border_w=2 if is_hover else 1)

        lbl = "[ THEME: DESERT OASIS ]" if is_desert else "[ THEME: ARCTIC EXPEDITION ]"
        draw_text(surf, lbl, theme.font(16, bold=True), (255, 255, 255), r.center, "center")
        hint_col = (245, 190, 140) if is_desert else (160, 205, 240)
        draw_text(surf, "[Click / Press 'T' to switch]", theme.font(13), hint_col, (r.centerx, r.bottom + 6), "midtop")

    def _draw_background(self, surf: pygame.Surface):
        if self.app.current_theme == "desert":
            top_color = (48, 22, 34)
            bot_color = (112, 52, 56)
        else:
            top_color = (16, 26, 48)
            bot_color = (36, 56, 92)
        h = self.h
        for y in range(0, h, 2):
            t = y / h
            col = (
                int(top_color[0] + (bot_color[0] - top_color[0]) * t),
                int(top_color[1] + (bot_color[1] - top_color[1]) * t),
                int(top_color[2] + (bot_color[2] - top_color[2]) * t),
            )
            pygame.draw.line(surf, col, (0, y), (self.w, y), 2)

    def _draw_aurora(self, surf: pygame.Surface):
        aurora_surf = pygame.Surface((self.w, 440), pygame.SRCALPHA)
        t = self.time * 0.7

        if self.app.current_theme == "desert":
            layers = [
                ((255, 140, 65, 34), 125.0, 0.0035, 1.4, 0.0),
                ((245, 85, 115, 30), 95.0, 0.0045, 1.1, 2.1),
                ((255, 205, 80, 22), 75.0, 0.0028, 1.6, 4.2),
            ]
        else:
            layers = [
                ((80, 235, 248, 30), 125.0, 0.0035, 1.4, 0.0),
                ((95, 252, 205, 34), 95.0, 0.0045, 1.1, 2.1),
                ((135, 215, 255, 24), 75.0, 0.0028, 1.6, 4.2),
            ]

        step = 24
        for col, base_y, freq, speed, phase_offset in layers:
            pts = [(0, 440)]
            for x in range(0, self.w + step, step):
                y = base_y + math.sin(x * freq + t * speed + phase_offset) * 48.0 + math.cos(x * 0.0018 - t * 0.5) * 26.0
                pts.append((x, int(y)))
            pts.append((self.w, 440))
            if len(pts) > 2:
                pygame.draw.polygon(aurora_surf, col, pts)

        surf.blit(aurora_surf, (0, 0))

    def _draw_branding(self, surf: pygame.Surface):
        x = 180
        y = 220
        is_desert = (self.app.current_theme == "desert")

        sub_badge = "[ AI SOLVER EXPEDITION ]"
        badge_col = (255, 205, 100) if is_desert else (120, 240, 255)
        draw_text(surf, sub_badge, theme.font(16, bold=True), badge_col, (x, y))

        title_y = y + 28
        title_tint = (220, 110, 65) if is_desert else (60, 175, 235)
        draw_text(surf, "BLOXORZ", theme.font(92, bold=True), (12, 8, 16), (x + 3, title_y + 4))
        draw_text(surf, "BLOXORZ", theme.font(92, bold=True), title_tint, (x, title_y))
        draw_text(surf, "BLOXORZ", theme.font(92, bold=True), (252, 248, 245), (x - 2, title_y - 2))

        tag_y = title_y + 98
        tag_text = "DESERT OASIS EXPEDITION" if is_desert else "POLAR EXPEDITION"
        tag_col = (255, 215, 140) if is_desert else (180, 230, 255)
        draw_text(surf, tag_text, theme.font(24, bold=True), tag_col, (x, tag_y))

        line_y = tag_y + 40
        line_col = (135, 75, 52) if is_desert else (50, 80, 120)
        circ_col = (255, 205, 100) if is_desert else (130, 245, 255)
        pygame.draw.line(surf, line_col, (x, line_y), (x + 480, line_y), 2)
        pygame.draw.circle(surf, circ_col, (x + 240, line_y), 4)

    def _draw_menu_buttons(self, surf: pygame.Surface):
        start_x = 180
        start_y = 440
        btn_w = 340
        btn_h = 58
        spacing = 74
        is_desert = (self.app.current_theme == "desert")

        self.item_rects = []

        for i, (action_id, label) in enumerate(self.items):
            cur_y = start_y + i * spacing
            t = self.hover_progress[i]

            slide_x = int(t * 14.0)
            rect = pygame.Rect(start_x + slide_x, cur_y, btn_w, btn_h)
            self.item_rects.append(pygame.Rect(start_x, cur_y, btn_w + 20, btn_h))

            if t > 0.01:
                if is_desert:
                    bg_col = (
                        int(38 + 45 * t),
                        int(22 + 35 * t),
                        int(30 + 35 * t),
                        int(170 + 80 * t),
                    )
                    border_col = (
                        int(170 + 85 * t),
                        int(95 + 110 * t),
                        int(45 + 50 * t),
                    )
                    glow_col = (255, 195, 75)
                else:
                    bg_col = (
                        int(20 + 35 * t),
                        int(32 + 55 * t),
                        int(55 + 85 * t),
                        int(170 + 80 * t),
                    )
                    border_col = (
                        int(70 + 175 * t),
                        int(120 + 130 * t),
                        int(180 + 75 * t),
                    )
                    glow_col = (120, 245, 255)
                rrect(surf, rect, bg_col, radius=10, border=border_col, border_w=2)

                glow_h = int(btn_h * 0.7)
                glow_rect = pygame.Rect(rect.x + 3, rect.centery - glow_h // 2, 4, glow_h)
                pygame.draw.rect(surf, glow_col, glow_rect, border_radius=2)

                # Vẽ hình thoi bằng đa giác chuẩn (không dùng font unicode tránh lỗi ô vuông)
                diamond_x = rect.x + 24
                diamond_y = rect.centery
                pts = [
                    (diamond_x, diamond_y - 6),
                    (diamond_x + 6, diamond_y),
                    (diamond_x, diamond_y + 6),
                    (diamond_x - 6, diamond_y),
                ]
                gfx.filled_polygon(surf, pts, glow_col)
            else:
                bg_col = (34, 18, 26, 140) if is_desert else (18, 26, 44, 140)
                border_col = (82, 45, 40) if is_desert else (46, 68, 102)
                rrect(surf, rect, bg_col, radius=10, border=border_col, border_w=1)

            if is_desert:
                text_col = (
                    int(215 + 40 * t),
                    int(185 + 65 * t),
                    int(145 + 105 * t),
                )
            else:
                text_col = (
                    int(175 + 80 * t),
                    int(200 + 55 * t),
                    int(230 + 25 * t),
                )
            text_x = rect.x + (46 if t > 0.05 else 32)
            draw_text(surf, label, theme.font(24, bold=True), text_col, (text_x, rect.centery), anchor="midleft")

    def _draw_diorama(self, surf: pygame.Surface):
        """Vẽ diorama đảo sa mạc / bắc cực với mô hình 3D biểu tượng của theme."""
        cx = 1360
        cy = 580

        island_pts_top = [
            (cx - 250, cy + 80),
            (cx - 100, cy + 25),
            (cx + 120, cy + 20),
            (cx + 260, cy + 65),
            (cx + 240, cy + 135),
            (cx + 90, cy + 180),
            (cx - 110, cy + 175),
            (cx - 240, cy + 130),
        ]
        cliff_depth = 48
        glow_pulse = 0.5 + 0.5 * math.sin(self.time * 2.2)
        pedestal_cx = cx
        pedestal_cy = cy + 95

        if self.app.current_theme == "desert":
            # Nền đảo sa mạc cao nguyên đá trầm tích
            for i in range(len(island_pts_top)):
                p1 = island_pts_top[i]
                p2 = island_pts_top[(i + 1) % len(island_pts_top)]
                if p2[0] >= p1[0] or p1[1] > cy + 95:
                    side_pts = [p1, p2, (p2[0], p2[1] + cliff_depth), (p1[0], p1[1] + cliff_depth)]
                    side_col = (168, 98, 54) if i % 2 == 0 else (138, 76, 38)
                    poly(surf, side_col, side_pts, outline=(95, 48, 25))

            poly(surf, (238, 196, 132), island_pts_top, outline=(215, 168, 105))

            # Vệt cát vàng sa mạc
            sand_pts = [(cx - 90, cy + 80), (cx - 40, cy + 95), (cx + 15, cy + 88), (cx + 55, cy + 112)]
            pygame.draw.lines(surf, (255, 220, 160), False, sand_pts, 3)

            # Vầng hào quang hoàng hôn dưới chân cây xương rồng
            halo_surf = pygame.Surface((200, 110), pygame.SRCALPHA)
            halo_alpha = int(45 + 35 * glow_pulse)
            pygame.draw.ellipse(halo_surf, (255, 185, 75, halo_alpha), (0, 0, 200, 110))
            surf.blit(halo_surf, (pedestal_cx - 100, pedestal_cy - 55))

            # Mô hình 3D Cây Xương Rồng low-poly xoay chậm quanh trục đứng Z
            c_verts, c_faces, c_colors = get_cactus_mesh(is_cube=False)
            rot = self.time * 0.75
            cos_a, sin_a = math.cos(rot), math.sin(rot)
            d_scale = 68.0

            proj_verts = []
            for vr, vc, vz in c_verts:
                rx = vr * cos_a - vc * sin_a
                ry = vr * sin_a + vc * cos_a
                rz = vz
                sx = pedestal_cx + (ry - rx * 0.8) * d_scale
                sy = (pedestal_cy - 65) - rz * d_scale + (rx + ry) * d_scale * 0.32
                depth = rx * 0.5 + ry * 0.5 + rz
                proj_verts.append((sx, sy, depth, (rx, ry, rz)))

            light_dir = (0.577, 0.577, 0.577)
            face_draw_list = []
            for f_idx, f in enumerate(c_faces):
                q = [proj_verts[i] for i in f]
                if len(q) < 3:
                    continue
                avg_depth = sum(p[2] for p in q) / len(q)
                v0, v1, v2 = q[0][3], q[1][3], q[2][3]
                d1 = (v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2])
                d2 = (v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2])
                nx = d1[1] * d2[2] - d1[2] * d2[1]
                ny = d1[2] * d2[0] - d1[0] * d2[2]
                nz = d1[0] * d2[1] - d1[1] * d2[0]
                nl = math.hypot(nx, ny, nz) or 1.0
                norm = (nx / nl, ny / nl, nz / nl)
                fc = (sum(p[3][0] for p in q) / len(q), sum(p[3][1] for p in q) / len(q), sum(p[3][2] for p in q) / len(q))
                if norm[0] * fc[0] + norm[1] * fc[1] + norm[2] * fc[2] < 0:
                    norm = (-norm[0], -norm[1], -norm[2])

                if norm[0] * (-0.7) + norm[1] * (-0.5) + norm[2] * 0.8 <= -0.15:
                    continue

                lum = 0.52 + 0.62 * max(0.0, norm[0] * light_dir[0] + norm[1] * light_dir[1] + norm[2] * light_dir[2])
                col = theme.shade(c_colors[f_idx], lum)
                pts = [(int(p[0]), int(p[1])) for p in q]
                face_draw_list.append((avg_depth, pts, col))

            face_draw_list.sort(key=lambda item: item[0])
            for _, pts, col in face_draw_list:
                poly(surf, col, pts)
                gfx.aapolygon(surf, pts, (*theme.shade(col, 0.82), 255))
            return

        # Theme Bắc Cực: Khối hộp pha lê băng đứng thẳng ở trung tâm tảng băng
        for i in range(len(island_pts_top)):
            p1 = island_pts_top[i]
            p2 = island_pts_top[(i + 1) % len(island_pts_top)]
            if p2[0] >= p1[0] or p1[1] > cy + 95:
                side_pts = [p1, p2, (p2[0], p2[1] + cliff_depth), (p1[0], p1[1] + cliff_depth)]
                side_col = (82, 122, 165) if i % 2 == 0 else (64, 98, 138)
                poly(surf, side_col, side_pts, outline=(42, 68, 98))

        poly(surf, (235, 248, 255), island_pts_top, outline=(185, 225, 252))

        # Đường nứt băng phát sáng
        crack_pts = [(cx - 90, cy + 80), (cx - 40, cy + 95), (cx + 15, cy + 88), (cx + 55, cy + 112)]
        pygame.draw.lines(surf, (150, 220, 250), False, crack_pts, 3)

        # Vầng hào quang dưới chân khối băng
        halo_surf = pygame.Surface((180, 100), pygame.SRCALPHA)
        halo_alpha = int(45 + 30 * glow_pulse)
        pygame.draw.ellipse(halo_surf, (80, 230, 255, halo_alpha), (0, 0, 180, 100))
        surf.blit(halo_surf, (pedestal_cx - 90, pedestal_cy - 50))

        # Khối hộp băng Bloxorz 3D đứng thẳng ở trung tâm tảng băng
        bw, bh = 36, 72
        bx, by = pedestal_cx, pedestal_cy - 30

        top_poly = [
            (bx, by - bh),
            (bx + bw, by - bh - 18),
            (bx, by - bh - 36),
            (bx - bw, by - bh - 18),
        ]
        left_poly = [
            (bx - bw, by - bh - 18),
            (bx, by - bh),
            (bx, by),
            (bx - bw, by - 18),
        ]
        right_poly = [
            (bx, by - bh),
            (bx + bw, by - bh - 18),
            (bx + bw, by - 18),
            (bx, by),
        ]

        poly(surf, (140, 215, 250), left_poly, outline=(190, 245, 255))
        poly(surf, (100, 175, 225), right_poly, outline=(180, 240, 255))
        poly(surf, (220, 248, 255), top_poly, outline=(245, 255, 255))

    def _draw_footer(self, surf: pygame.Surface):
        y = self.h - 48
        draw_text(surf, "Bloxorz: Polar Expedition  |  CSAI Project 2026", theme.font(16), (120, 155, 195), (180, y))
        controls_hint = "[W/S / ARROWS] Navigate   |   [ENTER / SPACE] Select   |   [ESC] Quit"
        draw_text(surf, controls_hint, theme.font(16), (135, 175, 215), (self.w - 180, y), anchor="topright")

    def _draw_credits_modal(self, surf: pygame.Surface):
        overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        overlay.fill((8, 14, 26, 220))
        surf.blit(overlay, (0, 0))

        mw, mh = 760, 520
        mx = (self.w - mw) // 2
        my = (self.h - mh) // 2

        modal_rect = pygame.Rect(mx, my, mw, mh)
        rrect(surf, modal_rect, (18, 28, 48, 250), radius=16, border=(90, 160, 225), border_w=2)

        draw_text(surf, "CREDITS & PROJECT INFO", theme.font(28, bold=True), (230, 248, 255), (mx + mw // 2, my + 38), "center")
        pygame.draw.line(surf, (50, 90, 135), (mx + 60, my + 78), (mx + mw - 60, my + 78), 2)

        lines = [
            ("Course", "Cơ sở Trí tuệ Nhân tạo (CSAI)"),
            ("Institution", "Trường Đại học Khoa học Tự nhiên - ĐHQG HCM"),
            ("Project", "Bloxorz Solver"),
            ("AI Solvers", "BFS, DFS, UCS, A* (Manhattan, Euclidean, Walking Dist, Pattern DB)"),
        ]

        text_y = my + 110
        for label, val in lines:
            draw_text(surf, label, theme.font(18, bold=True), (120, 225, 250), (mx + 80, text_y))
            draw_text(surf, val, theme.font(17), (220, 235, 250), (mx + 220, text_y))
            text_y += 42

        draw_text(surf, "[ Click anywhere or press ESC / ENTER to close ]", theme.font(17, bold=True), (140, 195, 235), (mx + mw // 2, my + mh - 45), "center")


# ---------------------------------------------------------------------------
# Màn hình Chọn màn chơi (Level Select - Archipelago Grid with Map Previews)
# ---------------------------------------------------------------------------
class LevelSelectView:
    def __init__(self, app):
        self.app = app
        self.w, self.h = theme.WIDTH, theme.HEIGHT
        self.active_tab = "classic"
        self.page = 0
        self.levels_per_page = 10  # 5 cột x 2 hàng có ảnh map thu nhỏ
        self.hovered_level_idx = -1
        self.btn_back_rect = pygame.Rect(100, 50, 130, 44)
        self.tab_rects = {
            "classic": pygame.Rect(self.w // 2 - 200, 50, 190, 44),
            "custom": pygame.Rect(self.w // 2 + 10, 50, 190, 44),
        }
        self.card_rects: List[Tuple[int, pygame.Rect]] = []
        self.btn_prev_page = pygame.Rect(0, 0, 100, 40)
        self.btn_next_page = pygame.Rect(0, 0, 100, 40)
        self.page_pill_rects: List[Tuple[int, pygame.Rect]] = []

    def _get_tab_levels(self) -> List[Tuple[int, any]]:
        return [(i, lv) for i, lv in enumerate(self.app.levels) if lv.section == self.active_tab]

    def handle(self, event: pygame.event.Event, mouse: Tuple[int, int]) -> bool:
        tab_levels = self._get_tab_levels()
        max_page = max(0, (len(tab_levels) - 1) // self.levels_per_page)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.app.pop_screen()
                self.app.audio.play("swap")
                return True
            elif event.key == pygame.K_LEFT:
                if self.page > 0:
                    self.page -= 1
                    self.app.audio.play("swap")
                return True
            elif event.key == pygame.K_RIGHT:
                if self.page < max_page:
                    self.page += 1
                    self.app.audio.play("swap")
                return True
            elif event.key == pygame.K_TAB:
                self.active_tab = "custom" if self.active_tab == "classic" else "classic"
                self.page = 0
                self.app.audio.play("swap")
                return True

        if event.type == pygame.MOUSEMOTION:
            found = -1
            for global_idx, r in self.card_rects:
                if r.collidepoint(mouse):
                    found = global_idx
                    break
            self.hovered_level_idx = found

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.btn_back_rect.collidepoint(mouse):
                self.app.pop_screen()
                self.app.audio.play("swap")
                return True

            # Chuyển đổi tab CLASSIC / CUSTOM
            for tab_key, r in self.tab_rects.items():
                if r.collidepoint(mouse) and self.active_tab != tab_key:
                    self.active_tab = tab_key
                    self.page = 0
                    self.app.audio.play("swap")
                    return True

            # Nút mũi tên lùi trang [ < PREV ]
            if self.btn_prev_page.collidepoint(mouse) and self.page > 0:
                self.page -= 1
                self.app.audio.play("swap")
                return True

            # Nút mũi tên tới trang [ NEXT > ]
            if self.btn_next_page.collidepoint(mouse) and self.page < max_page:
                self.page += 1
                self.app.audio.play("swap")
                return True

            # Click trực tiếp vào các nút số trang [ 1 ] [ 2 ] [ 3 ]...
            for p, r in self.page_pill_rects:
                if r.collidepoint(mouse) and self.page != p:
                    self.page = p
                    self.app.audio.play("swap")
                    return True

            # Click vào thẻ bài màn chơi để bắt đầu
            for global_idx, r in self.card_rects:
                if r.collidepoint(mouse):
                    self.app.audio.play("switch")
                    self.app.load_level(global_idx)
                    self.app.screen_stack = ["menu", "playing"]
                    self.app.screen_state = "playing"
                    return True

        return False

    def update(self, dt: float, mouse: Tuple[int, int]):
        pass

    def draw(self, surf: pygame.Surface, mouse: Tuple[int, int]):
        surf.blit(self.app.bg, (0, 0))
        is_desert = (self.app.current_theme == "desert")

        # Nút Quay lại
        is_back_hover = self.btn_back_rect.collidepoint(mouse)
        back_bg = ((60, 32, 42) if is_desert else (34, 52, 82)) if is_back_hover else ((36, 18, 26) if is_desert else (22, 34, 54))
        back_bdr = (255, 185, 75) if is_desert else (80, 150, 220)
        rrect(surf, self.btn_back_rect, back_bg, radius=8, border=back_bdr, border_w=1)
        draw_text(surf, "< BACK", theme.font(17, bold=True), (240, 248, 255), self.btn_back_rect.center, "center")

        # 2 Tabs chọn nhóm màn chơi (CLASSIC / CUSTOM)
        for tab_key, r in self.tab_rects.items():
            active = (self.active_tab == tab_key)
            is_hover = r.collidepoint(mouse)
            if active:
                bg = (85, 42, 54) if is_desert else (46, 88, 142)
                border = (255, 205, 80) if is_desert else (120, 230, 255)
            elif is_hover:
                bg = (56, 28, 38) if is_desert else (32, 50, 78)
                border = (215, 140, 60) if is_desert else (80, 140, 200)
            else:
                bg = (34, 18, 26) if is_desert else (20, 30, 48)
                border = (110, 60, 52) if is_desert else (56, 90, 135)
            rrect(surf, r, bg, radius=8, border=border, border_w=2 if active else 1)
            count = sum(1 for lv in self.app.levels if lv.section == tab_key)
            label = f"{tab_key.upper()} ({count})"
            col = (255, 255, 255) if active else (175, 205, 235)
            draw_text(surf, label, theme.font(17, bold=True), col, r.center, "center")

        tab_levels = self._get_tab_levels()
        start_idx = self.page * self.levels_per_page
        page_levels = tab_levels[start_idx : start_idx + self.levels_per_page]
        max_page = max(0, (len(tab_levels) - 1) // self.levels_per_page)

        # Lưới thẻ bài (5 cột x 2 hàng = 10 thẻ có ảnh preview bàn chơi)
        card_w = 320
        card_h = 326
        gap_x = 20
        gap_y = 18
        grid_w = 5 * card_w + 4 * gap_x
        grid_x = (self.w - grid_w) // 2
        grid_y = 118

        self.card_rects = []
        for i, (global_idx, lv) in enumerate(page_levels):
            col = i % 5
            row = i // 5
            rx = grid_x + col * (card_w + gap_x)
            ry = grid_y + row * (card_h + gap_y)
            rect = pygame.Rect(rx, ry, card_w, card_h)
            self.card_rects.append((global_idx, rect))

            is_hover = (global_idx == self.hovered_level_idx)
            is_current = (global_idx == getattr(self.app, "level_idx", 0))
            is_cleared = self.app.progress.is_cleared(lv.name)
            best_moves = self.app.progress.best(lv.name)

            if is_hover:
                card_bg = (64, 32, 42) if is_desert else (34, 54, 88)
                border = (255, 205, 80) if is_desert else (130, 245, 255)
                border_w = 2
            elif is_current:
                card_bg = (52, 26, 36) if is_desert else (26, 44, 72)
                border = (225, 145, 65) if is_desert else (80, 195, 255)
                border_w = 2
            else:
                card_bg = (38, 20, 28) if is_desert else (18, 28, 46)
                border = (95, 52, 48) if is_desert else (50, 75, 110)
                border_w = 1

            rrect(surf, rect, card_bg, radius=12, border=border, border_w=border_w)

            # 1. Header thẻ
            num_str = f"STAGE {i + 1 + start_idx:02d}"
            num_col = (255, 205, 90) if is_desert else ((130, 230, 255) if is_hover else (100, 180, 235))
            draw_text(surf, num_str, theme.font(16, bold=True), num_col, (rx + 14, ry + 12))

            if is_cleared:
                rrect(surf, (rx + card_w - 92, ry + 8, 80, 24), (20, 60, 42), radius=6, border=(65, 210, 135), border_w=1)
                draw_text(surf, "[v] CLEAR", theme.font(12, bold=True), (90, 245, 155), (rx + card_w - 52, ry + 20), "center")
            elif is_current:
                rrect(surf, (rx + card_w - 92, ry + 8, 80, 24), (65, 38, 20) if is_desert else (24, 48, 75), radius=6, border=(240, 160, 60) if is_desert else (80, 180, 255), border_w=1)
                draw_text(surf, "PLAYING", theme.font(12, bold=True), (255, 215, 110) if is_desert else (130, 230, 255), (rx + card_w - 52, ry + 20), "center")

            # 2. Ảnh map thu nhỏ của màn chơi (Isometric Preview)
            thumb_w, thumb_h = 296, 210
            thumb_rect = pygame.Rect(rx + 12, ry + 36, thumb_w, thumb_h)
            tb_bg = (24, 12, 18) if is_desert else (12, 18, 30)
            rrect(surf, thumb_rect, tb_bg, radius=8)
            thumb_img = self.app._thumb(global_idx, (thumb_w, thumb_h))
            surf.blit(thumb_img, thumb_rect.topleft)
            tb_bdr = (120, 65, 55) if is_desert else (50, 75, 115)
            rrect(surf, thumb_rect, (0, 0, 0, 0), radius=8, border=border if is_hover else tb_bdr, border_w=1)

            # 3. Footer thẻ (Tên màn chơi + Kích thước lưới + Thành tích)
            draw_text(surf, lv.name, theme.font(17, bold=True), (245, 250, 255), (rx + 14, ry + 256))
            max_r = max((r for r, c in lv.problem.grid), default=0) + 1
            max_c = max((c for r, c in lv.problem.grid), default=0) + 1
            dim_str = f"Grid: {max_r}x{max_c}"
            draw_text(surf, dim_str, theme.font(14), (160, 190, 220), (rx + 14, ry + 282))

            if is_cleared and best_moves is not None:
                draw_text(surf, f"Best: {best_moves} moves", theme.font(14, bold=True), (255, 220, 100), (rx + card_w - 14, ry + 282), "topright")
            else:
                draw_text(surf, "Unplayed", theme.font(14), (130, 155, 185), (rx + card_w - 14, ry + 282), "topright")

        # ----------------- THANH ĐIỀU HƯỚNG TRANG (PAGINATION BAR) -----------------
        cx = self.w // 2
        py = 808
        n_pages = max_page + 1
        pill_w, pill_h, pill_gap = 46, 38, 10
        total_pills_w = n_pages * pill_w + (n_pages - 1) * pill_gap
        pills_start_x = cx - total_pills_w // 2

        self.btn_prev_page = pygame.Rect(pills_start_x - 116, py, 100, pill_h)
        self.btn_next_page = pygame.Rect(pills_start_x + total_pills_w + 16, py, 100, pill_h)

        # Nút mũi tên lùi trang [ < PREV ]
        prev_enabled = (self.page > 0)
        prev_hover = self.btn_prev_page.collidepoint(mouse) and prev_enabled
        if prev_enabled:
            prev_bg = ((60, 32, 42) if is_desert else (38, 62, 98)) if prev_hover else ((36, 18, 26) if is_desert else (22, 34, 54))
            prev_bdr = (255, 195, 80) if is_desert else (100, 175, 240)
            prev_col = (255, 255, 255)
        else:
            prev_bg = (24, 14, 18) if is_desert else (16, 22, 36)
            prev_bdr = (60, 36, 32) if is_desert else (35, 48, 70)
            prev_col = (110, 95, 95) if is_desert else (85, 105, 130)
        rrect(surf, self.btn_prev_page, prev_bg, radius=8, border=prev_bdr, border_w=1)
        draw_text(surf, "< PREV", theme.font(15, bold=True), prev_col, self.btn_prev_page.center, "center")

        # Các nút số trang [ 1 ] [ 2 ] [ 3 ]...
        self.page_pill_rects = []
        for p in range(n_pages):
            pr = pygame.Rect(pills_start_x + p * (pill_w + pill_gap), py, pill_w, pill_h)
            self.page_pill_rects.append((p, pr))
            p_active = (p == self.page)
            p_hover = pr.collidepoint(mouse)

            if p_active:
                bg = (85, 42, 54) if is_desert else (48, 92, 148)
                bdr = (255, 210, 85) if is_desert else (120, 240, 255)
                col = (255, 255, 255)
            elif p_hover:
                bg = (56, 28, 38) if is_desert else (32, 52, 82)
                bdr = (215, 140, 60) if is_desert else (80, 150, 220)
                col = (255, 240, 210) if is_desert else (220, 240, 255)
            else:
                bg = (32, 16, 24) if is_desert else (20, 30, 48)
                bdr = (85, 48, 42) if is_desert else (50, 75, 115)
                col = (205, 180, 160) if is_desert else (160, 190, 225)

            rrect(surf, pr, bg, radius=8, border=bdr, border_w=2 if p_active else 1)
            draw_text(surf, str(p + 1), theme.font(16, bold=True), col, pr.center, "center")

        # Nút mũi tên tới trang [ NEXT > ]
        next_enabled = (self.page < max_page)
        next_hover = self.btn_next_page.collidepoint(mouse) and next_enabled
        if next_enabled:
            next_bg = ((60, 32, 42) if is_desert else (38, 62, 98)) if next_hover else ((36, 18, 26) if is_desert else (22, 34, 54))
            next_bdr = (255, 195, 80) if is_desert else (100, 175, 240)
            next_col = (255, 255, 255)
        else:
            next_bg = (24, 14, 18) if is_desert else (16, 22, 36)
            next_bdr = (60, 36, 32) if is_desert else (35, 48, 70)
            next_col = (110, 95, 95) if is_desert else (85, 105, 130)
        rrect(surf, self.btn_next_page, next_bg, radius=8, border=next_bdr, border_w=1)
        draw_text(surf, "NEXT >", theme.font(15, bold=True), next_col, self.btn_next_page.center, "center")

        # Dòng thông tin số lượng màn chơi
        show_str = f"Showing stages {start_idx + 1} - {min(len(tab_levels), start_idx + self.levels_per_page)} of {len(tab_levels)}"
        draw_text(surf, show_str, theme.font(15), (180, 210, 240), (cx, py + 52), "center")
        hint_str = "[< / >] Prev / Next Page   |   [TAB] Switch Tab   |   [ESC] Return to Menu"
        draw_text(surf, hint_str, theme.font(14), theme.TEXT_FAINT, (cx, self.h - 28), "center")


# ---------------------------------------------------------------------------
# Màn hình Cài đặt Toàn diện chuẩn PC (Settings View chia 3 Tab)
# ---------------------------------------------------------------------------
class SettingsView:
    def __init__(self, app):
        self.app = app
        self.w, self.h = theme.WIDTH, theme.HEIGHT
        self.btn_back_rect = pygame.Rect(180, 80, 140, 46)
        self.tab = "audio_display"  # "audio_display" | "gameplay_hints" | "data_replay"
        self.tab_rects = {
            "audio_display": pygame.Rect(self.w // 2 - 300, 80, 190, 46),
            "gameplay_hints": pygame.Rect(self.w // 2 - 95, 80, 190, 46),
            "data_replay": pygame.Rect(self.w // 2 + 110, 80, 190, 46),
        }
        self.confirm_reset = False

    def handle(self, event: pygame.event.Event, mouse: Tuple[int, int]) -> bool:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
            self.app.settings.save()
            self.app.pop_screen()
            self.app.audio.play("swap")
            return True

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.btn_back_rect.collidepoint(mouse):
                self.app.settings.save()
                self.app.pop_screen()
                self.app.audio.play("swap")
                return True

            for tab_key, r in self.tab_rects.items():
                if r.collidepoint(mouse) and self.tab != tab_key:
                    self.tab = tab_key
                    self.confirm_reset = False
                    self.app.audio.play("swap")
                    return True

            cx = self.w // 2

            if self.tab == "audio_display":
                # Fullscreen
                if pygame.Rect(cx + 120, 240, 160, 42).collidepoint(mouse):
                    pygame.display.toggle_fullscreen()
                    self.app.audio.play("switch")
                    return True
                # Sound on/off
                if pygame.Rect(cx + 120, 310, 160, 42).collidepoint(mouse):
                    self.app._set_sound(not self.app.audio.enabled)
                    return True
                # Theme toggle
                if pygame.Rect(cx + 60, 560, 220, 42).collidepoint(mouse):
                    self.app.toggle_theme()
                    return True

            elif self.tab == "gameplay_hints":
                # Solution path
                if pygame.Rect(cx + 120, 240, 160, 40).collidepoint(mouse):
                    self.app.toggle_path()
                    return True
                # Compass
                if pygame.Rect(cx + 120, 300, 160, 40).collidepoint(mouse):
                    val = not self.app.settings.show_compass
                    self.app.settings.set("show_compass", val)
                    self.app.audio.play("switch")
                    return True
                # Camera help
                if pygame.Rect(cx + 120, 360, 160, 40).collidepoint(mouse):
                    val = not self.app.settings.show_camera_help
                    self.app.settings.set("show_camera_help", val)
                    self.app.audio.play("switch")
                    return True
                # Floor arrows
                if pygame.Rect(cx + 120, 420, 160, 40).collidepoint(mouse):
                    val = not self.app.settings.show_floor_arrows
                    self.app.settings.set("show_floor_arrows", val)
                    self.app.audio.play("switch")
                    return True
                # Link lines
                if pygame.Rect(cx + 120, 480, 160, 40).collidepoint(mouse):
                    val = not self.app.settings.show_link_lines
                    self.app.settings.set("show_link_lines", val)
                    self.app.audio.play("switch")
                    return True
                # Tips
                if pygame.Rect(cx + 120, 540, 160, 40).collidepoint(mouse):
                    val = not self.app.settings.show_tips
                    self.app.settings.set("show_tips", val)
                    self.app.audio.play("switch")
                    return True

            elif self.tab == "data_replay":
                # Reset progress
                reset_btn = pygame.Rect(cx - 150, 420, 300, 48)
                if reset_btn.collidepoint(mouse):
                    if not self.confirm_reset:
                        self.confirm_reset = True
                        self.app.audio.play("swap")
                    else:
                        self.app.progress._best.clear()
                        self.app.progress._save()
                        self.confirm_reset = False
                        self.app.toast("Progress has been reset!", theme.GOOD)
                        self.app.audio.play("switch")
                    return True

        if self.tab == "audio_display":
            # Volume slider
            self.app.volume_slider.rect = pygame.Rect(self.w // 2 + 50, 410, 260, 24)
            if self.app.volume_slider.handle(event, mouse):
                self.app.audio.set_volume(self.app.volume_slider.value)
                if not self.app.volume_slider.drag:
                    self.app.settings.set("volume", self.app.audio.volume)
                    self.app.audio.play("switch")
                return True

            # Tilt slider
            self.app.tilt_slider.rect = pygame.Rect(self.w // 2 + 50, 490, 260, 24)
            if self.app.tilt_slider.handle(event, mouse):
                self.app._set_tilt(self.app.tilt_slider.value)
                return True

        elif self.tab == "data_replay":
            # Replay speed slider
            sp_slider = getattr(self.app, "speed_slider", getattr(self.app, "slider", None))
            if sp_slider is not None:
                sp_slider.rect = pygame.Rect(self.w // 2 - 150, 310, 300, 26)
                if sp_slider.handle(event, mouse):
                    self.app.speed = sp_slider.value
                    if not sp_slider.drag:
                        self.app.settings.set("replay_speed", self.app.speed)
                    return True

        return False

    def update(self, dt: float, mouse: Tuple[int, int]):
        pass

    def draw(self, surf: pygame.Surface, mouse: Tuple[int, int]):
        surf.blit(self.app.bg, (0, 0))

        is_back_hover = self.btn_back_rect.collidepoint(mouse)
        back_bg = (34, 52, 82) if is_back_hover else (22, 34, 54)
        rrect(surf, self.btn_back_rect, back_bg, radius=8, border=(80, 150, 220), border_w=1)
        draw_text(surf, "< BACK", theme.font(18, bold=True), (240, 248, 255), self.btn_back_rect.center, "center")

        # 3 Tabs
        tab_names = {
            "audio_display": "AUDIO & DISPLAY",
            "gameplay_hints": "GAMEPLAY & HINTS",
            "data_replay": "DATA & REPLAY",
        }
        for tab_key, r in self.tab_rects.items():
            active = (self.tab == tab_key)
            is_hover = r.collidepoint(mouse)
            bg = (46, 88, 142) if active else ((32, 50, 78) if is_hover else (20, 30, 48))
            border = (120, 230, 255) if active else (56, 90, 135)
            rrect(surf, r, bg, radius=8, border=border, border_w=2 if active else 1)
            col = (255, 255, 255) if active else (175, 205, 235)
            draw_text(surf, tab_names[tab_key], theme.font(16, bold=True), col, r.center, "center")

        cx = self.w // 2
        panel_w, panel_h = 820, 560
        px = cx - panel_w // 2
        py = 180
        rrect(surf, (px, py, panel_w, panel_h), (20, 32, 54, 230), radius=16, border=(60, 95, 145), border_w=1)

        # TAB 1: AUDIO & DISPLAY
        if self.tab == "audio_display":
            draw_text(surf, "Display Mode", theme.font(20, bold=True), (225, 242, 255), (px + 70, 250))
            fs_rect = pygame.Rect(cx + 120, 240, 160, 42)
            rrect(surf, fs_rect, (30, 48, 80), radius=8, border=(80, 145, 215), border_w=1)
            is_fs = bool(self.app.screen.get_flags() & pygame.FULLSCREEN)
            draw_text(surf, "Fullscreen (F11)" if is_fs else "Windowed", theme.font(16, bold=True), (245, 252, 255), fs_rect.center, "center")

            draw_text(surf, "Audio Sound FX", theme.font(20, bold=True), (225, 242, 255), (px + 70, 320))
            snd_rect = pygame.Rect(cx + 120, 310, 160, 42)
            rrect(surf, snd_rect, (30, 48, 80), radius=8, border=(80, 145, 215), border_w=1)
            snd_label = "ENABLED (M)" if self.app.audio.enabled else "MUTED (M)"
            snd_col = (100, 250, 160) if self.app.audio.enabled else (255, 120, 120)
            draw_text(surf, snd_label, theme.font(16, bold=True), snd_col, snd_rect.center, "center")

            draw_text(surf, f"Master Volume: {int(self.app.audio.volume * 100)}%", theme.font(20, bold=True), (225, 242, 255), (px + 70, 410))
            self.app.volume_slider.rect = pygame.Rect(cx + 50, 410, 260, 24)
            self.app.volume_slider.draw(surf)

            draw_text(surf, f"Camera Tilt: {int(self.app.settings.tilt_deg)} deg", theme.font(20, bold=True), (225, 242, 255), (px + 70, 490))
            self.app.tilt_slider.rect = pygame.Rect(cx + 50, 490, 260, 24)
            self.app.tilt_slider.draw(surf)

            draw_text(surf, "Visual World Theme", theme.font(20, bold=True), (225, 242, 255), (px + 70, 570))
            theme_rect = pygame.Rect(cx + 60, 560, 220, 42)
            is_desert = (self.app.current_theme == "desert")
            bg_btn = (65, 34, 46) if is_desert else (30, 48, 80)
            bdr_btn = (215, 140, 60) if is_desert else (80, 145, 215)
            rrect(surf, theme_rect, bg_btn, radius=8, border=bdr_btn, border_w=1)
            theme_text = "DESERT (CACTUS)" if is_desert else "ARCTIC (PENGUIN)"
            theme_col = (255, 205, 85) if is_desert else (120, 245, 255)
            draw_text(surf, theme_text, theme.font(15, bold=True), theme_col, theme_rect.center, "center")

        # TAB 2: GAMEPLAY & HINTS
        elif self.tab == "gameplay_hints":
            hints = [
                ("Solution Path Overlay", self.app.show_path, 240),
                ("Move Keys Compass", self.app.settings.show_compass, 300),
                ("Camera Orbit Help", self.app.settings.show_camera_help, 360),
                ("Floor Movement Arrows", self.app.settings.show_floor_arrows, 420),
                ("Switch-to-Bridge Links", self.app.settings.show_link_lines, 480),
                ("Beginner Mechanism Tips", self.app.settings.show_tips, 540),
            ]
            for label, is_on, y_pos in hints:
                draw_text(surf, label, theme.font(19, bold=True), (225, 242, 255), (px + 70, y_pos + 8))
                btn_r = pygame.Rect(cx + 120, y_pos, 160, 38)
                rrect(surf, btn_r, (30, 48, 80), radius=8, border=(80, 145, 215), border_w=1)
                lbl = "ON" if is_on else "OFF"
                col = (100, 250, 160) if is_on else (160, 185, 215)
                draw_text(surf, lbl, theme.font(16, bold=True), col, btn_r.center, "center")

        # TAB 3: DATA & REPLAY
        elif self.tab == "data_replay":
            draw_text(surf, "Solver Replay Speed", theme.font(22, bold=True), (225, 242, 255), (cx, 260), "center")
            sp_slider = getattr(self.app, "speed_slider", getattr(self.app, "slider", None))
            if sp_slider is not None:
                sp_slider.rect = pygame.Rect(cx - 150, 310, 300, 26)
                sp_slider.draw(surf)

            draw_text(surf, "Campaign Saved Progress", theme.font(22, bold=True), (225, 242, 255), (cx, 380), "center")
            reset_btn = pygame.Rect(cx - 150, 420, 300, 48)
            btn_bg = (90, 32, 42) if self.confirm_reset else (34, 52, 84)
            btn_bdr = (255, 95, 115) if self.confirm_reset else (75, 135, 205)
            rrect(surf, reset_btn, btn_bg, radius=10, border=btn_bdr, border_w=1)
            reset_lbl = "Click Again to Confirm Reset!" if self.confirm_reset else "Reset All Cleared Levels"
            draw_text(surf, reset_lbl, theme.font(16, bold=True), (255, 255, 255), reset_btn.center, "center")

        draw_text(surf, "Settings are saved automatically upon return.", theme.font(15), (135, 175, 215), (cx, py + panel_h - 40), "center")


# ---------------------------------------------------------------------------
# Menu Tạm dừng (Pause Menu)
# ---------------------------------------------------------------------------
class PauseMenu:
    def __init__(self, app):
        self.app = app
        self.w, self.h = theme.WIDTH, theme.HEIGHT
        self.items = [
            ("resume", "RESUME"),
            ("restart", "RESTART"),
            ("level_select", "LEVEL SELECT"),
            ("settings", "SETTINGS"),
            ("main_menu", "MAIN MENU"),
        ]
        self.selected_idx = 0
        self.hovered_idx = -1
        self.keyboard_mode = False
        self.hover_progress = [0.0] * len(self.items)
        self.item_rects: List[pygame.Rect] = []

    def handle(self, event: pygame.event.Event, mouse: Tuple[int, int]) -> bool:
        if event.type == pygame.KEYDOWN:
            self.keyboard_mode = True
            if event.key in (pygame.K_UP, pygame.K_w):
                self.selected_idx = (self.selected_idx - 1) % len(self.items)
                self.app.audio.play("swap")
                return True
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected_idx = (self.selected_idx + 1) % len(self.items)
                self.app.audio.play("swap")
                return True
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self._activate_item(self.items[self.selected_idx][0])
                return True
            elif event.key == pygame.K_ESCAPE:
                self._activate_item("resume")
                return True

        if event.type == pygame.MOUSEMOTION:
            found = -1
            for idx, r in enumerate(self.item_rects):
                if r.collidepoint(mouse):
                    found = idx
                    break
            if found != self.hovered_idx:
                if found != -1:
                    self.selected_idx = found
                    self.keyboard_mode = False
                    self.app.audio.play("swap")
                self.hovered_idx = found

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for idx, r in enumerate(self.item_rects):
                if r.collidepoint(mouse):
                    self.selected_idx = idx
                    self._activate_item(self.items[idx][0])
                    return True

        return False

    def _activate_item(self, action_id: str):
        self.app.audio.play("switch")
        if action_id == "resume":
            self.app.pop_screen()
        elif action_id == "restart":
            self.app.pop_screen()
            self.app.restart()
        elif action_id == "level_select":
            self.app.push_screen("level_select")
        elif action_id == "settings":
            self.app.push_screen("settings")
        elif action_id == "main_menu":
            self.app.screen_stack = ["menu"]
            self.app.screen_state = "menu"

    def update(self, dt: float, mouse: Tuple[int, int]):
        mouse_over_any = any(r.collidepoint(mouse) for r in self.item_rects)
        if not mouse_over_any and not self.keyboard_mode:
            self.hovered_idx = -1

        for i in range(len(self.items)):
            if self.keyboard_mode:
                target = 1.0 if (i == self.selected_idx) else 0.0
            else:
                target = 1.0 if (i == self.hovered_idx) else 0.0

            speed = 28.0 if target > self.hover_progress[i] else 24.0
            self.hover_progress[i] += (target - self.hover_progress[i]) * min(1.0, dt * speed)

    def draw(self, surf: pygame.Surface, mouse: Tuple[int, int]):
        overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        overlay.fill((10, 18, 32, 195))
        surf.blit(overlay, (0, 0))

        card_w, card_h = 460, 520
        cx = (self.w - card_w) // 2
        cy = (self.h - card_h) // 2
        card_rect = pygame.Rect(cx, cy, card_w, card_h)
        is_desert = (self.app.current_theme == "desert")

        bg_card = (52, 26, 36, 245) if is_desert else (20, 32, 52, 245)
        bdr_card = (215, 140, 60) if is_desert else (80, 160, 230)
        rrect(surf, card_rect, bg_card, radius=16, border=bdr_card, border_w=2)

        draw_text(surf, "PAUSED", theme.font(36, bold=True), (255, 245, 240) if is_desert else (235, 248, 255), (cx + card_w // 2, cy + 42), "center")
        line_col = (135, 75, 45) if is_desert else (50, 85, 128)
        pygame.draw.line(surf, line_col, (cx + 50, cy + 85), (cx + card_w - 50, cy + 85), 2)

        start_y = cy + 120
        btn_w = 340
        btn_h = 54
        spacing = 68
        btn_x = cx + (card_w - btn_w) // 2

        self.item_rects = []
        for i, (action_id, label) in enumerate(self.items):
            cur_y = start_y + i * spacing
            t = self.hover_progress[i]
            r = pygame.Rect(btn_x, cur_y, btn_w, btn_h)
            self.item_rects.append(r)

            if t > 0.01:
                if is_desert:
                    bg_col = (
                        int(42 + 45 * t),
                        int(24 + 35 * t),
                        int(32 + 35 * t),
                        int(180 + 75 * t),
                    )
                    border_col = (
                        int(170 + 85 * t),
                        int(95 + 110 * t),
                        int(45 + 50 * t),
                    )
                    glow_col = (255, 195, 75)
                else:
                    bg_col = (
                        int(22 + 35 * t),
                        int(34 + 55 * t),
                        int(58 + 85 * t),
                        int(180 + 75 * t),
                    )
                    border_col = (
                        int(80 + 170 * t),
                        int(130 + 125 * t),
                        int(190 + 65 * t),
                    )
                    glow_col = (120, 245, 255)
                rrect(surf, r, bg_col, radius=10, border=border_col, border_w=2)
                dx, dy = r.x + 22, r.centery
                pts = [(dx, dy - 5), (dx + 5, dy), (dx, dy + 5), (dx - 5, dy)]
                gfx.filled_polygon(surf, pts, glow_col)
                text_col = (255, 255, 255)
            else:
                bg_col = (36, 18, 26, 160) if is_desert else (22, 32, 52, 160)
                border_col = (82, 45, 40) if is_desert else (50, 72, 105)
                rrect(surf, r, bg_col, radius=10, border=border_col, border_w=1)
                text_col = (240, 205, 175) if is_desert else (185, 210, 240)

            draw_text(surf, label, theme.font(21, bold=True), text_col, (r.centerx, r.centery), "center")


# ---------------------------------------------------------------------------
# Màn hình Chúc mừng Chiến thắng (Win Overlay)
# ---------------------------------------------------------------------------
class WinOverlay:
    def __init__(self, app):
        self.app = app
        self.w, self.h = theme.WIDTH, theme.HEIGHT
        self.items = [("next", "NEXT LEVEL"), ("retry", "REPLAY"), ("select", "LEVEL SELECT")]
        self.hovered_idx = -1
        self.item_rects: List[pygame.Rect] = []

    def handle(self, event: pygame.event.Event, mouse: Tuple[int, int]) -> bool:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.app.next_level()
                return True
            elif event.key == pygame.K_r:
                self.app.restart()
                return True
            elif event.key in (pygame.K_n, pygame.K_ESCAPE):
                self.app.screen_state = "level_select"
                return True

        if event.type == pygame.MOUSEMOTION:
            found = -1
            for idx, r in enumerate(self.item_rects):
                if r.collidepoint(mouse):
                    found = idx
                    break
            self.hovered_idx = found

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for idx, r in enumerate(self.item_rects):
                if r.collidepoint(mouse):
                    act = self.items[idx][0]
                    if act == "next":
                        self.app.next_level()
                    elif act == "retry":
                        self.app.restart()
                    elif act == "select":
                        self.app.screen_state = "level_select"
                    return True

        return False

    def draw(self, surf: pygame.Surface, mouse: Tuple[int, int]):
        overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        is_desert = (self.app.current_theme == "desert")
        overlay.fill((22, 12, 18, 195) if is_desert else (8, 14, 26, 185))
        surf.blit(overlay, (0, 0))

        cw, ch = 560, 420
        cx = (self.w - cw) // 2
        cy = (self.h - ch) // 2
        card_bg = (56, 32, 42, 250) if is_desert else (20, 32, 54, 250)
        card_bdr = (255, 195, 75) if is_desert else (95, 230, 170)
        rrect(surf, (cx, cy, cw, ch), card_bg, radius=16, border=card_bdr, border_w=2)

        title_col = (255, 215, 85) if is_desert else (120, 250, 180)
        draw_text(surf, "LEVEL CLEARED!", theme.font(36, bold=True), title_col, (cx + cw // 2, cy + 45), "center")
        line_col = (145, 80, 50) if is_desert else (45, 95, 75)
        pygame.draw.line(surf, line_col, (cx + 60, cy + 90), (cx + cw - 60, cy + 90), 2)

        moves = self.app.session.moves
        best = self.app.progress.best(self.app.level.name)
        draw_text(surf, f"Moves Taken: {moves}", theme.font(24, bold=True), (245, 250, 255), (cx + cw // 2, cy + 135), "center")

        is_new_record = (best is not None and moves <= best)
        best_str = f"Best Record: {best if best is not None else moves}"
        draw_text(surf, best_str, theme.font(20), (255, 220, 100) if is_new_record else (175, 205, 235), (cx + cw // 2, cy + 175), "center")
        if is_new_record:
            draw_text(surf, "NEW PERSONAL BEST!", theme.font(16, bold=True), (255, 220, 100), (cx + cw // 2, cy + 210), "center")

        btn_w = 150
        btn_h = 48
        spacing = 18
        total_w = len(self.items) * btn_w + (len(self.items) - 1) * spacing
        bx_start = cx + (cw - total_w) // 2
        by = cy + ch - 80

        self.item_rects = []
        for i, (act, label) in enumerate(self.items):
            r = pygame.Rect(bx_start + i * (btn_w + spacing), by, btn_w, btn_h)
            self.item_rects.append(r)
            is_hover = (i == self.hovered_idx)
            is_primary = (act == "next")

            if is_primary:
                if is_desert:
                    bg = (185, 95, 45) if is_hover else (150, 72, 32)
                    border = (255, 205, 95)
                else:
                    bg = (44, 150, 95) if is_hover else (34, 120, 75)
                    border = (120, 250, 180)
            else:
                if is_desert:
                    bg = (68, 36, 46) if is_hover else (48, 24, 34)
                    border = (195, 115, 65)
                else:
                    bg = (38, 56, 88) if is_hover else (24, 36, 58)
                    border = (80, 145, 210)

            rrect(surf, r, bg, radius=8, border=border, border_w=1)
            draw_text(surf, label, theme.font(16, bold=True), (255, 255, 255), r.center, "center")
