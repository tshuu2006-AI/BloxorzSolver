import heapq
import time
import tracemalloc
from typing import Dict, List, Optional, Any

from App.Components.node import Node
from App.Components.problem import Problem
from App.Components.state import State
from App.Solvers.base_solver import BaseSolver

class UCSSolver(BaseSolver):
    def __init__(self):
        super().__init__()

    def solve(self, problem: Problem) -> Optional[List[str]]:
        start_time = time.time()
        tracemalloc.start()

        self.expanded_nodes = 0
        root_node = Node(state=problem.initial_state, path_cost=0)

        frontier: List[Node] = []
        heapq.heappush(frontier, root_node)

        best_cost : Dict[State, int] = {root_node.state: 0}
        solution: Optional[List[str]] = None

        while frontier:
            current_node = heapq.heappop(frontier)
            current_state = current_node.state

            if current_node.path_cost > best_cost.get(current_state, float('inf')):
                continue  # Bỏ qua nếu đã có đường đi rẻ hơn đến trạng thái này

            self.expanded_nodes += 1

            if problem.is_goal(current_node.state):
                solution = current_node.extract_solution()
                solution_cost = current_node.path_cost
                solution_length = len(solution)
                break

            for action in problem.actions(current_state):
                child_state = problem.result(current_state, action)
                if child_state is None:
                    continue
                step_cost = problem.action_cost(current_state, action, child_state)
                child_cost = current_node.path_cost + step_cost

                if child_cost < best_cost.get(child_state, float('inf')):
                    best_cost[child_state] = child_cost
                    child_node = Node(state=child_state, parent=current_node, action=action, path_cost=child_cost)
                    heapq.heappush(frontier, child_node)

        self.search_time = time.time() - start_time
        self.memory_usage = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()

        return solution