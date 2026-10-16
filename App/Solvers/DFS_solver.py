import time
import tracemalloc
from typing import Optional, List
from App.Solvers.base_solver import BaseSolver
from App.Components.node import Node
from App.Components.problem import Problem

class DFSSolver(BaseSolver):

    def solve(self, problem: Problem) -> Optional[List[str]]:
        self.problem = problem
        start_time = time.time()
        tracemalloc.start()

        self.expanded_nodes = 0
        root_node = Node(state=problem.initial_state, path_cost=0)
        stack = [root_node]
        visited = {root_node.state}

        solution: Optional[List[str]] = None

        while stack:
            current_node = stack.pop()
            current_state = current_node.state

            self.expanded_nodes += 1

            if problem.is_goal(current_state):
                solution = current_node.extract_solution()
                self.solution_cost = current_node.path_cost
                self.solution_length = len(solution)
                break

            for action in problem.actions(current_state):
                next_state = problem.result(current_state, action)
                if next_state is not None and next_state not in visited:
                    visited.add(next_state)
                    step_cost = problem.action_cost(current_state, action, next_state)
                    child_node = Node(
                        state=next_state,
                        parent=current_node,
                        action=action,
                        path_cost=current_node.path_cost + step_cost
                    )
                    stack.append(child_node)

        self.search_time = time.time() - start_time
        self.memory_usage = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()

        return solution
