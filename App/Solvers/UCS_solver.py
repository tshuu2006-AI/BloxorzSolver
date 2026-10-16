from App.Solvers.base_solver import BestFirstSearchSolver
from App.Components.node import Node
class UCSSolver(BestFirstSearchSolver):
    def __init__(self):
        super().__init__()


    def evaluate(self, node: Node):
        return node.path_cost
