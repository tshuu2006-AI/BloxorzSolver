import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"

import pygame
pygame.init()

from App.GUI.app import App as BloxorzApp
from App.Components.state import Orientation

print("Starting complete UX integration verification...")
app = BloxorzApp()

# 1. Menu State
assert app.screen_state == "menu", f"Expected menu, got {app.screen_state}"
assert app.screen_stack == ["menu"], f"Expected ['menu'], got {app.screen_stack}"

# Draw menu frame
surf = pygame.Surface((1920, 1080))
app.menu.update(0.016, (500, 500))
app.menu.draw(surf, (500, 500))
print("[OK] Main menu updated and rendered with 3D baked penguin successfully.")

# 2. Start Game
play_idx = [i for i, (act, _) in enumerate(app.menu.items) if act == "play"][0]
play_rect = app.menu.item_rects[play_idx]
down_ev = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": play_rect.center})
app.handle(down_ev, play_rect.center)
assert app.screen_state == "playing", f"Expected playing, got {app.screen_state}"
assert app.screen_stack == ["menu", "playing"], f"Stack: {app.screen_stack}"
print("[OK] Entered gameplay screen.")

# 3. Gameplay & Undo with Reverse Animation
init_moves = app.session.moves
app.do_action("R")
assert app.session.moves == init_moves + 1, "Move did not register"
assert len(app.action_history) == 1, "Action history not recorded"

# Trigger undo
app.undo()
assert len(app.anims) > 0, "Expected reverse RollAnim in anims"
anim = app.anims[0]
assert anim.kind == "roll", f"Expected roll anim, got {anim.kind}"

# Update anim until finished
while app.anims:
    app.update(0.05, (0, 0))

assert app.session.moves == init_moves, f"Moves should be back to {init_moves}, got {app.session.moves}"
print("[OK] Undo with reverse roll animation verified successfully.")

# 4. AI Solver Panel Interactions
assert not app.show_ai_panel, "AI panel should initially be closed"

# TAB opens AI panel
tab_ev = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_TAB})
app.handle(tab_ev, (0, 0))
assert app.show_ai_panel, "AI panel should open on TAB"

# Click [X] to close
close_rect = app.solver_drawer.btn_close.rect
down_x = pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": close_rect.center})
app.handle(down_x, close_rect.center)
up_x = pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": close_rect.center})
app.handle(up_x, close_rect.center)
assert not app.show_ai_panel, "Clicking [X] should close AI panel!"
print("[OK] Clicking [X] successfully closed AI panel.")

# TAB opens AI panel again
app.handle(tab_ev, (0, 0))
assert app.show_ai_panel, "AI panel should open on TAB"

# ESC while AI panel open should close AI panel (not pause game!)
esc_ev = pygame.event.Event(pygame.KEYDOWN, {"key": pygame.K_ESCAPE})
app.handle(esc_ev, (0, 0))
assert not app.show_ai_panel, "ESC should close AI panel"
assert app.screen_state == "playing", f"ESC on AI panel should stay playing, got {app.screen_state}"
print("[OK] ESC closes AI panel without pausing or dropping to menu.")

# Re-open AI panel and test BFS solver
app.handle(tab_ev, (0, 0))
bfs_btn = app.solver_drawer.solver_buttons["BFS"]
app.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": bfs_btn.rect.center}), bfs_btn.rect.center)
app.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, {"button": 1, "pos": bfs_btn.rect.center}), bfs_btn.rect.center)

# Poll solver
import time
for _ in range(100):
    time.sleep(0.02)
    app.update(0.05, (0, 0))
    if app.stats is not None and app.stats.found:
        break

assert app.stats is not None and app.stats.found, "BFS did not find solution"
print(f"[OK] BFS solved stage: {len(app.stats.actions)} actions, metrics: {app.stats.metrics}")

# Draw AI panel while solved
app.draw(surf)
print("[OK] Rendered AI Solver Arena with solved telemetry successfully.")

# Close panel
app.handle(esc_ev, (0, 0))
assert not app.show_ai_panel

# 5. Pause -> Settings -> Return to Pause Flow
# ESC when panel is closed pauses game
app.handle(esc_ev, (0, 0))
assert app.screen_state == "paused", f"Expected paused, got {app.screen_state}"
assert app.screen_stack == ["menu", "playing", "paused"], f"Stack: {app.screen_stack}"

app.pause_menu.draw(surf, (0, 0))
# Click SETTINGS in PauseMenu
settings_idx = [i for i, (act, _) in enumerate(app.pause_menu.items) if act == "settings"][0]
settings_rect = app.pause_menu.item_rects[settings_idx]
app.pause_menu.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": settings_rect.center}), settings_rect.center)
assert app.screen_state == "settings", f"Expected settings, got {app.screen_state}"
assert app.screen_stack == ["menu", "playing", "paused", "settings"], f"Stack: {app.screen_stack}"

# Press ESC in settings: MUST return to "paused"
app.settings_view.handle(esc_ev, (0, 0))
assert app.screen_state == "paused", f"Expected return to paused, got {app.screen_state}"
assert app.screen_stack == ["menu", "playing", "paused"], f"Stack: {app.screen_stack}"
print("[OK] Settings Back/ESC returned to Pause Menu (game session preserved).")

app.pause_menu.draw(surf, (0, 0))
# Click LEVEL SELECT in PauseMenu
lvl_idx = [i for i, (act, _) in enumerate(app.pause_menu.items) if act == "level_select"][0]
lvl_rect = app.pause_menu.item_rects[lvl_idx]
app.pause_menu.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": lvl_rect.center}), lvl_rect.center)
assert app.screen_state == "level_select", f"Expected level_select, got {app.screen_state}"
assert app.screen_stack == ["menu", "playing", "paused", "level_select"], f"Stack: {app.screen_stack}"

# Press ESC in LevelSelect: MUST return to "paused"
app.level_select_view.handle(esc_ev, (0, 0))
assert app.screen_state == "paused", f"Expected return to paused, got {app.screen_state}"
assert app.screen_stack == ["menu", "playing", "paused"], f"Stack: {app.screen_stack}"
print("[OK] Level Select Back/ESC returned to Pause Menu.")

app.pause_menu.draw(surf, (0, 0))
# Click RESUME in PauseMenu
resume_idx = [i for i, (act, _) in enumerate(app.pause_menu.items) if act == "resume"][0]
resume_rect = app.pause_menu.item_rects[resume_idx]
app.pause_menu.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, {"button": 1, "pos": resume_rect.center}), resume_rect.center)
assert app.screen_state == "playing", f"Expected playing, got {app.screen_state}"
assert app.screen_stack == ["menu", "playing"], f"Stack: {app.screen_stack}"
print("[OK] Pause Menu resumed to gameplay seamlessly.")

# 6. From Menu -> Settings -> Return to Menu
app.screen_stack = ["menu"]
app.screen_state = "menu"
app.push_screen("settings")
assert app.screen_state == "settings"
app.settings_view.handle(esc_ev, (0, 0))
assert app.screen_state == "menu"
assert app.screen_stack == ["menu"]
print("[OK] Menu -> Settings -> Back returns to Menu.")

print("\nALL UX INTEGRATION TESTS PASSED 100% PERFECTLY!")
