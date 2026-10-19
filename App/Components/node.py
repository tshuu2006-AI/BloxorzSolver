from typing import List

from App.Components.state import State


class Node:
    """A search-tree node linking a state to its predecessor and action."""

    def __init__(
        self, state: State, parent=None, action=None, path_cost: int = 0
    ):
        """Create a node for ``state`` with optional parent and path details."""
        self.state: State = state
        self.action = action
        self.parent = parent
        self.path_cost = path_cost

    @property
    def parent(self):
        """Return the preceding node in the search path, if any."""
        return self._parent

    @parent.setter
    def parent(self, value) -> None:
        """Set the preceding node in the search path."""
        self._parent = value

    @property
    def state(self) -> State:
        """Return the game state represented by this node."""
        return self._state

    @state.setter
    def state(self, value: State) -> None:
        """Set the game state represented by this node."""
        self._state = value

    def __lt__(self, other) -> bool:
        """Compare nodes by accumulated path cost."""
        return self.path_cost < other.path_cost

    def extract_solution(self) -> List[str]:
        """Trace parent links and return actions from root to this node."""
        actions = []
        curr = self
        while curr.parent is not None:
            actions.append(curr.action)
            curr = curr.parent
        return actions[::-1]
