"""
Implementation of a solver with Depth-First Search Algorithm
"""
from typing import Optional, List

from App.Components.node import Node
from App.Components.problem import Problem
from App.Solvers.base_solver import BaseSolver


class DFSSolver(BaseSolver):
    """Implementation of a solver with Depth-First Search Algorithm"""
    def __init__(self):
        super().__init__()

    def _search(self, problem: Problem) -> Optional[List[str]]:
        """
        :param problem: the problem that need to be solved
        :return:
        """
        self.expanded_nodes = 0
        root_node = Node(state=problem.initial_state)
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

        return solution
