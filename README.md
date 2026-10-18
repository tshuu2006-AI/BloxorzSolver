# BloxorzSolver

Bloxorz game (pygame GUI) plus search solvers (BFS / DFS / UCS / A*) for the CSC14003 Project 1.

## Setup and run

```bash
pip install -r requirements.txt
python play.py          # open the game; `python play.py 5` starts at stage 5
python -m App.test --solver ucs   # CLI check of the hand-built test levels
python -m unittest discover -s tests -t .   # unit tests
```

Controls: arrows / WASD roll the block (the "Move keys" compass in the corner shows where each key goes on
screen, and gold arrows on the floor show the same around the piece you control), `Space` swaps the active cube
when split, `R` restart, `Z` undo, `N` stage select, `Enter` next stage after a win, `F11` fullscreen.

Camera: `Q`/`E` or mouse wheel zoom, right-mouse drag rotates and tilts (or `[` `]` rotate, `PgUp`/`PgDn` tilt),
middle-mouse drag pans, `C` resets the view. The default view runs the board west-to-east with a 15 degree tilt
(`AXIS_TILT_DEG` in `App/GUI/theme.py`).
The window is a 1920x1080 canvas scaled to your screen.

## Layout

| Path | What |
|---|---|
| `App/Components/` | Rules engine shared by the game and solvers: `state.py`, `features.py`, `problem.py`, `node.py`, and `level_loader.py` (JSON -> `Problem`) |
| `App/Solvers/` | Search algorithms (`BaseSolver`, DFS, UCS, A*) |
| `App/Game/` | `GameSession` (moves, undo, win/fall) and `solver_bridge.py` (runs a solver from the GUI) |
| `App/GUI/` | pygame app (`app.py`), isometric renderer (`render.py`), widgets, theme |
| `levels/*.json` | Stages, loaded in file-name order |
| `tests/` | Unit tests (transition table, every tile type, session, all stages solvable) |

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
`"targets": [[r, c], [r, c]]` instead of `link`.

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
