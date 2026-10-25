"""Màu sắc, kích thước và font dùng chung cho GUI (canvas logic 1920x1080)."""

from __future__ import annotations

from functools import lru_cache

import pygame

WIDTH, HEIGHT = 1920, 1080

# Trục cột của bàn chạy Tây -> Đông, nghiêng bấy nhiêu độ ngược chiều kim đồng hồ.
AXIS_TILT_DEG = 15.0
PANEL_W = 500
PANEL_MARGIN = 28
BOARD_AREA = pygame.Rect(0, 0, WIDTH, HEIGHT)
BOARD_VIEW = pygame.Rect(80, 100, WIDTH - 160, 840)
PANEL_RECT = pygame.Rect(WIDTH - PANEL_W - PANEL_MARGIN, 28, PANEL_W, HEIGHT - 56)

# Nền
BG_TOP = (18, 28, 48)
BG_BOTTOM = (44, 68, 108)

# Giao diện
PANEL = (24, 36, 58)
PANEL_EDGE = (64, 94, 138)
CARD = (34, 50, 78)
CARD_HI = (48, 72, 110)
TEXT = (245, 248, 255)
TEXT_DIM = (168, 192, 224)
TEXT_FAINT = (112, 134, 164)
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
# Hai khối đơn phải phân biệt được ngay: khối đang điều khiển sáng + viền trắng + mũi tên,
# khối còn lại xám xanh tối và hơi trong.
CUBE_ACTIVE = (70, 236, 250)
CUBE_INACTIVE = (66, 78, 104)

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

# --- Theme Bắc Cực (Arctic / Penguin Theme) ---
ARCTIC_BG_TOP = (18, 28, 48)
ARCTIC_BG_BOTTOM = (44, 68, 108)
ARCTIC_PANEL = (24, 36, 58)
ARCTIC_PANEL_EDGE = (64, 94, 138)
ARCTIC_CARD = (34, 50, 78)
ARCTIC_CARD_HI = (48, 72, 110)
ARCTIC_ACCENT = (255, 196, 64)
ARCTIC_ACCENT_DARK = (214, 150, 28)

ARCTIC_FLOOR_TOP = (236, 246, 255)
ARCTIC_FLOOR_TOP_ALT = (224, 238, 252)
ARCTIC_START_TOP = (185, 228, 255)
ARCTIC_FLOOR_SIDE_R = (92, 134, 178)
ARCTIC_FLOOR_SIDE_C = (72, 110, 150)

ARCTIC_FRAGILE_TOP = (165, 226, 242)
ARCTIC_FRAGILE_TOP_ALT = (150, 215, 235)
ARCTIC_FRAGILE_SIDE_R = (72, 140, 172)
ARCTIC_FRAGILE_SIDE_C = (54, 110, 138)

ARCTIC_WOOD_TOP = (144, 94, 56)
ARCTIC_WOOD_TOP_ALT = (130, 82, 46)
ARCTIC_WOOD_SIDE_R = (92, 58, 34)
ARCTIC_WOOD_SIDE_C = (72, 44, 24)

ARCTIC_BRIDGE_COLORS = [
    (156, 102, 60),   # Gỗ sồi
    (180, 120, 75),   # Gỗ thông
    (130, 80, 45),    # Gỗ óc chó
    (195, 135, 85),   # Gỗ phong
    (140, 75, 40),    # Gỗ tuyết tùng
    (165, 110, 65),   # Gỗ tếch
    (120, 70, 38),    # Gỗ gụ
    (175, 125, 78),   # Gỗ bạch đàn
]

ARCTIC_ICE_BLOCK = (185, 235, 255)
ARCTIC_GOAL_RING = (90, 248, 220)

# --- Theme Sa Mạc (Desert / Cactus Theme) ---
DESERT_BG_TOP = (46, 22, 34)
DESERT_BG_BOTTOM = (108, 48, 52)
DESERT_PANEL = (52, 28, 38)
DESERT_PANEL_EDGE = (165, 88, 62)
DESERT_CARD = (68, 36, 46)
DESERT_CARD_HI = (88, 48, 60)
DESERT_ACCENT = (255, 185, 65)
DESERT_ACCENT_DARK = (215, 125, 35)

DESERT_FLOOR_TOP = (238, 196, 132)
DESERT_FLOOR_TOP_ALT = (226, 184, 120)
DESERT_START_TOP = (248, 218, 155)
DESERT_FLOOR_SIDE_R = (168, 102, 58)
DESERT_FLOOR_SIDE_C = (136, 78, 42)

DESERT_FRAGILE_TOP = (215, 110, 75)
DESERT_FRAGILE_TOP_ALT = (198, 96, 64)
DESERT_FRAGILE_SIDE_R = (145, 65, 40)
DESERT_FRAGILE_SIDE_C = (115, 50, 30)

DESERT_WOOD_TOP = (168, 124, 82)
DESERT_WOOD_TOP_ALT = (152, 110, 70)
DESERT_WOOD_SIDE_R = (118, 78, 46)
DESERT_WOOD_SIDE_C = (92, 58, 32)

DESERT_BRIDGE_COLORS = [
    (210, 105, 55),
    (235, 150, 70),
    (185, 85, 45),
    (240, 180, 85),
    (195, 115, 60),
    (220, 130, 65),
    (170, 75, 40),
    (225, 160, 75),
]

DESERT_CACTUS_BLOCK = (76, 175, 70)
DESERT_GOAL_RING = (255, 205, 80)


GROUP_COLORS = {
    "simple": (96, 214, 140),
    "fragile": (255, 160, 80),
    "switch": (92, 190, 236),
    "split": (120, 236, 232),
    "combined": (236, 120, 210),
    "classic": (255, 196, 64),
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
