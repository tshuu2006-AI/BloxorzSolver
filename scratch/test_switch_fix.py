import os
os.environ['SDL_VIDEODRIVER'] = 'dummy'
os.environ['SDL_AUDIODRIVER'] = 'dummy'

import pygame
pygame.init()
from App.GUI.app import App
from App.Game.session import Status, Outcome

app = App()
app.screen_state = 'playing'
classic = [l for l in app.levels if '09' in l.name and l.section == 'classic'][0]
app.load_level(app.levels.index(classic))
app.solver_drawer._on_solver_click('BFS')
while app.job and not app.job.done:
    app._poll_solver()
app._poll_solver()
app.toggle_step_guide()

# Advance 17 steps:
for step in range(17):
    act = app.next_step_info['action']
    app.do_action(act, from_replay=False)
    while app.anims:
        app.update(0.05, (0, 0))

print('Step 17 reached!')
print('next_step_info before SPACE:', app.next_step_info['action'])

# Apply fix to do_action:
orig_do_action = app.do_action
def my_do_action(action, from_replay=False):
    ev = orig_do_action(action, from_replay=from_replay)
    if ev is not None and ev.outcome == Outcome.SWITCHED:
        app._on_player_moved()
    return ev
app.do_action = my_do_action

# Also apply fix to _on_player_moved:
def my_on_player_moved():
    if not app.selected_solver or app.session.status != Status.PLAYING:
        return
    from_replay = getattr(app, 'is_action_from_replay', False)
    st = app.session.state
    if app.guide_solution and app.guide_states:
        if len(app.guide_states) > 0 and st == app.guide_states[0]:
            app._update_step_guide()
            return
        if len(app.guide_states) > 1 and st == app.guide_states[1]:
            act_done = app.guide_solution[0] if app.guide_solution else None
            if not from_replay and app.replay:
                app.replay_done.append(app.replay.popleft())
            app.guide_solution = app.guide_solution[1:]
            app.guide_states = app.guide_states[1:]
            if app.path_steps and act_done != 'SWITCH':
                app.path_steps = app.path_steps[1:]
            app._update_step_guide()
            return
    if from_replay:
        return
    app._recalculate_guide_from_current()
app._on_player_moved = my_on_player_moved

def my_update_step_guide():
    if app.session.status != Status.PLAYING or not app.selected_solver:
        app.next_step_info = None
        return
    st = app.session.state
    if app.guide_solution and app.guide_states and len(app.guide_states) > 1 and app.guide_states[0] == st:
        app.next_step_info = {
            'action': app.guide_solution[0],
            'next_state': app.guide_states[1],
        }
        return
    from App.Game.path import compute_step_guide
    res = compute_step_guide(
        app.level.problem,
        st,
        app.guide_solution,
        app.guide_states,
        solver_name=app.selected_solver,
        heuristic=app.heuristic if app.selected_solver == 'A*' else None,
    )
    if res:
        app.guide_solution = res['solution']
        app.guide_states = res['states']
        app.next_step_info = {'action': res['action'], 'next_state': res['next_state']}
        if not app.replay:
            from collections import deque
            app.replay = deque(res['solution'])
            app.replay_done = []
            app.replay_total = len(res['solution'])
    else:
        app.next_step_info = None
app._update_step_guide = my_update_step_guide

# Now test: user presses SPACE (SWITCH)
print('\n--- USER PRESSES SPACE (CORRECT SWITCH) ---')
app.do_action('SWITCH', from_replay=False)
act_after = app.next_step_info['action']
print('Next step info after SPACE:', act_after)
assert act_after == 'D', f'Expected D, got {act_after}'
print('[PASS] After pressing SPACE, next step is D! NOT repeating SWITCH!')

# Now test: user presses SPACE AGAIN BY MISTAKE (accidental switch)
print('\n--- USER PRESSES SPACE BY MISTAKE (ACCIDENTAL SWITCH) ---')
app.do_action('SWITCH', from_replay=False)
act_accidental = app.next_step_info['action']
print('Next step info after accidental switch:', act_accidental)
assert act_accidental == 'SWITCH', f'Expected SWITCH back, got {act_accidental}'
print('[PASS] After accidental switch, guide tells user to SWITCH back!')

# User presses SPACE to switch back
print('\n--- USER PRESSES SPACE TO SWITCH BACK ---')
app.do_action('SWITCH', from_replay=False)
act_back = app.next_step_info['action']
print('Next step info after switching back:', act_back)
assert act_back == 'D', f'Expected D, got {act_back}'
print('[PASS] After switching back, guide resumes with D!')

# Now finish the level following the guide!
print('\n--- FINISHING THE REST OF THE LEVEL ---')
while app.session.status == Status.PLAYING and app.next_step_info:
    act = app.next_step_info['action']
    app.do_action(act, from_replay=False)
    while app.anims:
        app.update(0.05, (0, 0))

print('Final session status:', app.session.status)
assert app.session.status == Status.WON, 'Should win the level!'
print('[PASS] Successfully won Classic 09 by following the guide!')
pygame.quit()

