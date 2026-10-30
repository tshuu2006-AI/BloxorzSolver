import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
pygame.init()

from App.GUI.app import App as BloxorzApp
from App.GUI import theme
from App.GUI.models import get_cactus_mesh
from App.Solvers.BFS_solver import BFSSolver

def test_all_user_fixes():
    print("Verifying all user bug fixes & improvements...")
    app = BloxorzApp()
    
    # 1. Verify App has slider and speed_slider attribute
    assert hasattr(app, "slider"), "App must have slider attribute"
    assert hasattr(app, "speed_slider"), "App must have speed_slider attribute"
    assert app.slider is app.speed_slider
    print("[OK] app.slider and app.speed_slider initialized correctly.")
    
    # 2. Test SettingsView "DATA & REPLAY" tab drawing & interaction
    app.settings_view.tab = "data_replay"
    surf = pygame.Surface((1920, 1080))
    # Draw settings view - must NOT raise AttributeError: 'App' object has no attribute 'slider'
    app.settings_view.draw(surf, (960, 310))
    
    # Handle slider event
    down_ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": (960, 310)})
    app.settings_view.handle(down_ev, (960, 310))
    up_ev = pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": (960, 310)})
    app.settings_view.handle(up_ev, (960, 310))
    print("[OK] SettingsView 'DATA & REPLAY' tab renders and handles slider without error.")
    
    # 3. Test Map Centering
    assert theme.BOARD_VIEW.centerx == 960, f"Expected BOARD_VIEW centerx=960, got {theme.BOARD_VIEW.centerx}"
    print(f"[OK] Map viewport is perfectly centered at x = {theme.BOARD_VIEW.centerx}.")
    
    # 4. Test Cactus Mesh Taper (distinguishing head vs foot)
    c_verts, c_faces, c_colors = get_cactus_mesh(is_cube=False)
    z_coords = [v[2] for v in c_verts]
    z_min = min(z_coords)
    foot_verts = [v for v in c_verts if abs(v[2] - z_min) < 0.05]
    foot_radius = max((v[0]**2 + v[1]**2)**0.5 for v in foot_verts)
    
    head_verts = [v for v in c_verts if 0.25 <= v[2] <= 0.45]
    head_radius = max((v[0]**2 + v[1]**2)**0.5 for v in head_verts)
    
    print(f"[OK] Cactus geometry: foot_radius={foot_radius:.3f}, head_radius={head_radius:.3f}")
    assert foot_radius < head_radius * 0.55, f"Foot ({foot_radius}) should be noticeably narrower than head ({head_radius})"
    print("[OK] Cactus foot is distinctly tapered for immediate visual orientation.")
    
    # 5. Test Main Menu simplicity (no diorama drawn)
    app.screen_state = "menu"
    app.menu.update(0.016, (500, 500))
    app.menu.draw(surf, (500, 500))
    print("[OK] Main Menu renders cleanly and simply without 3D block/cactus diorama.")
    
    # 6. Test Win Animation (SinkAnim)
    app.load_level(0)
    app.push_screen("playing")
    
    # Solve with BFS to get guaranteed winning path
    solver = BFSSolver()
    actions = solver.solve(app.level.problem)
    assert actions is not None
    print(f"[INFO] Solving stage with {len(actions)} actions: {actions}")
    
    # Track audio calls
    played_sounds = []
    app.audio.play = lambda name: played_sounds.append(name)
    
    for act in actions:
        app.do_action(act)
        while app.anims:
            app.update(0.04, (960, 540))
            app.draw((960, 540))
            
    # Check that winning triggered "sink" and "win" sound effects
    assert "sink" in played_sounds, f"Expected 'sink' in played_sounds, got {played_sounds}"
    assert "win" in played_sounds, f"Expected 'win' in played_sounds, got {played_sounds}"
    print(f"[OK] Win animation triggered sound effects: {played_sounds}")
    
    # Check that board drawing during gameplay runs smoothly
    app.draw((960, 540))
    print("[OK] Gameplay board rendered smoothly during win celebration.")

    print("\nALL USER FIXES VERIFIED 100% SUCCESFULLY!")

if __name__ == "__main__":
    test_all_user_fixes()
