class BaseSolver():
    def __init__(self):
        self.search_time: float = 0.0
        self.memory_usage: int = 0  # Lưu theo Bytes (hoặc đổi sang KB/MB)
        self.expanded_nodes: int = 0
        self.solution_length: int = 0
        self.solution_cost: int = 0


    def solve(self):
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