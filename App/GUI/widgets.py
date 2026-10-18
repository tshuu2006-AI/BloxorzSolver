"""Widget nhỏ: nút, thanh trượt, nhãn, vẽ bo góc."""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence

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
    ):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.sublabel = sublabel
        self.on_click = on_click
        self.style = style
        self.enabled = enabled
        self.tooltip = tooltip
        self.accent = accent
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
            draw_text(surf, self.label, theme.font(26, True), text, (r.centerx, r.centery - 9), "center")
            draw_text(
                surf, self.sublabel, theme.font(15),
                theme.TEXT_DIM if self.enabled else theme.TEXT_FAINT,
                (r.centerx, r.centery + 17), "center",
            )
        else:
            draw_text(surf, self.label, theme.font(24, True), text, r.center, "center")


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
