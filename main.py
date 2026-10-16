import argparse
import sys
import time

# Đảm bảo in tiếng Việt chuẩn trên Terminal Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from App.Components.state import State
from App.Components.features import TileType
from App.Solvers.DFS_solver import DFSSolver
from App.Solvers.UCS_solver import UCSSolver
from App.Solvers.A_star_solver import AstarSolver
from App.test import (
    build_test_1_basic,
    build_test_2_fragile,
    build_test_3_bridges_and_switches,
    build_test_4_split_and_merge,
    build_test_5_hardcore_stage,
    verify_and_replay,
    print_ascii_map,
)


def get_test_cases():
    # Test 2B: Màn phạt nặng Fragile (+10)
    def build_test_2b_fragile_high_risk():
        p = build_test_2_fragile()
        def high_risk_cost(s: State, a: str, s_new: State) -> int:
            cost = 2
            for cell in s_new.get_occupied_cells():
                if p.grid.get(cell) == TileType.FRAGILE:
                    cost += 10
            return cost
        p.action_cost = high_risk_cost
        return p

    return [
        ("Test 1: Cơ bản (Basic)", build_test_1_basic),
        ("Test 2A: Sàn mỏng (Fragile default)", build_test_2_fragile),
        ("Test 2B: Sàn mỏng (Fragile phạt +10)", build_test_2b_fragile_high_risk),
        ("Test 3: Cầu & Công tắc (Switches)", build_test_3_bridges_and_switches),
        ("Test 4: Tách & Hợp nhất khối (Split)", build_test_4_split_and_merge),
        ("Test 5: Map lớn (The Gauntlet)", build_test_5_hardcore_stage),
    ]


def run_single_solver(solver_name: str, heuristic: str = "relaxed"):
    if solver_name == "dfs":
        solver = DFSSolver()
        label = "Depth-First Search (DFS)"
    elif solver_name == "ucs":
        solver = UCSSolver()
        label = "Uniform-Cost Search (UCS)"
    elif solver_name == "astar":
        solver = AstarSolver()
        solver.heuristic = heuristic
        label = f"A* ({heuristic})"
    else:
        raise ValueError(f"Thuật toán không hợp lệ: {solver_name}")

    print("=" * 70)
    print(f"  CHẠY KIỂM THỬ THUẬT TOÁN: {label}")
    print("=" * 70)

    for name, builder in get_test_cases():
        print(f"\n--- {name} ---")
        problem = builder()
        if "Test 5" in name:
            print_ascii_map(problem)
        actions = solver.solve(problem)
        verify_and_replay(problem, actions, solver.get_metrics())


def run_benchmark_comparison():
    print("=" * 80)
    print("  SO SÁNH HIỆU NĂNG CÁC THUẬT TOÁN (BENCHMARK COMPARISON)")
    print("=" * 80)

    solvers = [
        ("DFS", lambda: DFSSolver()),
        ("UCS", lambda: UCSSolver()),
        ("A* (relaxed)", lambda: AstarSolver()),
    ]

    test_cases = get_test_cases()

    # In tiêu đề bảng
    header = f"{'Test Case':<32} | {'Thuật toán':<13} | {'Số bước':<8} | {'Chi phí':<8} | {'Nodes duyệt':<12} | {'Thời gian':<10} | {'Bộ nhớ':<10}"
    print("\n" + header)
    print("-" * len(header))

    for test_name, builder in test_cases:
        for solver_label, solver_fn in solvers:
            problem = builder()
            solver = solver_fn()
            actions = solver.solve(problem)
            m = solver.get_metrics()
            steps = m['solution_length'] if actions is not None else "N/A"
            cost = m['solution_cost'] if actions is not None else "N/A"
            nodes = m['expanded_nodes']
            sec = f"{m['search_time_sec']:.4f}s"
            mem = f"{m['peak_memory_kb']:.1f} KB"

            row = f"{test_name:<32} | {solver_label:<13} | {str(steps):<8} | {str(cost):<8} | {str(nodes):<12} | {sec:<10} | {mem:<10}"
            print(row)
        print("-" * len(header))


def parse_args():
    parser = argparse.ArgumentParser(description="Bloxorz Solver Runner")
    parser.add_argument(
        "--solver",
        choices=("dfs", "ucs", "astar", "compare"),
        default="compare",
        help="Thuật toán muốn chạy: dfs, ucs, astar, hoặc compare (mặc định: compare)",
    )
    parser.add_argument(
        "--heuristic",
        choices=("manhattan", "orientation", "relaxed"),
        default="relaxed",
        help="Heuristic cho A* (chỉ dùng khi --solver astar; mặc định: relaxed)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.solver == "compare":
        run_benchmark_comparison()
    else:
        run_single_solver(args.solver, args.heuristic)
