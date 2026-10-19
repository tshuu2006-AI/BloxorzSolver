"""A* search and the three heuristic variants described in the project brief.

Heuristics return estimates in cost units.  The project's roll cost is at least
1, and a roll moves a block by at most two grid cells in one axis.
"""

from collections import deque
from typing import Callable, Dict, Tuple
import math
from App.Components.node import Node
from App.Components.problem import Problem
from App.Components.state import Orientation, State
from App.Solvers.base_solver import BestFirstSearchSolver

Coordinate = Tuple[int, int]
Heuristic = Callable[[State, Problem], float]


def _distance_to_goal(state: State, goal: Coordinate) -> int:
    """Minimum Manhattan distance from any occupied cell to the goal."""
    return min(abs(r - goal[0]) + abs(c - goal[1])
               for r, c in state.get_occupied_cells())


def heuristic_manhattan(state, problem) -> int:
    cells = state.get_occupied_cells()
    cr = sum(r for r, _ in cells) / len(cells)
    cc = sum(c for _, c in cells) / len(cells)
    gr, gc = problem.goal_pos
    return math.ceil((abs(cr - gr) + abs(cc - gc)) / 1.5)


def heuristic_orientation_aware(state: State, problem: Problem) -> float:
    """Idea 2: include the minimum rolls imposed by the current orientation."""
    h = heuristic_manhattan(state, problem)
    if state.orientation in (Orientation.HORIZONTAL, Orientation.VERTICAL):
        h = max(h, 1)
    elif state.orientation == Orientation.SPLIT:
        # Split cubes cannot finish the level; they must first merge, then stand.
        h = max(h, 2)
    return h


def _relaxed_point_distances(problem: Problem) -> Dict[Coordinate, int]:
    """Shortest point-walk distances on a relaxed board.

    All present tiles are passable and orientation/fragile restrictions are
    ignored. Split-switch destinations are added as free teleport edges, so
    the distance remains a lower bound even on boards with split switches.
    """
    goal = problem.goal_pos
    reverse_teleports: Dict[Coordinate, list[Coordinate]] = {}
    for switch in problem.switches.values():
        if switch.split_targets is not None:
            for target in switch.split_targets:
                reverse_teleports.setdefault(target, []).append(switch.pos)

    distances: Dict[Coordinate, int] = {goal: 0}
    queue = deque([goal])
    while queue:
        r, c = queue.popleft()
        neighbors = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
        neighbors.extend(reverse_teleports.get((r, c), ()))
        for pos in neighbors:
            if pos in problem.grid and pos not in distances:
                distances[pos] = distances[(r, c)] + 1
                queue.append(pos)
    return distances


def heuristic_relaxed_point(state: State, problem: Problem) -> float:
    """Idea 3: relaxed point-object shortest path, scaled for two-cell rolls."""
    distances = _relaxed_point_distances(problem)
    point_distance = min(
        (distances[cell] for cell in state.get_occupied_cells()
         if cell in distances),
        default=0,
    )
    estimate = (point_distance + 1) // 2
    if state.orientation in (Orientation.HORIZONTAL, Orientation.VERTICAL):
        estimate = max(estimate, 1)
    elif state.orientation == Orientation.SPLIT:
        estimate = max(estimate, 2)
    return estimate


HEURISTICS: Dict[str, Heuristic] = {
    "manhattan": heuristic_manhattan,
    "orientation": heuristic_orientation_aware,
    "relaxed": heuristic_relaxed_point,
}


def heuristic(state: State, problem: Problem) -> float:
    """Default heuristic (the third, relaxed point-object variant)."""
    return heuristic_relaxed_point(state, problem)


class AstarSolver(BestFirstSearchSolver):
    """A* solver; select ``manhattan``, ``orientation``, or ``relaxed``."""

    def __init__(self):
        super().__init__()
        self._heuristic_name = "relaxed"
        self._heuristic = HEURISTICS[self._heuristic_name]

    def evaluate(self, node: Node) -> float:
        return node.path_cost + self._heuristic(node.state, self.problem)

    @property
    def heuristic(self) -> str:
        """Getter trả về tên heuristic hiện tại hoặc hàm heuristic tùy ý."""
        return self._heuristic_name


    @heuristic.setter
    def heuristic(self, heuristic_name: str):
        try:
            self._heuristic = HEURISTICS[heuristic_name]
        except KeyError as exc:
            choices = ", ".join(HEURISTICS)
            raise ValueError(f"Unknown heuristic {heuristic_name!r}; choose {choices}") from exc
        self._heuristic_name = heuristic_name

