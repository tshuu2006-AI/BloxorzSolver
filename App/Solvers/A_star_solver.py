"""A* search with selectable admissible heuristics.

Heuristics return estimates in cost units.  The project's roll cost is at least
1, and a roll moves a block by at most two grid cells in one axis.
"""

from typing import Dict, Type

from App.Components.node import Node
from App.Solvers.base_solver import BestFirstSearchSolver
from App.Solvers.heuristics import (
    BaseHeuristic,
    ManhattanHeuristic,
    ModifiedManhattanHeuristic,
    RelaxedConfigurationHeuristic,
)

HEURISTICS: Dict[str, Type[BaseHeuristic]] = {
    "manhattan": ManhattanHeuristic,
    "modified_manhattan": ModifiedManhattanHeuristic,
    "relaxed": RelaxedConfigurationHeuristic,
}


class AstarSolver(BestFirstSearchSolver):
    """A* solver with the currently registered heuristic options."""

    def __init__(self):
        super().__init__()
        self._heuristic_name = "relaxed"
        self._heuristic: BaseHeuristic = HEURISTICS[self._heuristic_name]()

    def evaluate(self, node: Node)  :
        # Among equal f-scores, prefer the deeper node. This preserves A*'s
        # ordering by f while usually reducing plateau expansions.
        return (
            node.path_cost + self._heuristic(node.state, self.problem),
            -node.path_cost,
        )

    @property
    def heuristic(self) -> str:
        """Getter trả về tên heuristic hiện tại hoặc hàm heuristic tùy ý."""
        return self._heuristic_name


    @heuristic.setter
    def heuristic(self, heuristic_name: str):
        try:
            heuristic_type = HEURISTICS[heuristic_name]
        except KeyError as exc:
            choices = ", ".join(HEURISTICS)
            raise ValueError(f"Unknown heuristic {heuristic_name!r}; choose {choices}") from exc
        self._heuristic = heuristic_type()
        self._heuristic_name = heuristic_name
