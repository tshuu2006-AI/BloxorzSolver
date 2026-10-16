import time
import tracemalloc
from typing import Dict, List, Optional, Callable

from App.Components.node import Node
from App.Components.problem import Problem
from App.Components.state import State
from abc import ABC, abstractmethod
import heapq
import itertools

class BaseSolver(ABC):
    def __init__(self):
        self.search_time: float = 0.0
        self.memory_usage: int = 0  # Lưu theo Bytes (hoặc đổi sang KB/MB)
        self.expanded_nodes: int = 0
        self.solution_length: int = 0
        self.solution_cost: int = 0
        self.problem: Problem

    @abstractmethod
    def solve(self, problem: Problem):
        pass

    def get_metrics(self) -> dict:
        """Trả về các chỉ số đánh giá để hiển thị lên GUI hoặc xuất báo cáo."""
        return {
            "search_time_sec": round(self.search_time, 6),
            "peak_memory_kb": round(self.memory_usage / 1024, 2),
            "expanded_nodes": self.expanded_nodes,
            "solution_length": self.solution_length,
            "solution_cost": self.solution_cost,
        }

class PriorityQueue:
    def __init__(self, key: Callable = lambda x: x):
        self._heap = []
        self._key = key
        # Dùng bộ đếm tăng dần để tránh lỗi so sánh 2 Node khi điểm f(n) bằng nhau
        self._counter = itertools.count()

    def push(self, item):
        priority = self._key(item)
        count = next(self._counter)
        heapq.heappush(self._heap, (priority, count, item))

    def pop(self):
        return heapq.heappop(self._heap)[2]

    def __len__(self):
        return len(self._heap)

class BestFirstSearchSolver(BaseSolver):
    """Best First Search Algorithm"""
    def __init__(self):
        super().__init__()

    @abstractmethod
    def evaluate(self, node: Node) -> float:
        pass


    def solve(self, problem: Problem) -> Optional[List[str]]:
        self.problem = problem
        start_time = time.time()
        tracemalloc.start()

        self.expanded_nodes = 0
        root_node = Node(state=problem.initial_state, path_cost=0)

        frontier: PriorityQueue = PriorityQueue(key = self.evaluate)
        frontier.push(root_node)

        best_cost: Dict[State, int] = {root_node.state: 0}
        solution: Optional[List[str]] = None

        while frontier:
            current_node = frontier.pop()
            current_state = current_node.state

            if current_node.path_cost > best_cost.get(current_state, float('inf')):
                continue  # Bỏ qua nếu đã có đường đi rẻ hơn đến trạng thái này

            self.expanded_nodes += 1

            if problem.is_goal(current_node.state):
                solution = current_node.extract_solution()
                self.solution_cost = current_node.path_cost
                self.solution_length = len(solution)
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
                    frontier.push(child_node)

        self.search_time = time.time() - start_time
        self.memory_usage = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()

        return solution



