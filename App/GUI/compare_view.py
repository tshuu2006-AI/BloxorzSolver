"""Bảng so sánh các thuật toán (cửa sổ phủ lên game): số liệu từng solver, tô giá trị tốt nhất,
thanh so sánh theo thang log, bấm vào một dòng để xem lại lời giải của solver đó."""

from __future__ import annotations

import math
from typing import Callable, Dict, List

import pygame

from App.GUI import theme
from App.GUI.widgets import Button, draw_text, rrect, wrap_text
from App.Game.compare import best_marks, summary_line, usable

PANEL = pygame.Rect(150, 110, 1620, 860)
ROW_H = 84
ROW_GAP = 10
FIRST_ROW_Y = PANEL.y + 214

# (khoá, tiêu đề, x tương đối của cột, bề rộng thanh)
BAR_COLS = (("expanded", "Expanded nodes", 590, 280), ("time_ms", "Search time", 930, 280), ("memory_kb", "Peak memory", 1270, 280))


def fmt_value(key: str, v) -> str:
    if v in (None, ""):
        return "-"
    if key == "time_ms":
        return f"{v / 1000:.2f} s" if v >= 1000 else f"{v:.2f} ms"
    if key == "memory_kb":
        return f"{v / 1024:.2f} MB" if v >= 1024 else f"{v:.1f} KB"
    if key == "expanded":
        return f"{int(v):,}"
    return str(v)


def bar_fraction(v: float, lo: float, hi: float) -> float:
    """Độ dài thanh theo thang log trong [0.12, 1]; mọi giá trị bằng nhau thì thanh nửa."""
    if hi <= lo or lo <= 0 or v <= 0:
        return 0.5
    return 0.12 + 0.88 * (math.log(v) - math.log(lo)) / (math.log(hi) - math.log(lo))


class CompareView:
    def __init__(
        self,
        on_replay: Callable[[Dict], None],
        on_rerun: Callable[[], None],
        on_save: Callable[[], None],
        on_close: Callable[[], None],
        on_race: Callable[[Dict, Dict], None],
    ):
        self.on_replay = on_replay
        self.on_race = on_race
        self.selected: List[str] = []  # nhãn các thuật toán được tích để đua (tối đa 2)
        self.cb_rects: Dict[str, pygame.Rect] = {}
        self._rows: Dict[str, Dict] = {}
        self.rows_rects: Dict[str, pygame.Rect] = {}
        self.btn_rerun = Button((PANEL.x + 40, PANEL.bottom - 84, 190, 52), "Run again", on_rerun)
        self.btn_save = Button((PANEL.x + 250, PANEL.bottom - 84, 190, 52), "Save CSV", on_save)
        self.btn_race = Button((PANEL.x + 460, PANEL.bottom - 84, 230, 52), "Race selected", self._do_race)
        self.btn_close = Button((PANEL.right - 230, PANEL.bottom - 84, 190, 52), "Close", on_close, "primary")
        self.buttons = [self.btn_rerun, self.btn_save, self.btn_race, self.btn_close]

    def _do_race(self) -> None:
        if len(self.selected) == 2 and all(l in self._rows for l in self.selected):
            self.on_race(self._rows[self.selected[0]], self._rows[self.selected[1]])

    def toggle_selected(self, label: str) -> None:
        if label in self.selected:
            self.selected.remove(label)
        else:
            self.selected = (self.selected + [label])[-2:]  # chọn thứ ba thì bỏ lựa chọn cũ nhất

    # ------------------------------------------------------------------ vào/ra
    def update(self, dt: float, mouse, running: bool, has_rows: bool) -> None:
        self.btn_rerun.enabled = not running
        self.btn_save.enabled = has_rows and not running
        self.btn_race.enabled = len(self.selected) == 2 and not running
        for b in self.buttons:
            b.update(dt, mouse)

    def handle(self, event, mouse, data: Dict) -> bool:
        for b in self.buttons:
            if b.handle(event, mouse):
                return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for label, rect in self.cb_rects.items():
                if rect.inflate(16, 16).collidepoint(mouse):
                    self.toggle_selected(label)
                    return True
            for label, rect in self.rows_rects.items():
                row = data["rows"].get(label)
                if rect.collidepoint(mouse) and row is not None and usable(row) and row.get("actions"):
                    self.on_replay(row)
                    return True
            if not PANEL.collidepoint(mouse):
                self.btn_close.on_click()
                return True
        return event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEWHEEL)

    # ------------------------------------------------------------------ vẽ
    def draw(self, surf, mouse, data: Dict) -> None:
        dim = pygame.Surface((theme.WIDTH, theme.HEIGHT), pygame.SRCALPHA)
        dim.fill((6, 8, 16, 220))
        surf.blit(dim, (0, 0))
        rrect(surf, PANEL, theme.PANEL, 28, theme.PANEL_EDGE, 2)

        draw_text(surf, "Compare algorithms", theme.font(46, True), theme.TEXT, (PANEL.x + 40, PANEL.y + 28))
        draw_text(surf, data["title"], theme.font(24), theme.ACCENT, (PANEL.right - 40, PANEL.y + 44), "topright")
        labels: List[str] = data["labels"]
        rows: Dict[str, Dict] = data["rows"]
        self._rows = rows
        self.selected = [l for l in self.selected if l in rows]
        running = data["running_label"]
        if running is not None:
            status = f"Running {running}  ({len(rows)} / {data['total']} done)"
        elif rows:
            status = "Click a row to replay its solution, or tick two algorithms and press Race selected."
        else:
            status = ""
        draw_text(surf, status, theme.font(20), theme.TEXT_DIM, (PANEL.x + 42, PANEL.y + 92))
        if data["skipped"]:
            draw_text(
                surf, "Skipped (not implemented yet): " + ", ".join(data["skipped"]),
                theme.font(17), theme.TEXT_FAINT, (PANEL.x + 42, PANEL.y + 122),
            )

        # tiêu đề cột
        hy = PANEL.y + 168
        draw_text(surf, "ALGORITHM", theme.font(14, True), theme.TEXT_FAINT, (PANEL.x + 60, hy))
        draw_text(surf, "MOVES", theme.font(14, True), theme.TEXT_FAINT, (PANEL.x + 440, hy), "topright")
        draw_text(surf, "COST", theme.font(14, True), theme.TEXT_FAINT, (PANEL.x + 540, hy), "topright")
        for _, title, x, _w in BAR_COLS:
            draw_text(surf, title.upper(), theme.font(14, True), theme.TEXT_FAINT, (PANEL.x + x, hy))

        done_rows = [rows[l] for l in labels if l in rows]
        final = running is None  # chỉ tô "tốt nhất" / "optimal" khi đã có đủ kết quả để so sánh
        marks = best_marks(done_rows) if final else {i: set() for i in range(len(done_rows))}
        mark_of = {id(r): marks[i] for i, r in enumerate(done_rows)}
        ranges = {}
        for key, *_ in BAR_COLS:
            vals = [r[key] for r in done_rows if usable(r) and r.get(key) not in (None, "")]
            ranges[key] = (min(vals), max(vals)) if vals else (0, 0)
        min_cost = min((r["cost"] for r in done_rows if usable(r)), default=None) if final else None

        self.rows_rects = {}
        self.cb_rects = {}
        for i, label in enumerate(labels):
            rect = pygame.Rect(PANEL.x + 24, FIRST_ROW_Y + i * (ROW_H + ROW_GAP), PANEL.w - 48, ROW_H)
            row = rows.get(label)
            self._draw_row(surf, rect, label, row, running == label, mark_of.get(id(row), set()), ranges, min_cost, mouse)
            self.rows_rects[label] = rect

        if done_rows and final:
            for j, line in enumerate(wrap_text(summary_line(done_rows), theme.font(19), 640)[:3]):
                draw_text(surf, line, theme.font(19), theme.TEXT, (PANEL.x + 720, PANEL.bottom - 88 + j * 24))
        for b in self.buttons:
            b.draw(surf)

    def _draw_row(self, surf, rect, label, row, is_running, marks, ranges, min_cost, mouse) -> None:
        playable = row is not None and usable(row) and bool(row.get("actions"))
        hot = playable and rect.collidepoint(mouse)
        edge = theme.ACCENT if hot else theme.PANEL_EDGE
        rrect(surf, rect, theme.CARD_HI if hot else theme.CARD, 16, edge, 2)
        cy = rect.centery
        if playable:  # ô tích chọn để đua
            cb = pygame.Rect(rect.x + 18, cy - 13, 26, 26)
            self.cb_rects[label] = cb
            on = label in self.selected
            rrect(surf, cb, theme.ACCENT if on else (36, 43, 64), 7, theme.ACCENT if on else theme.PANEL_EDGE, 2)
            if on:
                pygame.draw.lines(surf, (28, 22, 8), False, [(cb.x + 6, cb.centery), (cb.x + 11, cb.bottom - 8), (cb.right - 6, cb.y + 7)], 3)
        else:
            pygame.draw.circle(surf, theme.ACCENT if is_running else theme.TEXT_FAINT, (rect.x + 31, cy), 8)
        draw_text(surf, label, theme.font(27, True), theme.TEXT, (rect.x + 62, cy), "midleft")

        if row is None:
            if is_running:
                ang = pygame.time.get_ticks() / 140
                for k in range(8):
                    a = ang + k * math.tau / 8
                    pygame.draw.circle(
                        surf, theme.mix(theme.CARD, theme.ACCENT, (k + 1) / 8),
                        (int(rect.x + 560 + 14 * math.cos(a)), int(cy + 14 * math.sin(a))), 3,
                    )
                draw_text(surf, "searching...", theme.font(22), theme.TEXT, (rect.x + 590, cy), "midleft")
            else:
                draw_text(surf, "waiting", theme.font(20), theme.TEXT_FAINT, (rect.x + 560, cy), "midleft")
            return

        status = row.get("status", "")
        if status != "ok" or row.get("valid") is not True:
            if status == "no_solution":
                msg = "No solution found"
            elif status == "timeout":
                msg = "Timed out"
            elif status == "ok":
                msg = "Returned an invalid solution"
            else:
                msg = status.replace("error: ", "Error: ")
            draw_text(surf, msg[:80], theme.font(22, True), theme.BAD, (rect.x + 560, cy), "midleft")
            return

        good = lambda key: key in marks  # noqa: E731
        draw_text(
            surf, str(row["moves"]), theme.mono(26, True),
            theme.GOOD if good("moves") else theme.TEXT, (rect.x + 416, cy), "midright",
        )
        optimal = row["cost"] == min_cost
        draw_text(
            surf, str(row["cost"]), theme.mono(26, True),
            theme.GOOD if good("cost") else theme.TEXT, (rect.x + 516, cy - (10 if optimal else 0)), "midright",
        )
        if optimal:
            draw_text(surf, "optimal", theme.font(14, True), theme.GOOD, (rect.x + 516, cy + 16), "midright")
        for key, _title, x, width in BAR_COLS:
            lo, hi = ranges[key]
            v = row.get(key)
            best = good(key)
            draw_text(
                surf, fmt_value(key, v), theme.mono(22, True),
                theme.GOOD if best else theme.TEXT, (rect.x + x - 24, rect.y + 16),
            )
            track = pygame.Rect(rect.x + x - 24, rect.y + 52, width, 10)
            rrect(surf, track, (44, 52, 76), 5)
            frac = bar_fraction(float(v), float(lo), float(hi)) if v not in (None, "") else 0
            fill = pygame.Rect(track.x, track.y, max(8, int(track.w * frac)), track.h)
            rrect(surf, fill, theme.GOOD if best else theme.INFO, 5)
