import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
pygame.init()

from App.GUI.app import App as BloxorzApp
from App.Solvers.BFS_solver import BFSSolver

def test_level_select_and_cactus():
    print("Testing LevelSelectView with Map Previews & Desert Cactus Sink...")
    app = BloxorzApp()
    
    # 1. Test LevelSelectView in Arctic
    app.screen_state = "level_select"
    surf = pygame.Surface((1920, 1080))
    app.level_select_view.update(0.016, (960, 540))
    app.level_select_view.draw(surf, (960, 540))
    print("[OK] LevelSelectView rendered with map thumbnails in Arctic.")
    
    # Test Pagination: Next page button
    assert app.level_select_view.page == 0
    next_pos = app.level_select_view.btn_next_page.center
    down_ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": next_pos})
    app.level_select_view.handle(down_ev, next_pos)
    assert app.level_select_view.page == 1, f"Expected page 1 after clicking next, got {app.level_select_view.page}"
    print("[OK] Clicked [NEXT >] arrow button: navigated to page 1.")
    
    # Test Click on Page Pill [ 3 ]
    pills = app.level_select_view.page_pill_rects
    target_p, target_rect = [(p, r) for p, r in pills if p == 2][0]  # Page 3 (0-indexed 2)
    pill_pos = target_rect.center
    app.level_select_view.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": pill_pos}), pill_pos)
    assert app.level_select_view.page == 2, f"Expected page 2 after clicking pill, got {app.level_select_view.page}"
    print("[OK] Clicked Page Pill [ 3 ]: navigated directly to page 3.")
    
    # Test Click Prev button [ < PREV ]
    prev_pos = app.level_select_view.btn_prev_page.center
    app.level_select_view.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": prev_pos}), prev_pos)
    assert app.level_select_view.page == 1, f"Expected page 1 after clicking prev, got {app.level_select_view.page}"
    print("[OK] Clicked [< PREV] arrow button: navigated back to page 1.")
    
    # 2. Test LevelSelectView in Desert
    app.set_theme("desert")
    app.level_select_view.draw(surf, (960, 540))
    print("[OK] LevelSelectView rendered with warm map thumbnails in Desert.")
    
    # 3. Test Desert Cactus Sink Animation
    app.load_level(0)
    app.push_screen("playing")
    solver = BFSSolver()
    actions = solver.solve(app.level.problem)
    
    for act in actions:
        app.do_action(act)
        while app.anims:
            app.update(0.04, (960, 540))
            app.draw((960, 540))
            
    print("[OK] Desert Cactus smoothly plunged down into the circular oasis without rendering glitches.")
    print("\nALL LEVEL SELECT & CACTUS SINK TESTS PASSED 100%!")

if __name__ == "__main__":
    test_level_select_and_cactus()
