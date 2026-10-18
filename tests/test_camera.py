"""Camera: phép chiếu, tia nhìn và thứ tự vẽ đúng ở mọi góc xoay."""

import math
import os
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from App.GUI.render import ELEV_MAX, ELEV_MIN, ZOOM_MAX, ZOOM_MIN, Camera, Iso

AREA = pygame.Rect(0, 140, 1360, 730)


class CameraMath(unittest.TestCase):
    def test_default_view_has_columns_running_west_east_with_15_degree_tilt(self):
        iso = Iso(6, 10, AREA, Camera())
        x0, y0 = iso.p(0, 0)
        x1, y1 = iso.p(0, 1)
        angle = math.degrees(math.atan2(-(y1 - y0), x1 - x0))  # + = ngược chiều kim đồng hồ
        self.assertAlmostEqual(angle, 15.0, places=3)

    def test_view_ray_projects_to_a_single_point(self):
        for alpha in (-2.5, -1.0, -0.49, 0.0, 0.7, 1.9, 3.0):
            for elev in (ELEV_MIN, 0.5, ELEV_MAX):
                cam = Camera()
                cam.alpha, cam.elev = alpha, elev
                iso = Iso(7, 9, AREA, cam)
                base = iso.p(2.0, 3.0, 0.4)
                moved = iso.p(2.0 + 5 * iso.view[0], 3.0 + 5 * iso.view[1], 0.4 + 5 * iso.view[2])
                self.assertAlmostEqual(base[0], moved[0], places=6)
                self.assertAlmostEqual(base[1], moved[1], places=6)

    def test_nearer_cells_draw_later_and_appear_lower_on_screen(self):
        cam = Camera()
        iso = Iso(6, 6, AREA, cam)
        # dọc theo hướng camera nhìn, ô càng gần có order lớn hơn và nằm thấp hơn trên màn hình
        near = (3.0 + iso.ca, 3.0 + iso.sa)
        self.assertGreater(iso.order(*near), iso.order(3.0, 3.0))
        self.assertGreater(iso.p(*near)[1], iso.p(3.0, 3.0)[1])

    def test_board_center_stays_put_when_rotating_and_zooming(self):
        cam = Camera()
        centers = []
        for alpha, zoom in ((0.2, 1.0), (1.4, 1.7), (-2.0, 0.6)):
            cam.alpha, cam.zoom = alpha, zoom
            iso = Iso(6, 10, AREA, cam)
            x, y = iso.p(3, 5, 0)
            centers.append((round(x, 3), round(y - (2 - iso.depth) * iso.U / 2, 3)))
        self.assertEqual(len(set(centers)), 1)

    def test_zoom_and_pitch_are_clamped(self):
        cam = Camera()
        for _ in range(60):
            cam.zoom_by(1.3)
        self.assertEqual(cam.target_zoom, ZOOM_MAX)
        for _ in range(120):
            cam.zoom_by(0.7)
        self.assertEqual(cam.target_zoom, ZOOM_MIN)
        cam.rotate(0.1, 10.0)
        self.assertEqual(cam.elev, ELEV_MAX)
        cam.rotate(0.1, -10.0)
        self.assertEqual(cam.elev, ELEV_MIN)

    def test_reset_restores_default(self):
        cam = Camera()
        cam.rotate(1.0, 0.3)
        cam.zoom_by(2)
        cam.pan[0] = 50
        cam.reset()
        fresh = Camera()
        self.assertEqual((cam.alpha, cam.elev, cam.target_zoom, cam.pan), (fresh.alpha, fresh.elev, 1.0, [0.0, 0.0]))


if __name__ == "__main__":
    unittest.main()
