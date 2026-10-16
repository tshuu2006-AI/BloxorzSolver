from typing import List
from App.Components.state import State

class Node:

    def __init__(
        self, state: State, parent=None, action=None, path_cost: int = 0
    ):
        self.state: State = state
        self.action = action
        self.parent = parent
        self.path_cost = path_cost

    @property
    def parent(self):
        return self._parent

    @parent.setter
    def parent(self, value) -> None:
        self._parent = value

    @property
    def state(self) -> State:
        return self._state

    @state.setter
    def state(self, value: State) -> None:
        self._state = value

    def __lt__(self, other) -> bool:
        return self.path_cost < other.path_cost

    def extract_solution(self) -> List[str]:
        """Truy vết ngược lại danh sách hành động từ nút gốc đến nút hiện tại."""
        actions = []
        curr = self
        while curr.parent is not None:
            actions.append(curr.action)
            curr = curr.parent
        return actions[::-1]