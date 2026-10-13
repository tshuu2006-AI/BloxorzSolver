class Node:

    def __init__(
        self, state: State, parent=None, action=None, path_cost: int = 0
    ):
        self.state: State = state
        self.action = action
        self.parent = parent
        self.path_cost = path_cost

    def __lt__(self, other: Node) -> bool:
        return self.path_cost < other.path_cost

    def extract_solution(self) -> List[str]:
        """Truy vết ngược lại danh sách hành động từ nút gốc đến nút hiện tại."""
        actions = []
        curr = self
        while curr.parent is not None:
            actions.append(curr.action)
            curr = curr.parent
        return actions[::-1]