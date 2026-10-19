"""
Implementation of Uniform-cost search solver
"""
from App.Components.node import Node
from App.Solvers.base_solver import BestFirstSearchSolver


class UCSSolver(BestFirstSearchSolver):
    def __init__(self):
        """
        Initialize an UCS solver.
        """
        super().__init__()


    def evaluate(self, node: Node) -> float|int:
        """
        Evaluate the current state by the path cost
        :param node: a node that represents the current state (Node).
        :return: path_cost: the cost value (float|int).
        """
        path_cost = node.path_cost
        return path_cost