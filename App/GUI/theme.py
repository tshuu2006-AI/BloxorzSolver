"""Màu sắc, kích thước và font dùng chung cho GUI (canvas logic 1920x1080)."""

from __future__ import annotations

from functools import lru_cache

import pygame

WIDTH, HEIGHT = 1920, 1080
PANEL_W = 500
PANEL_MARGIN = 28
BOARD_AREA = pygame.Rect(0, 0, WIDTH - PANEL_W - PANEL_MARGIN, HEIGHT)
BOARD_VIEW = pygame.Rect(0, 140, WIDTH - PANEL_W - PANEL_MARGIN, 730)
PANEL_RECT = pygame.Rect(WIDTH - PANEL_W - PANEL_MARGIN, 28, PANEL_W, HEIGHT - 56)

# Nền
BG_TOP = (12, 16, 28)
BG_BOTTOM = (34, 42, 70)

# Giao diện
PANEL = (22, 27, 40)
PANEL_EDGE = (52, 62, 90)
CARD = (31, 38, 56)
CARD_HI = (42, 51, 76)
TEXT = (232, 236, 246)
TEXT_DIM = (150, 160, 184)
TEXT_FAINT = (98, 108, 132)
ACCENT = (255, 196, 64)
ACCENT_DARK = (214, 150, 28)
GOOD = (96, 214, 140)
BAD = (255, 104, 104)
INFO = (92, 190, 236)

# Ô sàn
FLOOR_TOP = (108, 122, 156)
FLOOR_TOP_ALT = (100, 114, 148)
START_TOP = (118, 140, 188)
FLOOR_SIDE_R = (66, 76, 104)
FLOOR_SIDE_C = (50, 58, 82)
FRAGILE_TOP = (232, 142, 64)
FRAGILE_TOP_ALT = (218, 128, 52)
FRAGILE_SIDE_R = (160, 90, 38)
FRAGILE_SIDE_C = (124, 68, 28)
GOAL_RING = (255, 226, 130)

# Khối
BLOCK = (244, 192, 62)
CUBE = (78, 196, 206)
CUBE_DIM = (52, 128, 142)

# Mỗi nhóm cầu một màu để nhìn ra công tắc nào điều khiển cầu nào.
BRIDGE_COLORS = [
    (226, 92, 190),
    (80, 200, 236),
    (140, 218, 92),
    (172, 128, 244),
    (252, 124, 96),
    (246, 226, 92),
    (96, 232, 190),
    (236, 160, 220),
]
SPLIT_COLOR = (120, 236, 232)

GROUP_COLORS = {
    "simple": (96, 214, 140),
    "fragile": (255, 160, 80),
    "switch": (92, 190, 236),
    "split": (120, 236, 232),
    "combined": (236, 120, 210),
}


@lru_cache(maxsize=None)
def font(size: int, bold: bool = False) -> pygame.font.Font:
    return pygame.font.SysFont("segoeui,seguisb,calibri,arial", size, bold=bold)


@lru_cache(maxsize=None)
def mono(size: int, bold: bool = False) -> pygame.font.Font:
    return pygame.font.SysFont("consolas,couriernew,monospace", size, bold=bold)


def shade(color, factor: float):
    return tuple(max(0, min(255, int(ch * factor))) for ch in color[:3])


def mix(a, b, t: float):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def group_color(group: str):
    return GROUP_COLORS.get(group, TEXT_DIM)
