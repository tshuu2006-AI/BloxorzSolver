"""Kiểm tra mô hình 3D Chim Cánh Cụt (Penguin) và render Bắc Cực."""

import math
import os
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from App.Components.level_loader import load_level
from App.GUI.models import INITIAL_FRAME, get_penguin_mesh, roll_frame
from App.GUI.render import BoardRenderer, Camera, Iso, _cross, _dot, _norm, _sub

LEVELS_DIR = Path(__file__).resolve().parent.parent / "levels"


class PenguinModelTest(unittest.TestCase):
    def test_mesh_generation_standing_and_cube(self):
        v_block, f_block, c_block = get_penguin_mesh(is_cube=False)
        self.assertGreater(len(v_block), 100)
        self.assertGreater(len(f_block), 80)
        self.assertEqual(len(f_block), len(c_block))

        # Kích thước khối 2x1x1 (cao ~1.76 đơn vị, vừa vặn trong khối cao 2.0)
        zs = [p[2] for p in v_block]
        rs = [p[0] for p in v_block]
        cs = [p[1] for p in v_block]
        self.assertLess(max(zs), 1.0)
        self.assertGreater(min(zs), -1.0)
        self.assertLess(max(rs), 0.5)
        self.assertGreater(min(rs), -0.5)
        self.assertLess(max(cs), 0.5)
        self.assertGreater(min(cs), -0.5)

        # Kích thước khối 1x1x1 khi bị tách
        v_cube, f_cube, c_cube = get_penguin_mesh(is_cube=True)
        self.assertGreater(len(v_cube), 100)
        self.assertEqual(len(f_cube), len(c_cube))
        self.assertLess(max(p[2] for p in v_cube), 0.5)
        self.assertGreater(min(p[2] for p in v_cube), -0.5)

    def test_head_and_facial_features_present(self):
        v, f, colors = get_penguin_mesh(is_cube=False)

        # Kiểm tra sự hiện diện của đỉnh đầu (apex z ~ 0.90)
        has_head_top = any(p[2] >= 0.88 for p in v)
        self.assertTrue(has_head_top, "Đỉnh đầu phải đạt z >= 0.88 để đầu tròn không bị cụt")

        # Kiểm tra màu mỏ cam
        has_orange_beak = any(col in ((255, 140, 0), (235, 110, 0), (255, 145, 15)) for col in colors)
        self.assertTrue(has_orange_beak, "Mỏ chim cam 3D phải hiện diện")

        # Kiểm tra mắt trắng & má hồng
        has_white_eye = any(col == (255, 255, 255) for col in colors)
        self.assertTrue(has_white_eye, "Đôi mắt trắng phải hiện diện")

        has_blush = any(col == (255, 155, 170) for col in colors)
        self.assertTrue(has_blush, "Má hồng phải hiện diện")

        # Đảm bảo không còn mảng màu vàng trên đầu và thân
        self.assertNotIn((255, 192, 38), colors, "Các mảng màu vàng đã được xóa khỏi thân và đầu")

    def test_beak_normals_not_backface_culled_from_front(self):
        v, f, colors = get_penguin_mesh(is_cube=False)
        cam = Camera()
        area = pygame.Rect(0, 0, 800, 600)
        iso = Iso(6, 6, area, cam)

        # Ít nhất một mặt mỏ phải hướng về phía camera mặc định
        visible_beak_faces = 0
        for i, face in enumerate(f):
            if colors[i] in ((255, 140, 0), (235, 110, 0), (255, 145, 15)):
                q = [v[idx] for idx in face]
                n = _norm(_cross(_sub(q[1], q[0]), _sub(q[2], q[0])))
                if _dot(n, iso.view) > 1e-6:
                    visible_beak_faces += 1

        self.assertGreater(visible_beak_faces, 0, "Mỏ chim không được bị cull hoàn toàn khi nhìn từ góc camera chuẩn")

    def test_renderer_draws_penguin_in_arctic_theme(self):
        lvl = load_level(LEVELS_DIR / "classic" / "01.json")
        surf = pygame.Surface((800, 600))
        renderer = BoardRenderer(lvl, area=pygame.Rect(0, 0, 800, 600), arctic_theme=True)
        renderer.set_theme("arctic")
        self.assertTrue(renderer.arctic_theme)
        self.assertTrue(renderer.is_arctic)

        # Vẽ một khối không ném ngoại lệ
        cells = lvl.problem.initial_state.get_occupied_cells()
        renderer.draw_piece(surf, cells, "block", 2.0, active=True)


if __name__ == "__main__":
    unittest.main()
