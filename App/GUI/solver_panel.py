"""Bảng điều khiển Thuật toán AI (AI Solver Drawer) chuyên dụng.

Thiết kế chuẩn Indie Game:
- Bố cục rộng rãi (560px), thoáng đãng, tuyệt đối không đè chữ, không lỗi ký tự.
- 4 nút thuật toán lớn (BFS, DFS, UCS, A*) có phân cấp màu sắc rõ rệt.
- Trình chọn Heuristic trực quan cho A*.
- Nút Benchmark / Đua thuật toán thời gian thực ([RACE]).
- Bộ điều khiển Replay trực quan với thanh tiến trình và thanh tốc độ độc lập.
- Thẻ số liệu Telemetry rộng rãi hiển thị đầy đủ thông số lời giải.
"""

from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pygame

from App.GUI import theme
from App.GUI.widgets import Button, Slider, draw_text, rrect, wrap_text
from App.Game.solver_bridge import available_heuristics

SOLVER_ORDER = ["BFS", "DFS", "UCS", "A*"]
SOLVER_COLORS = {
    "BFS": (80, 225, 255),
    "DFS": (255, 130, 90),
    "UCS": (130, 245, 160),
    "A*": (255, 215, 60),
}
SOLVER_SUB = {
    "BFS": "Shortest path",
    "DFS": "Deep branch",
    "UCS": "Optimal cost g(n)",
    "A*": "Heuristic f = g + h",
}


class SolverDrawer:
    def __init__(self, app):
        self.app = app
        self.w = 560
        self.h = theme.HEIGHT - 48
        self.x = theme.WIDTH - self.w - 28
        self.y = 24
        self.rect = pygame.Rect(self.x, self.y, self.w, self.h)

        x0 = self.x + 24
        pw = self.w - 48
        self.x0, self.pw = x0, pw

        # Nút đóng bảng chuyên biệt (ASCII an toàn tuyệt đối)
        self.btn_close = Button(
            (self.rect.right - 116, self.rect.y + 18, 92, 36),
            "Close", self._close, font_size=15,
        )

        # 4 nút thuật toán lớn, thoáng đẹp, bố cục 2x2
        self.solver_buttons: Dict[str, Button] = {}
        sw = (pw - 12) // 2
        for i, name in enumerate(SOLVER_ORDER):
            bx = x0 + (i % 2) * (sw + 12)
            by = self.rect.y + 184 + (i // 2) * 68
            self.solver_buttons[name] = Button(
                (bx, by, sw, 60), name,
                lambda n=name: self._on_solver_click(n),
                "secondary",
                accent=SOLVER_COLORS[name],
                sublabel=SOLVER_SUB[name],
                font_size=20,
            )

        # Nút chọn Heuristic cho A*
        self.show_heuristic_button = False
        self.heuristic_menu_open = False
        self.btn_heuristic = Button(
            (x0, self.rect.y + 328, pw, 38),
            f"Heuristic: {self._heuristic_label()}  [v]",
            self._toggle_heuristic_menu,
            font_size=14,
        )

        # Nút Đua / So sánh
        self.btn_compare = Button(
            (x0, self.rect.y + 372, pw, 44),
            "[RACE] Benchmark & Compare",
            self._open_compare,
            style="primary",
            font_size=16,
        )

        # Nút điều khiển Replay
        ry = self.rect.y + 448
        bw_s = 52
        bw_pp = 152
        bw_path = 144
        gap = 8
        self.btn_restart_replay = Button((x0, ry, bw_s, 40), "|<", self._restart_replay, tooltip="Restart Replay", font_size=16)
        self.btn_step_back = Button((x0 + bw_s + gap, ry, bw_s, 40), "<", lambda: self.app._request_step(-1), tooltip="Step back (,)", font_size=18)
        self.btn_play_pause = Button((x0 + (bw_s + gap) * 2, ry, bw_pp, 40), "Pause", self.app.toggle_pause, font_size=15)
        self.btn_step_fwd = Button((x0 + (bw_s + gap) * 2 + bw_pp + gap, ry, bw_s, 40), ">", lambda: self.app._request_step(1), tooltip="Step fwd (.)", font_size=18)
        self.btn_path = Button((x0 + pw - bw_path, ry, bw_path, 40), "Path: ON", self.app.toggle_path, tooltip="Toggle path (V)", font_size=14)

        # Slider renders its label and value on one line above the track.
        self.slider = Slider((x0, self.rect.y + 558, pw, 18), 0.5, 4.0, self.app.speed, label="Replay Speed", fmt="{:.2f}x")

        # Thẻ thông số Telemetry
        self.stats_box = pygame.Rect(x0, self.rect.y + 618, pw, self.h - 644)

    def _close(self):
        self.app.show_ai_panel = False
        self.heuristic_menu_open = False
        self.show_heuristic_button = False
        self.app.audio.play("switch")

    def _on_solver_click(self, name: str):
        if name == "A*":
            # Reveal A*'s heuristic control only after A* is selected.
            self.show_heuristic_button = True
            self.heuristic_menu_open = False
        else:
            self.show_heuristic_button = False
            self.heuristic_menu_open = False
            self.app.start_solver(name)

    def _toggle_heuristic_menu(self):
        self.heuristic_menu_open = not self.heuristic_menu_open
        self.app.audio.play("swap")

    def _heuristic_label(self) -> str:
        return self.app.heuristic.replace("_", " ").title()

    def _open_compare(self):
        self.heuristic_menu_open = False
        self.app.open_compare()

    def _restart_replay(self):
        if self.app.stats and self.app.stats.found:
            self.app.restart()
            self.app._begin_replay(self.app.stats.label, self.app.stats.actions)

    def _heuristic_options_rects(self) -> List[Tuple[str, pygame.Rect]]:
        opts = available_heuristics()
        btn_r = self.btn_heuristic.rect
        row_h = 38
        rects = []
        for i, opt in enumerate(opts):
            r = pygame.Rect(btn_r.x, btn_r.bottom + 4 + i * row_h, btn_r.w, row_h)
            rects.append((opt, r))
        return rects

    def handle(self, event: pygame.event.Event, mouse: Tuple[int, int]) -> bool:
        """Xử lý sự kiện chuột và phím riêng cho AI Drawer."""
        # 1. Click bên ngoài drawer: Đóng drawer ngay
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if not self.rect.collidepoint(mouse):
                self._close()
                return True

        # 2. Xử lý popup chọn Heuristic nếu đang mở
        if self.heuristic_menu_open:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                clicked_opt = False
                for opt, r in self._heuristic_options_rects():
                    if r.collidepoint(mouse):
                        self.app.set_heuristic(opt)
                        self.heuristic_menu_open = False
                        self.show_heuristic_button = False
                        self.btn_heuristic.label = f"Heuristic: {self._heuristic_label()}  [v]"
                        self.app.audio.play("switch")
                        self.app.start_solver("A*")
                        clicked_opt = True
                        break
                if not clicked_opt and not self.btn_heuristic.rect.collidepoint(mouse):
                    self.heuristic_menu_open = False
                return True

        # 3. Nút đóng
        if self.btn_close.handle(event, mouse):
            return True

        # 4. Các nút thuật toán
        if self.show_heuristic_button and self.btn_heuristic.handle(event, mouse):
            return True

        for b in self.solver_buttons.values():
            if b.handle(event, mouse):
                return True

        if self.btn_compare.handle(event, mouse):
            return True

        # 5. Các nút Replay
        for b in (self.btn_restart_replay, self.btn_step_back, self.btn_play_pause, self.btn_step_fwd, self.btn_path):
            if b.handle(event, mouse):
                return True

        # 6. Thanh trượt tốc độ
        if self.slider.handle(event, mouse):
            self.app.speed = self.slider.value
            if not self.slider.drag:
                self.app.settings.set("replay_speed", self.app.speed)
            return True

        # Hấp thu toàn bộ sự kiện chuột khi click trong Drawer (chống click lọt xuống bàn cờ)
        if self.rect.collidepoint(mouse):
            return True

        return False

    def update(self, dt: float, mouse: Tuple[int, int]):
        """Cập nhật trạng thái hover và tính khả dụng của các nút."""
        busy_job = self.app.job is not None and not self.app.job.done
        avail = self.app.available

        for name, b in self.solver_buttons.items():
            b.enabled = (not busy_job) and avail
            b.update(dt, mouse)

        self.btn_heuristic.label = f"Heuristic: {self._heuristic_label()}  [v]"
        self.btn_heuristic.enabled = self.show_heuristic_button and (not busy_job) and avail
        if self.show_heuristic_button:
            self.btn_heuristic.update(dt, mouse)

        self.btn_compare.enabled = (not busy_job) and avail
        self.btn_compare.update(dt, mouse)
        self.btn_close.update(dt, mouse)

        has_replay = bool(self.app.replay) or bool(self.app.replay_done)
        self.btn_restart_replay.enabled = bool(self.app.stats and self.app.stats.found)
        self.btn_restart_replay.update(dt, mouse)
        self.btn_step_back.enabled = bool(self.app.replay_done)
        self.btn_step_back.update(dt, mouse)
        self.btn_play_pause.enabled = has_replay
        self.btn_play_pause.label = "Resume" if (self.app.paused and has_replay) else "Pause"
        self.btn_play_pause.update(dt, mouse)
        self.btn_step_fwd.enabled = has_replay
        self.btn_step_fwd.update(dt, mouse)
        self.btn_path.label = "Path: ON" if self.app.show_path else "Path: OFF"
        self.btn_path.update(dt, mouse)

    def draw(self, surf: pygame.Surface, mouse: Tuple[int, int]):
        """Vẽ Drawer bóng mờ và toàn bộ nội dung phòng thí nghiệm AI."""
        is_desert = (self.app.current_theme == "desert")

        # 1. Lớp phủ mờ nền bàn cờ (Backdrop veil)
        backdrop = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        backdrop.fill((8, 14, 26, 120))
        surf.blit(backdrop, (0, 0))

        # 2. Khung viền Drawer phong cách Bắc cực / Sa mạc
        panel_bg = (34, 18, 28, 252) if is_desert else (14, 22, 38, 250)
        panel_border = (215, 140, 60) if is_desert else (75, 145, 225)
        top_glow = (255, 205, 80) if is_desert else (120, 240, 255)
        accent_title = (255, 215, 120) if is_desert else (120, 240, 255)

        rrect(surf, self.rect, panel_bg, radius=18, border=panel_border, border_w=2)
        pygame.draw.line(surf, top_glow, (self.rect.x + 24, self.rect.y + 2), (self.rect.right - 24, self.rect.y + 2), 2)

        x0, w = self.x0, self.pw

        # 3. Tiêu đề Header & Nút đóng
        draw_text(surf, "[ AI SOLVER EXPEDITION ]", theme.font(13, True), accent_title, (x0, self.rect.y + 16))
        draw_text(surf, "ALGORITHM LAB", theme.font(24, True), (245, 252, 255), (x0, self.rect.y + 36))
        self.btn_close.draw(surf)

        pygame.draw.line(surf, (60, 40, 52) if is_desert else (45, 75, 115), (x0, self.rect.y + 76), (x0 + w, self.rect.y + 76), 1)

        # 4. Thẻ tóm tắt màn chơi (Stage Summary Card)
        lv = self.app.level
        card = pygame.Rect(x0, self.rect.y + 86, w, 64)
        card_bg = (48, 26, 38, 220) if is_desert else (20, 32, 54, 220)
        card_bdr = (110, 65, 55) if is_desert else (50, 80, 125)
        rrect(surf, card, card_bg, radius=12, border=card_bdr, border_w=1)
        draw_text(surf, lv.name, theme.font(18, True), (245, 252, 255), (card.x + 16, card.y + 12))
        col = theme.group_color(lv.group)
        draw_text(surf, f"[{lv.group.upper()}]", theme.font(13, True), col, (card.x + 16, card.y + 36))
        draw_text(surf, f"MOVES: {self.app.session.moves}", theme.font(20, True), accent_title, (card.right - 16, card.centery), "midright")

        # 5. Khu vực chọn thuật toán
        draw_text(surf, "SELECT SEARCH ALGORITHM", theme.font(13, True), accent_title, (x0, self.rect.y + 164))
        for b in self.solver_buttons.values():
            b.draw(surf)
        if self.show_heuristic_button:
            self.btn_heuristic.draw(surf)
        self.btn_compare.draw(surf)

        # 6. Khu vực Replay & tua bước
        draw_text(surf, "SOLUTION PLAYBACK & TRANSPORT", theme.font(13, True), accent_title, (x0, self.rect.y + 428))
        for b in (self.btn_restart_replay, self.btn_step_back, self.btn_play_pause, self.btn_step_fwd, self.btn_path):
            b.draw(surf)

        # Thanh tiến trình Replay độc lập (không bị đè)
        if self.app.replay or (self.app.stats and self.app.stats.found):
            done = self.app.replay_total - len(self.app.replay) if self.app.replay else len(self.app.replay_done)
            tot = max(1, self.app.replay_total if self.app.replay else (len(self.app.stats.actions) if self.app.stats else 1))
            lbl = self.app.replay_label or (self.app.stats.label if self.app.stats else "Solution")
            draw_text(surf, f"{lbl} Replay", theme.font(13, True), accent_title, (x0, self.rect.y + 500))
            draw_text(surf, f"Step {done} / {tot}", theme.mono(14, True), (240, 250, 255), (x0 + w, self.rect.y + 500), "topright")
            bar_bg = pygame.Rect(x0, self.rect.y + 520, w, 6)
            rrect(surf, bar_bg, (40, 25, 35) if is_desert else (30, 45, 70), radius=3)
            prog_w = int(w * min(1.0, done / tot))
            if prog_w > 0:
                rrect(surf, (x0, self.rect.y + 520, prog_w, 6), accent_title, radius=3)

        # Replay speed label and value are rendered by the slider without overlap.
        self.slider.draw(surf)

        # 7. Khu vực Telemetry & Số liệu
        draw_text(surf, "SOLVER TELEMETRY & METRICS", theme.font(13, True), accent_title, (x0, self.rect.y + 596))
        box = self.stats_box
        box_bg = (28, 16, 26, 230) if is_desert else (18, 28, 48, 225)
        box_bdr = (100, 58, 50) if is_desert else (50, 80, 125)
        rrect(surf, box, box_bg, radius=14, border=box_bdr, border_w=1)

        job = self.app.job
        stats = self.app.stats

        if job is not None and not job.done:
            ang = pygame.time.get_ticks() / 140
            c = (box.x + 36, box.y + 40)
            for k in range(8):
                a = ang + k * math.tau / 8
                col_pt = theme.mix((50, 30, 40), (255, 205, 80), (k + 1) / 8) if is_desert else theme.mix((30, 50, 80), (120, 240, 255), (k + 1) / 8)
                pygame.draw.circle(
                    surf, col_pt,
                    (int(c[0] + 13 * math.cos(a)), int(c[1] + 13 * math.sin(a))), 3,
                )
            draw_text(surf, f"{job.label} searching...", theme.font(20, True), theme.TEXT, (box.x + 64, box.y + 26))
            draw_text(surf, "Exploring state space in real-time...", theme.font(14), theme.TEXT_DIM, (box.x + 64, box.y + 52))
        elif stats is None:
            draw_text(surf, "Algorithm Lab Briefing", theme.font(18, True), (245, 252, 255), (box.x + 18, box.y + 16))
            pygame.draw.line(surf, (70, 45, 55) if is_desert else (40, 65, 100), (box.x + 16, box.y + 44), (box.right - 16, box.y + 44), 1)
            tips = [
                ("BFS", "Breadth-First", "Shortest step count guarantee"),
                ("DFS", "Depth-First", "Rapid deep branch exploration"),
                ("UCS", "Uniform-Cost", "Optimal cost priority queue g(n)"),
                ("A*", "A* Heuristic", "Guided by f(n) = g(n) + h(n)"),
            ]
            for idx, (code, title, desc) in enumerate(tips):
                row_y = box.y + 54 + idx * 58
                tag_bg = (40, 24, 34) if is_desert else (24, 38, 64)
                tag_bdr = (90, 50, 45) if is_desert else (50, 80, 120)
                rrect(surf, (box.x + 16, row_y, box.w - 32, 50), tag_bg, radius=8, border=tag_bdr, border_w=1)

                pill_r = pygame.Rect(box.x + 24, row_y + 10, 50, 30)
                rrect(surf, pill_r, SOLVER_COLORS[code], radius=6)
                draw_text(surf, code, theme.font(14, True), (18, 22, 32), pill_r.center, "center")

                draw_text(surf, title, theme.font(15, True), (240, 248, 255), (box.x + 86, row_y + 8))
                draw_text(surf, desc, theme.font(13), (170, 195, 220), (box.x + 86, row_y + 28))

            hint_txt = "Select any search algorithm above to begin."
            draw_text(surf, hint_txt, theme.font(13), theme.TEXT_FAINT, (box.x + 18, box.bottom - 22))
        elif stats.error:
            draw_text(surf, f"{stats.label} error", theme.font(19, True), theme.BAD, (box.x + 18, box.y + 16))
            for i, line in enumerate(wrap_text(stats.error, theme.font(14), box.w - 36)[:4]):
                draw_text(surf, line, theme.font(14), theme.TEXT_DIM, (box.x + 18, box.y + 52 + i * 22))
        elif not stats.found:
            draw_text(surf, stats.label, theme.font(19, True), theme.TEXT, (box.x + 18, box.y + 16))
            draw_text(surf, "No solution exists for this level.", theme.font(17), theme.BAD, (box.x + 18, box.y + 52))
        else:
            # Header kết quả: Tag trạng thái và tên thuật toán riêng biệt
            draw_text(surf, "SEARCH RESULT", theme.font(12, True), (160, 185, 215), (box.x + 18, box.y + 14))
            pill_rect = pygame.Rect(box.right - 108, box.y + 12, 90, 24)
            rrect(surf, pill_rect, (20, 60, 45), radius=6, border=(60, 220, 140), border_w=1)
            draw_text(surf, "SOLVED", theme.font(13, True), (80, 245, 160), pill_rect.center, "center")

            # Tên thuật toán chiếm toàn bộ bề ngang
            draw_text(surf, stats.label, theme.font(19, True), accent_title, (box.x + 18, box.y + 36))
            pygame.draw.line(surf, (70, 45, 55) if is_desert else (40, 65, 100), (box.x + 16, box.y + 64), (box.right - 16, box.y + 64), 1)

            rows = self.app._stat_rows() or []
            for i, (k, v) in enumerate(rows):
                y = box.y + 74 + i * 44
                row_bg = (36, 20, 30, 140) if (is_desert and i % 2 == 1) else ((24, 36, 58, 140) if i % 2 == 1 else (0, 0, 0, 0))
                if row_bg[3] > 0:
                    rrect(surf, (box.x + 10, y - 4, box.w - 20, 38), row_bg, radius=6)
                draw_text(surf, k, theme.font(15), (180, 202, 228), (box.x + 18, y + 4))
                draw_text(surf, v, theme.mono(16, True), (245, 252, 255), (box.right - 18, y + 4), "topright")

        # 8. Chú thích phím tắt chân bảng
        hint = "[ESC] Close Drawer   |   [V] Solution Path   |   [P] Pause Replay"
        draw_text(surf, hint, theme.font(13), theme.TEXT_FAINT, (x0 + w // 2, self.rect.bottom - 16), "center")

        # 9. Vẽ menu Heuristic thả xuống (nếu đang mở)
        if self.heuristic_menu_open:
            rects = self._heuristic_options_rects()
            popup_panel = pygame.Rect(rects[0][1].x, rects[0][1].y, rects[0][1].w, sum(r.h for _, r in rects) + 4)
            rrect(surf, popup_panel, (24, 14, 22, 254) if is_desert else (18, 28, 48, 252), radius=10, border=panel_border, border_w=2)
            for opt, r in rects:
                hot = r.collidepoint(mouse)
                selected = (opt == self.app.heuristic)
                if hot or selected:
                    inner = r.inflate(-6, -4)
                    rrect(surf, inner, (75, 42, 54) if (is_desert and selected) else ((40, 80, 130) if selected else (30, 50, 80)), radius=6)
                lbl = opt.replace("_", " ").title()
                col = (255, 255, 255) if (hot or selected) else (180, 210, 240)
                draw_text(surf, lbl, theme.font(15, bold=True), col, (r.x + 14, r.centery), anchor="midleft")
                if selected:
                    draw_text(surf, "*", theme.font(18, bold=True), (100, 250, 160), (r.right - 14, r.centery), anchor="midright")
