

class State:
    def __init__(self):
        pass


class Problem:
    def __init__(self):
        self.initial : State



    def is_goal(self, s : State)->bool:
        pass


    def result(self, s : State, a)->State:
        pass


    def action_cost(self, s : State, a, s_new: State)->int:
        pass

    def actions(self, s: State)->list:
        pass

class Node:
    def __init__(self, state:State, parent, action, path_cost:int ):
        self.state: State = state
        self.action = action
        self.parent = parent
        self.path_cost = path_cost

def expand(problem: Problem, node:Node):
    s = node.state
    for action in problem.actions(s):
        s_new = problem.result(s, action)
        cost = node.path_cost + problem.action_cost(s, action, s_new)
        yield Node(state=s_new, parent=node, action=action, path_cost=cost)
