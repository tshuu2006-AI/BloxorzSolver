# BloxorzSolver

Bloxorz game (pygame GUI) plus search solvers (BFS / DFS / UCS / A*) for the CSC14003 Project 1.

## Setup and run

```bash
pip install -r requirements.txt
python play.py                      # open the game
python play.py classic 12           # jump to Classic 12;  `python play.py custom 5` = custom stage 5
python App/test.py --solver all     # test all solvers (BFS, DFS, UCS, A*) on sample stages
python main.py                      # benchmark comparison table across test stages
python -m unittest discover -s tests -t .   # unit tests (121 tests)
```

Controls: arrows / WASD roll the block (the "Move keys" compass in the corner shows where each key goes on
screen, and gold arrows on the floor show the same around the piece you control), `Space` swaps the active cube
when split, `R` restart (or `Enter` on game over), `Z` undo, `N` stage select, `Enter` next stage after a win, `F11` fullscreen.

Camera: `Q`/`E` or mouse wheel zoom, right-mouse drag rotates and tilts (or `[` `]` rotate, `PgUp`/`PgDn` tilt),
middle-mouse drag pans, `C` resets the view.

**Compare all** (next to the SOLVERS label) runs every available algorithm on the current stage one after another (each in its own process, 60 s timeout, so a slow one can't freeze the game) and opens a table of moves, cost, expanded nodes, time and peak memory with bars, the best value per column highlighted, and an *optimal* tag. Click a row to replay that algorithm's solution; **Save CSV** writes `results/compare_<stage>.csv`. All four solvers (BFS, DFS, UCS, A*) are fully supported.

After a solver finishes, its path is drawn on the board as numbered tiles (`V` or the Path button toggles it). While a replay is paused,
`,` and `.` (or the arrow buttons) step it backward and forward. Cleared stages and your best move counts are remembered in
`.bloxorz_progress.json` (git-ignored). The default view runs the board west-to-east with a 15 degree tilt
(`AXIS_TILT_DEG` in `App/GUI/theme.py`).
The window is a 1920x1080 canvas scaled to your screen.

## Layout

| Path | What |
|---|---|
| `App/Components/` | Rules engine shared by the game and solvers: `state.py`, `features.py`, `problem.py`, `node.py`, and `level_loader.py` (JSON -> `Problem`) |
| `App/Solvers/` | Search algorithms (`BaseSolver`, BFS, DFS, UCS, A*) |
| `App/Game/` | GUI-independent game logic: `GameSession` (moves, undo, win/fall), `solver_bridge.py` (runs a solver from the GUI), `experiment.py` / `compare.py` (Compare all), `race_logic.py`, `settings.py`, `progress.py`, `tips.py`, `links.py`, `path.py`, `synth.py` (sound effects) |
| `App/GUI/` | pygame app (`app.py`), isometric renderer (`render.py`), `race.py`, `compare_view.py`, `audio.py`, widgets, theme |
| `play.py` | Launches the game (`python play.py [classic\|custom] [n]`) |
| `main.py`, `App/test.py` | Teammates' command-line runner and hand-built test stages |
| `tools/benchmark.py` | Benchmark script for the report (see Benchmark below) |
| `levels/classic/*.json` | The 33 original stages (`NOTICE.md` has the source) |
| `levels/*.json` | Custom stages (our own), loaded in file-name order |
| `tests/` | Unit tests (transition table, every tile type, session, all stages solvable) |

## Stages

### Classic - the 33 original levels (`levels/classic/`)

Recreated from the original game; see `levels/classic/NOTICE.md` for the source and licensing note. Our rules engine reproduces the published minimum move count on every one of them (1999 in total, checked by `tests/test_classic.py`).

| # | Size | Min moves | Features |
|---|---|---|---|
| 1 | 6x10 | 7 | plain |
| 2 | 6x15 | 17 | bridges, switches |
| 3 | 6x15 | 19 | plain |
| 4 | 9x14 | 28 | fragile |
| 5 | 10x15 | 33 | bridges, switches |
| 6 | 10x15 | 35 | plain |
| 7 | 8x15 | 44 | bridges, switches |
| 8 | 9x15 | 10 | teleporters |
| 9 | 5x15 | 24 | teleporters |
| 10 | 10x14 | 57 | bridges, teleporters, switches |
| 11 | 10x12 | 47 | bridges, switches |
| 12 | 10x13 | 65 | bridges, switches |
| 13 | 10x14 | 46 | fragile |
| 14 | 10x14 | 67 | bridges, switches |
| 15 | 10x15 | 57 | bridges, teleporters, switches |
| 16 | 8x13 | 28 | bridges, teleporters, switches |
| 17 | 10x15 | 106 | bridges, switches |
| 18 | 9x15 | 85 | bridges, switches |
| 19 | 10x15 | 67 | bridges, switches |
| 20 | 10x15 | 56 | bridges, teleporters, switches |
| 21 | 10x15 | 71 | bridges, switches |
| 22 | 10x14 | 65 | bridges, switches |
| 23 | 10x15 | 75 | fragile, bridges, teleporters, switches |
| 24 | 8x14 | 57 | bridges, teleporters, switches |
| 25 | 10x14 | 55 | bridges, switches |
| 26 | 9x14 | 104 | bridges, teleporters, switches |
| 27 | 10x15 | 71 | fragile, bridges, switches |
| 28 | 10x15 | 100 | fragile, bridges, teleporters, switches |
| 29 | 10x15 | 104 | bridges, switches |
| 30 | 10x15 | 114 | fragile, bridges, switches |
| 31 | 10x15 | 91 | fragile, bridges, switches |
| 32 | 9x14 | 129 | bridges, switches |
| 33 | 10x15 | 65 | bridges, switches |

### Custom stages - 20 stages in `levels/`, grouped by difficulty (simple, fragile, switch, split, combined). Numbers below come from the default UCS cost function (`Problem.action_cost`); `moves` excludes `SWITCH` actions.

| # | Stage | Group | Size | UCS moves | UCS cost | UCS expanded |
|---|---|---|---|---|---|---|
| 1 | First Roll | simple | 6x10 | 6 | 14 | 35 |
| 2 | Detour | simple | 7x10 | 9 | 22 | 134 |
| 3 | Staircase | simple | 5x10 | 10 | 23 | 66 |
| 4 | Long Walk | simple | 8x14 | 12 | 29 | 84 |
| 5 | Risky Shortcut | fragile | 3x4 | 2 | 8 | 7 |
| 6 | Thin Ice | fragile | 4x14 | 12 | 38 | 71 |
| 7 | Minefield | fragile | 3x13 | 14 | 39 | 89 |
| 8 | Cracked Bridge | fragile | 14x10 | 21 | 52 | 228 |
| 9 | Soft Touch | switch | 3x13 | 10 | 24 | 16 |
| 10 | Toggle Trap | switch | 3x13 | 10 | 23 | 16 |
| 11 | Crossed Wires | switch | 3x13 | 13 | 30 | 117 |
| 12 | Heavy Duty | switch | 3x10 | 20 | 46 | 70 |
| 13 | Two Keys | switch | 4x22 | 32 | 75 | 116 |
| 14 | Split and Merge | split | 5x5 | 6 | 14 | 41 |
| 15 | Thin Meeting | split | 5x11 | 10 | 36 | 321 |
| 16 | Twin Rooms | split | 5x11 | 14 | 28 | 482 |
| 17 | Obstacle Course | combined | 4x28 | 25 | 70 | 150 |
| 18 | The Gauntlet | combined | 10x11 | 29 | 76 | 786 |
| 19 | Switchboard | combined | 6x24 | 16 | 38 | 1990 |
| 20 | Grand Tour | combined | 12x28 | 55 | 134 | 912 |

### Settings, tips and extras

The right-hand panel has two tabs (**Tab** switches): **PLAY** keeps the everyday controls, **SETTINGS** holds the rest
(theme selection: Antarctica / Desert, move-keys compass, camera help, floor arrows, switch link lines, default tilt, tips, camera reset, screenshot, reset progress).
The A* heuristic selector stays on the PLAY tab next to the solver buttons. Choices are saved to `.bloxorz_settings.json` (git-ignored).

- **Switch link lines** (off by default): dashed lines from each switch to the bridges it controls (dot = opens, x = closes,
  ring = toggles) and from a split switch to its two landing cells.
- **Tips**: the first time a mechanic (rolling, fragile tiles, switches/bridges, heavy switches, splitting) appears, a small card
  explains it. They can be switched off or shown again in Settings.
- **Split cubes**: the cube you control is bright with a white outline and a bouncing arrow; the other is dark and translucent.
- **Screenshots**: `F12` or the Settings button saves `screenshots/bloxorz_<time>.png` (git-ignored).
- **Polish**: the block squashes a little when it lands, a soft glow with rising sparks marks a switch that fires
  (and the bridges it changes), the goal hole opens and swallows the block on a win (dropping inside with sound effects),
  and the stage picker shows isometric previews with page numbers and arrow buttons.
- **Sound**: short effects (landing thud, switch click, bridge open/close, split/merge, fall, win) are synthesized in
  code (`App/Game/synth.py`), so there are no audio files. `M` or Settings > Sound mutes them; volume is a slider
  there. If no audio device exists the game simply stays silent.
- **Race**: in the Compare table, tick two algorithms and press **Race** to play their solutions side by side, each on
  its own board, one action at a time, with per-algorithm stats and a "who arrives first" result.
## Benchmark (for the report's Experiments section)

```bash
python tools/benchmark.py                           # every stage (classic + custom) x every available solver
python tools/benchmark.py --set classic             # only the 33 originals (`--set custom`: only the custom ones)
python tools/benchmark.py --repeat 5 --timeout 120  # median of 5 runs, kill a run after 120 s
python tools/benchmark.py --set custom --levels 1-8,20 --solvers "UCS,A*"
python tools/benchmark.py --plots                   # also writes results/*.png
```

It runs BFS, DFS, UCS, "UCS (risk)" (fragile tiles cost +10, like Test 2B), and A* with each
heuristic, records search time, peak memory, expanded nodes, solution length/cost, and checks that every solution replays
to the goal. Results go to `results/benchmark.csv` (git-ignored) plus an optional chart per metric and a per-group summary.

## Rules (as implemented in `App/Components/problem.py`)

- The block wins only when **standing** on the goal. Lying across the goal is fine.
- A **fragile** tile breaks if the whole block stands on it. A single cube can stand on it.
- A closed **bridge** behaves like void. If a switch closes a bridge under the block, it falls.
- **Soft** switch: any part of the block (or a cube) triggers it. **Heavy** and **split** switches need the whole block standing.
- A switch triggers only when a piece *lands* on it. A cube resting on a switch does not retrigger when the other cube moves.
- Several switches in one move: per bridge, open+close or toggle+toggle cancel; otherwise every effect applies. Bridges resolve before the split teleport.
- **Split** switch teleports to its fixed `targets` and splits the block in two cubes. Cubes merge when side by side.
- A cube entering the goal cell falls and loses. Two cubes cannot overlap (the move is simply blocked).
- `SWITCH` (change the active cube) is an action in the search space. The GUI move counter does not count it.

## Level format (`levels/*.json`)

```json
{
  "name": "Soft Touch", "group": "switch", "description": "...",
  "grid": ["......o......", "......#......", "S######BBB##G"],
  "bridges": [{"cells": [[2, 7], [2, 8], [2, 9]], "open": false}],
  "switches": [{"pos": [0, 6], "mode": "toggle", "link": [0]}]
}
```

Grid characters: `.` void, `#` floor, `S` start, `G` goal, `F` fragile, `B` bridge (must belong to a `bridges` group),
`o` soft, `x` heavy, `p` split switch. Switch `mode` is `toggle`, `open` or `close` (permanent). A split switch has
`"targets": [[r, c], [r, c]]` instead of `link`, plus an optional `"active": 0 | 1` (which cube is selected right after
the split; default 0). A switch that needs a different mode per bridge uses
`"effects": [{"bridge": 0, "mode": "open"}, {"bridge": 1, "mode": "toggle"}]` instead of `link` + `mode`.
An optional top-level `"reference_moves"` records a known minimum number of rolls (used by the tests on the classic stages).

## Plugging in a solver

The GUI finds solvers by name and greys the button out if the file is missing:

| Button | File | Class |
|---|---|---|
| BFS | `App/Solvers/BFS_solver.py` | `BFSSolver` |
| DFS | `App/Solvers/DFS_solver.py` | `DFSSolver` |
| UCS | `App/Solvers/UCS_solver.py` | `UCSSolver` |
| A* | `App/Solvers/A_star_solver.py` | `AstarSolver` (with a `heuristic` property) |

A solver needs `solve(problem) -> list[str] | None` (actions `'U','D','L','R','SWITCH'`) and `get_metrics()`
(see `BaseSolver`). The GUI replays the returned actions and reports an illegal action if it finds one.
