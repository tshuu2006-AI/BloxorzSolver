"""Widget nhỏ: nút, thanh trượt, nhãn, vẽ bo góc."""

from __future__ import annotations

from typing import Callable, List, Sequence

import pygame

from App.GUI import theme


def draw_text(surf, text, font, color, pos, anchor="topleft", alpha=255):
    img = font.render(text, True, color)
    if alpha < 255:
        img.set_alpha(alpha)
    rect = img.get_rect(**{anchor: pos})
    surf.blit(img, rect)
    return rect


def wrap_text(text: str, font: pygame.font.Font, width: int) -> List[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if font.size(trial)[0] <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def rrect(surf, rect, color, radius=12, border=None, border_w=2):
    """Hình chữ nhật bo góc, hỗ trợ màu có alpha."""
    rect = pygame.Rect(rect)
    if color is None:
        if border:
            pygame.draw.rect(surf, border, rect, border_w, border_radius=radius)
        return
    if len(color) == 4 and color[3] < 255:
        tmp = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(tmp, color, tmp.get_rect(), border_radius=radius)
        if border:
            pygame.draw.rect(tmp, border, tmp.get_rect(), border_w, border_radius=radius)
        surf.blit(tmp, rect)
        return
    pygame.draw.rect(surf, color[:3], rect, border_radius=radius)
    if border:
        pygame.draw.rect(surf, border, rect, border_w, border_radius=radius)


def vgradient(size, top, bottom) -> pygame.Surface:
    w, h = size
    surf = pygame.Surface(size)
    for y in range(h):
        pygame.draw.line(surf, theme.mix(top, bottom, y / max(1, h - 1)), (0, y), (w, y))
    return surf


class Button:
    def __init__(
        self,
        rect,
        label: str,
        on_click: Callable[[], None],
        style: str = "secondary",
        enabled: bool = True,
        tooltip: str = "",
        accent=None,
        sublabel: str = "",
        icon: str = "",
        font_size: int = 24,
    ):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.sublabel = sublabel
        self.on_click = on_click
        self.style = style
        self.enabled = enabled
        self.tooltip = tooltip
        self.accent = accent
        self.icon = icon
        self.font_size = font_size
        self.hover = 0.0
        self.pressed = False

    def update(self, dt, mouse):
        target = 1.0 if (self.enabled and self.rect.collidepoint(mouse)) else 0.0
        self.hover += (target - self.hover) * min(1.0, dt * 14)

    def handle(self, event, mouse) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.enabled and self.rect.collidepoint(mouse):
                self.pressed = True
                return True
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was = self.pressed
            self.pressed = False
            if was and self.enabled and self.rect.collidepoint(mouse):
                self.on_click()
                return True
        return False

    def draw(self, surf):
        r = self.rect.copy()
        if self.pressed:
            r.y += 2
        h = self.hover
        if not self.enabled:
            fill, text, edge = (28, 33, 47), theme.TEXT_FAINT, (40, 47, 66)
        elif self.style == "primary":
            fill = theme.mix(theme.ACCENT_DARK, theme.ACCENT, 0.35 + 0.65 * h)
            text, edge = (28, 22, 8), theme.mix(theme.ACCENT_DARK, theme.ACCENT, h)
        else:
            fill = theme.mix(theme.CARD, theme.CARD_HI, h)
            text = theme.TEXT
            edge = theme.mix(theme.PANEL_EDGE, self.accent or theme.ACCENT, 0.35 + 0.65 * h)
        rrect(surf, r, fill, 12, edge, 2)
        if self.accent and self.enabled and self.style != "primary":
            pygame.draw.rect(
                surf, self.accent, (r.x + 10, r.bottom - 6, r.w - 20, 3), border_radius=2
            )
        if self.sublabel:
            main_sz = self.font_size if self.font_size != 24 else 21
            sub_sz = max(11, int(main_sz * 0.62))
            draw_text(surf, self.label, theme.font(main_sz, True), text, (r.centerx, r.centery - 10), "center")
            draw_text(
                surf, self.sublabel, theme.font(sub_sz),
                theme.TEXT_DIM if self.enabled else theme.TEXT_FAINT,
                (r.centerx, r.centery + 12), "center",
            )
        elif self.icon:
            cx, cy = r.center
            s = 11
            if self.icon == "back":
                pts = [(cx + s, cy - s), (cx + s, cy + s), (cx - s, cy)]
                bar = pygame.Rect(cx - s - 5, cy - s, 4, 2 * s)
            else:
                pts = [(cx - s, cy - s), (cx - s, cy + s), (cx + s, cy)]
                bar = pygame.Rect(cx + s + 1, cy - s, 4, 2 * s)
            pygame.draw.polygon(surf, text, pts)
            pygame.draw.rect(surf, text, bar, border_radius=1)
        else:
            draw_text(surf, self.label, theme.font(self.font_size, True), text, r.center, "center")


class Slider:
    def __init__(self, rect, lo, hi, value, label="", fmt="{:.1f}x"):
        self.rect = pygame.Rect(rect)
        self.lo, self.hi, self.value = lo, hi, value
        self.label, self.fmt = label, fmt
        self.drag = False

    def _set_from(self, x):
        t = (x - self.rect.x) / self.rect.w
        self.value = self.lo + max(0.0, min(1.0, t)) * (self.hi - self.lo)

    def handle(self, event, mouse) -> bool:
        grab = self.rect.inflate(0, 28)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and grab.collidepoint(mouse):
            self.drag = True
            self._set_from(mouse[0])
            return True
        if event.type == pygame.MOUSEMOTION and self.drag:
            self._set_from(mouse[0])
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.drag:
            self.drag = False
            return True
        return False

    def draw(self, surf):
        r = self.rect
        t = (self.value - self.lo) / (self.hi - self.lo)
        pygame.draw.rect(surf, (44, 52, 76), (r.x, r.centery - 4, r.w, 8), border_radius=4)
        pygame.draw.rect(surf, theme.ACCENT, (r.x, r.centery - 4, int(r.w * t), 8), border_radius=4)
        pygame.draw.circle(surf, theme.TEXT, (r.x + int(r.w * t), r.centery), 11)
        pygame.draw.circle(surf, theme.ACCENT, (r.x + int(r.w * t), r.centery), 7)
        if self.label:
            draw_text(surf, self.label, theme.font(18), theme.TEXT_DIM, (r.x, r.y - 30))
        draw_text(
            surf, self.fmt.format(self.value), theme.font(18, True), theme.TEXT,
            (r.right, r.y - 30), "topright",
        )


class Segmented:
    """Dải chọn một trong vài lựa chọn (dùng cho heuristic của A*)."""

    def __init__(self, rect, options: Sequence[str], selected: int, on_change):
        self.rect = pygame.Rect(rect)
        self.options = list(options)
        self.selected = selected
        self.on_change = on_change

    def _cell(self, i):
        w = self.rect.w / len(self.options)
        return pygame.Rect(self.rect.x + int(i * w), self.rect.y, int(w), self.rect.h)

    def handle(self, event, mouse) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i in range(len(self.options)):
                if self._cell(i).collidepoint(mouse):
                    self.selected = i
                    self.on_change(self.options[i])
                    return True
        return False

    def draw(self, surf):
        rrect(surf, self.rect, (26, 31, 46), 10, theme.PANEL_EDGE, 2)
        for i, opt in enumerate(self.options):
            cell = self._cell(i).inflate(-6, -6)
            if i == self.selected:
                rrect(surf, cell, theme.ACCENT_DARK, 8)
            draw_text(
                surf, opt, theme.font(17, True),
                (28, 22, 8) if i == self.selected else theme.TEXT_DIM, cell.center, "center",
            )


class Toggle:
    """Công tắc bật/tắt một dòng: nhãn bên trái, nút gạt dạng viên thuốc bên phải."""

    def __init__(self, rect, label: str, value: bool, on_change: Callable[[bool], None], hint: str = ""):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.hint = hint
        self.value = value
        self.on_change = on_change
        self._pos = 1.0 if value else 0.0  # vị trí núm gạt (0..1) để chạy hiệu ứng
        self.hover = 0.0
        self.pressed = False

    def update(self, dt, mouse):
        self._pos += ((1.0 if self.value else 0.0) - self._pos) * min(1.0, dt * 16)
        target = 1.0 if self.rect.collidepoint(mouse) else 0.0
        self.hover += (target - self.hover) * min(1.0, dt * 14)

    def handle(self, event, mouse) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.rect.collidepoint(mouse):
            self.pressed = True
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            was, self.pressed = self.pressed, False
            if was and self.rect.collidepoint(mouse):
                self.value = not self.value
                self.on_change(self.value)
                return True
        return False

    def draw(self, surf):
        r = self.rect
        if self.hover > 0.02:
            rrect(surf, r, (*theme.CARD_HI, int(120 * self.hover)), 12)
        draw_text(surf, self.label, theme.font(19, True), theme.TEXT, (r.x + 14, r.centery - (9 if self.hint else 0)), "midleft")
        if self.hint:
            draw_text(surf, self.hint, theme.font(14), theme.TEXT_FAINT, (r.x + 14, r.centery + 12), "midleft")
        track = pygame.Rect(0, 0, 54, 28)
        track.midright = (r.right - 14, r.centery)
        col = theme.mix((52, 60, 84), theme.ACCENT_DARK, self._pos)
        rrect(surf, track, col, 14, theme.mix(theme.PANEL_EDGE, theme.ACCENT, self._pos), 2)
        kx = track.x + 14 + int(self._pos * (track.w - 28))
        pygame.draw.circle(surf, theme.mix(theme.TEXT_DIM, (255, 255, 255), self._pos), (kx, track.centery), 10)
