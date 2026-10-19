"""Phần thuần của các hiệu ứng: tổng hợp âm thanh, đường cong ép dẹt, công tắc vừa kích hoạt, cài đặt âm thanh."""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

from App.Components.level_loader import load_level
from App.Game import synth
from App.Game.session import GameSession, Outcome, fired_switches
from App.Game.settings import Settings
from App.Solvers.UCS_solver import UCSSolver

LEVELS = Path(__file__).resolve().parent.parent / "levels"


class Synth(unittest.TestCase):
    def test_every_sound_renders_within_range(self):
        for name in synth.SOUNDS:
            samples = synth.render(name)
            self.assertGreater(len(samples), 500, name)
            self.assertLessEqual(max(abs(v) for v in samples), 32767, name)
            self.assertGreater(max(abs(v) for v in samples), 10000, name)  # đã chuẩn hoá, không im lặng

    def test_render_is_deterministic(self):
        self.assertEqual(synth.render("roll"), synth.render("roll"))

    def test_rate_scales_length(self):
        self.assertAlmostEqual(len(synth.render("fall", 44100)) / len(synth.render("fall", 22050)), 2.0, places=1)


class Squash(unittest.TestCase):
    def test_curve_starts_flat_then_bounces_back_to_rest(self):
        from App.GUI.render import LAND_DUR, squash_curve

        self.assertGreater(squash_curve(0.0), 0.1)  # chạm sàn: dẹt nhất
        self.assertLess(min(squash_curve(u / 100) for u in range(100)), 0.0)  # nảy lại giãn nhẹ
        self.assertEqual(squash_curve(1.0), 0.0)
        self.assertEqual(squash_curve(-0.1), 0.0)
        self.assertLess(max(abs(squash_curve(u / 100)) for u in range(100)), 0.2)  # không biến dạng quá tay
        self.assertGreater(LAND_DUR, 0.1)


class FragileFall(unittest.TestCase):
    def test_fragile_tile_can_fall_whole_and_reset(self):
        import pygame
        from App.Components.features import TileType
        from App.GUI.render import BoardRenderer

        level = load_level(LEVELS / "06_thin_ice.json")
        cell = next(cell for cell, tile in level.problem.grid.items() if tile == TileType.FRAGILE)
        renderer = BoardRenderer(level)
        renderer.start_fragile_fall(cell)
        surf = pygame.Surface((1920, 1080), pygame.SRCALPHA)
        renderer.draw_board(surf)
        renderer.draw_falling_fragile_tile(surf, cell, 0.65)
        self.assertIn(cell, renderer.falling_fragile_cells)
        renderer.clear_fragile_falls()
        self.assertNotIn(cell, renderer.falling_fragile_cells)


class FiredSwitches(unittest.TestCase):
    def test_soft_switch_reported_only_on_the_move_that_lands_on_it(self):
        level = load_level(LEVELS / "09_soft_touch.json")
        session = GameSession(level)
        fired_at = []
        for step, action in enumerate(UCSSolver().solve(level.problem)):
            ev = session.apply(action)
            if fired_switches(level.problem, ev):
                fired_at.append(step)
            if ev.outcome == Outcome.WON:
                break
        self.assertEqual(len(fired_at), 1)

    def test_nothing_fires_on_a_plain_move(self):
        level = load_level(LEVELS / "01_first_roll.json")
        session = GameSession(level)
        ev = session.apply(UCSSolver().solve(level.problem)[0])
        self.assertEqual(fired_switches(level.problem, ev), [])

    def test_falls_and_swaps_fire_nothing(self):
        level = load_level(LEVELS / "01_first_roll.json")
        session = GameSession(level)
        ev = session.apply("SWITCH")
        self.assertEqual(fired_switches(level.problem, ev), [])


class SoundSettings(unittest.TestCase):
    def test_defaults_and_clamping(self):
        with tempfile.TemporaryDirectory() as d:
            s = Settings(Path(d) / "s.json")
            self.assertTrue(s.sound_on)
            self.assertAlmostEqual(s.volume, 0.6)
            s.set("volume", 3.0)
            self.assertEqual(s.volume, 1.0)
            s.set("sound_on", False)
            self.assertFalse(Settings(Path(d) / "s.json").sound_on)


class AudioWrapper(unittest.TestCase):
    def test_play_never_raises_even_without_a_device(self):
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        import pygame

        pygame.mixer.pre_init(22050, -16, 1, 512)
        from App.GUI.audio import Audio

        audio = Audio(True, 0.5)
        for name in synth.SOUNDS:
            audio.play(name)
        audio.set_enabled(False)
        audio.play("roll")
        audio.set_volume(2.0)
        self.assertEqual(audio.volume, 1.0)


if __name__ == "__main__":
    unittest.main()
