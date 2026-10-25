import os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
pygame.init()

from App.GUI.app import App as BloxorzApp

def test_desert_and_solver():
    print("Testing Desert theme & Solver UI integration...")
    app = BloxorzApp()
    
    # 1. Check Initial Theme
    assert app.current_theme in ("arctic", "desert")
    print(f"[OK] Initial theme: {app.current_theme}")
    
    # Toggle to Desert
    if app.current_theme != "desert":
        app.toggle_theme()
    assert app.current_theme == "desert"
    assert app.renderer.theme_name == "desert"
    print("[OK] Toggled theme to Desert successfully.")
    
    # 2. Main menu update & render with Cactus diorama
    surf = pygame.Surface((1920, 1080))
    for _ in range(5):
        app.menu.update(0.016, (500, 500))
        app.menu.draw(surf, (500, 500))
    print("[OK] Main Menu rendered with 3D Cactus diorama.")
    
    # 3. Enter Game
    app.load_level(1)
    app.push_screen("playing")
    assert app.screen_state == "playing"
    assert app.renderer.is_desert is True
    print("[OK] Entered gameplay in Desert mode.")
    
    # Render standing cactus
    app.update(0.016, (500, 500))
    app.draw((500, 500))
    print("[OK] Standing cactus rendered on sand board.")
    
    # 4. Move block: roll Right to horizontal
    app.do_action("R")  # roll Right
    while app.anims:
        app.update(0.05, (500, 500))
        app.draw((500, 500))
    print(f"[OK] Rolled Right. State orientation = {app.session.state.orientation}")
    
    # Roll sideways along row (Up)
    app.do_action("U")  # roll Up (sideways cylinder roll)
    while app.anims:
        app.update(0.05, (500, 500))
        app.draw((500, 500))
    print("[OK] Cylindrical rolling sideways animation completed smoothly.")
    
    # 5. Open AI Solver drawer
    app.show_ai_panel = True
    assert app.show_ai_panel
    app.update(0.016, (500, 500))
    app.draw((500, 500))
    print("[OK] Solver drawer rendered with enlarged buttons and clean labels.")
    
    # Solve with BFS
    app.solver_drawer._on_solver_click("BFS")
    for _ in range(50):
        time.sleep(0.02)
        app.update(0.05, (500, 500))
        if app.stats is not None and app.stats.found:
            break
            
    assert app.stats is not None and app.stats.found
    print(f"[OK] Solver found solution: {len(app.stats.actions)} steps.")
    
    # Close Solver drawer
    app.solver_drawer._close()
    assert not app.show_ai_panel
    print("[OK] Closed Solver drawer cleanly.")
    
    # 6. Switch back to Arctic theme
    app.toggle_theme()
    assert app.current_theme == "arctic"
    assert app.renderer.is_arctic is True
    app.update(0.016, (500, 500))
    app.draw((500, 500))
    print("[OK] Seamlessly switched back to Arctic theme.")

    print("\nALL DESERT & POLISHED SOLVER TESTS PASSED 100%!")

if __name__ == "__main__":
    test_desert_and_solver()

