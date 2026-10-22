"""Admissible A* heuristics for the project's weighted Bloxorz rules.

The current action-cost function has a minimum cost of 1 (a split-control
switch, or a roll that changes bridge state). All estimates below are therefore
expressed in units of that minimum cost.
"""

from abc import ABC, abstractmethod
import heapq
from itertools import combinations
from typing import Dict, Iterable, List, Tuple

from App.Components import Problem, State
from App.Components.state import Orientation
from App.Components.features import SwitchType, TileType

Coordinate = Tuple[int, int]


class BaseHeuristic(ABC):
    @abstractmethod
    def __call__(self, state: State, problem: Problem) -> float:
        raise NotImplementedError

class ManhattanHeuristic(BaseHeuristic):
    """Conservative geometric lower bound in minimum-action-cost units.

    Each ordinary roll changes the block center by at most 1.5 Manhattan
    cells. A split switch can teleport the block, so this simple estimate is
    zero on boards containing split switches. Bridge discounts are handled by
    using the global minimum step cost (1), rather than assuming rolls cost 2.
    """

    def __call__(self, state: State, problem: Problem) -> float:
        if any(sw.switch_type == SwitchType.SPLIT for sw in problem.switches.values()):
            return 0

        cells = state.get_occupied_cells()
        center_r = sum(r for r, _ in cells) / len(cells)
        center_c = sum(c for _, c in cells) / len(cells)
        goal_r, goal_c = problem.goal_pos
        center_distance = abs(center_r - goal_r) + abs(center_c - goal_c)
        return int((center_distance + 1.5 - 1e-9) // 1.5)

    def __str__(self):
        return "Manhattan"


class OrientationManhattanHeuristic(ManhattanHeuristic):
    """Manhattan lower bound strengthened by the required final orientation."""

    def __call__(self, state: State, problem: Problem) -> float:
        h = super().__call__(state, problem)
        if state.orientation in (Orientation.HORIZONTAL, Orientation.VERTICAL):
            return max(h, 1)  # At least one roll is required to become standing.
        if state.orientation == Orientation.SPLIT:
            return max(h, 2)  # Merge to a lying block, then stand on the goal.
        return h

    def __str__(self):
        return "Orientation Manhattan"


class RelaxedConfigurationHeuristic(BaseHeuristic):
    """Shortest lower-bound cost in a relaxed orientation-aware puzzle graph.

    The abstraction preserves block orientation, split-piece positions and
    merging, and split-switch teleports. It preserves void and fragile-tile
    support rules, treats every bridge as open, and ignores bridge-state switch
    effects. Those relaxations can add routes but cannot remove a real route.
    Abstract rolls cost 1 when they do not land on fragile cells and 4 when
    they do; the latter is the real minimum 2 + 3 - 1 bridge discount. A
    control switch costs 1. These are lower bounds on the current real action
    costs, so Dijkstra's distance is admissible.

    Distances are computed once per Problem object and reused for every state
    evaluated by the solver.
    """

    def __init__(self):
        self._cached_problem = None
        self._distances: Dict[State, int] = {}

    def __call__(self, state: State, problem: Problem) -> float:
        if problem is not self._cached_problem:
            self._distances = self._build_distances(problem)
            self._cached_problem = problem
        # A zero fallback remains admissible for a state outside the abstract
        # graph (for example, a malformed board configuration).
        return self._distances.get(self._without_bridges(state), 0)

    @staticmethod
    def _without_bridges(state: State) -> State:
        return State(
            orientation=state.orientation,
            b1=state._b1,
            b2=state._b2,
            active_block=state.active_block,
            bridges_state=(),
        )

    @classmethod
    def _build_distances(cls, problem: Problem) -> Dict[State, int]:
        cells = {
            pos for pos, tile in problem.grid.items()
            if tile != TileType.VOID
        }
        cells = sorted(cells)

        abstract_states: List[State] = []
        for cell in cells:
            if cls._supported(problem, Orientation.STANDING, (cell,)):
                abstract_states.append(State(Orientation.STANDING, cell))

        cell_set = set(cells)
        for r, c in cells:
            if (r, c + 1) in cell_set:
                occupied = ((r, c), (r, c + 1))
                if cls._supported(problem, Orientation.HORIZONTAL, occupied):
                    abstract_states.append(State(Orientation.HORIZONTAL, *occupied))
            if (r + 1, c) in cell_set:
                occupied = ((r, c), (r + 1, c))
                if cls._supported(problem, Orientation.VERTICAL, occupied):
                    abstract_states.append(State(Orientation.VERTICAL, *occupied))

        for first, second in combinations(cells, 2):
            if cls._supported(problem, Orientation.SPLIT, (first, second)):
                abstract_states.append(State(Orientation.SPLIT, first, second, active_block=0))
                abstract_states.append(State(Orientation.SPLIT, first, second, active_block=1))

        reverse_edges: Dict[State, List[Tuple[State, int]]] = {}
        for current in abstract_states:
            for successor, action in cls._successors(current, problem):
                weight = cls._edge_lower_bound(successor, action, problem)
                reverse_edges.setdefault(successor, []).append((current, weight))

        goal = State(Orientation.STANDING, problem.goal_pos)
        distances = {goal: 0}
        queue = [(0, 0, goal)]
        sequence = 1
        while queue:
            current_distance, _, current = heapq.heappop(queue)
            if current_distance != distances.get(current):
                continue
            for predecessor, weight in reverse_edges.get(current, ()):
                candidate = current_distance + weight
                if candidate < distances.get(predecessor, float("inf")):
                    distances[predecessor] = candidate
                    heapq.heappush(queue, (candidate, sequence, predecessor))
                    sequence += 1
        return distances

    @staticmethod
    def _edge_lower_bound(state: State, action: str, problem: Problem) -> int:
        if action == "SWITCH":
            return 1
        if any(problem.grid.get(cell) == TileType.FRAGILE for cell in state.get_occupied_cells()):
            return 4
        return 1

    @staticmethod
    def _supported(
        problem: Problem,
        orientation: Orientation,
        occupied: Tuple[Coordinate, ...],
    ) -> bool:
        for cell in occupied:
            tile = problem.grid.get(cell, TileType.VOID)
            if tile == TileType.VOID:
                return False
            if orientation == Orientation.STANDING and tile == TileType.FRAGILE:
                return False
        # Bridge cells are passable regardless of their actual state.
        return True

    @classmethod
    def _successors(
        cls, state: State, problem: Problem
    ) -> Iterable[Tuple[State, str]]:
        if state.is_split:
            yield (
                State(
                    Orientation.SPLIT, state._b1, state._b2,
                    active_block=1 - state.active_block,
                ),
                "SWITCH",
            )
            actions = ("U", "D", "L", "R")
        else:
            actions = ("U", "D", "L", "R")

        for action in actions:
            geometry = problem._compute_next_geometry(state, action)
            if geometry is None:
                continue
            orientation, b1, b2 = geometry

            if orientation == Orientation.SPLIT:
                merged = problem._check_merge(b1, b2)
                if merged is not None:
                    orientation, b1, b2 = merged

            occupied = (b1,) if orientation == Orientation.STANDING else (b1, b2)
            if not cls._supported(problem, orientation, occupied):
                continue

            # A normal standing block landing on a split switch is teleported
            # and divided. Model the whole real action as one abstract edge.
            if orientation == Orientation.STANDING:
                switch = problem.switches.get(b1)
                if (
                    switch is not None
                    and switch.switch_type == SwitchType.SPLIT
                    and switch.split_targets is not None
                    and cls._supported(problem, Orientation.SPLIT, switch.split_targets)
                ):
                    p1, p2 = switch.split_targets
                    yield (
                        State(
                            Orientation.SPLIT, p1, p2,
                            active_block=getattr(switch, "split_active", 0),
                        ),
                        action,
                    )
                    continue

            yield State(orientation, b1, b2), action

    def __str__(self):
        return "Relaxed Configuration Distance"


class ModifiedManhattanHeuristic(OrientationManhattanHeuristic):
    """Backward-compatible name for the orientation-aware Manhattan variant."""


class RelaxedPointHeuristic(RelaxedConfigurationHeuristic):
    """Backward-compatible descriptive name for the stronger relaxed search."""
