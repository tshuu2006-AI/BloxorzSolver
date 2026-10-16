import argparse
import sys
from typing import List, Optional

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from App.Components.features import TileType, SwitchType, SwitchMode, Switch
from App.Components.state import Orientation, State
from App.Components.node import Node
from App.Components.problem import Problem
from App.Solvers.DFS_solver import DFSSolver
from App.Solvers.UCS_solver import UCSSolver
from App.Solvers.A_star_solver import AstarSolver



def verify_and_replay(problem: Problem, actions: Optional[List[str]], metrics: dict):
    """Mô phỏng lại từng bước đi của lời giải để kiểm tra tính đúng đắn."""
    if actions is None:
        print("  [KẾT QUẢ] Không tìm thấy lời giải (None)!")
        return

    print(f"  [KẾT QUẢ] Tìm thấy lời giải: {actions}")
    print(f"  [THÔNG SỐ] Số bước (Length): {metrics['solution_length']} | "
          f"Tổng chi phí (Cost): {metrics['solution_cost']} | "
          f"Nodes mở rộng: {metrics['expanded_nodes']} | "
          f"Thời gian: {metrics['search_time_sec']}s | "
          f"Bộ nhớ đỉnh: {metrics['peak_memory_kb']} KB")

    curr_state = problem.initial
    total_cost = 0
    print(f"    Bước 0 (Khởi tạo): {curr_state}")

    for i, action in enumerate(actions, 1):
        next_state = problem.result(curr_state, action)
        if next_state is None:
            print(f"    [LỖI] Bước {i}: Hành động '{action}' làm khối rơi hoặc không hợp lệ!")
            return
        step_cost = problem.action_cost(curr_state, action, next_state)
        total_cost += step_cost
        curr_state = next_state
        print(f"    Bước {i} (Hành động '{action}', +{step_cost} cost): {curr_state}")

    if problem.is_goal(curr_state):
        print("  => XÁC NHẬN: Đã đứng thẳng (STANDING) tại đúng ô GOAL thành công!\n")
    else:
        print("  => [LỖI]: Trạng thái cuối cùng chưa phải là GOAL!\n")

def print_ascii_map(problem: Problem):
    """In bản đồ ra Terminal dưới dạng ASCII để dễ quan sát cấu trúc màn chơi."""
    all_coords = list(problem.grid.keys())
    max_r = max(r for r, _ in all_coords)
    max_c = max(c for _, c in all_coords)
    init_cells = problem.initial.get_occupied_cells()

    print("\n  [BẢN ĐỒ MÀN CHƠI (ASCII)]")
    print("  Ký hiệu: S=Start | G=Goal | #=Floor | ^=Fragile | ==Bridge | o=SoftSw | X=HeavySw | %=SplitSw | .=Void")
    header = "     " + " ".join(f"{c:2d}" for c in range(max_c + 1))
    print(header)
    print("    +" + "---" * (max_c + 1) + "+")

    for r in range(max_r + 1):
        row_str = f" {r:2d} | "
        for c in range(max_c + 1):
            pos = (r, c)
            tile = problem.grid.get(pos, TileType.VOID)
            if pos in init_cells:
                ch = " S"
            elif pos == problem.goal_pos:
                ch = " G"
            elif pos in problem.switches:
                sw_type = problem.switches[pos].switch_type
                if sw_type == SwitchType.SOFT:
                    ch = " o"
                elif sw_type == SwitchType.HEAVY:
                    ch = " X"
                else:
                    ch = " %"
            elif tile == TileType.FLOOR:
                ch = " #"
            elif tile == TileType.FRAGILE:
                ch = " ^"
            elif tile == TileType.BRIDGE:
                ch = " ="
            else:
                ch = " ."
            row_str += ch + " "
        print(row_str + "|")
    print("    +" + "---" * (max_c + 1) + "+\n")


# =====================================================================
# TEST 1: MÀN CHƠI CƠ BẢN (CHỈ CÓ FLOOR VÀ GOAL)
# =====================================================================
def build_test_1_basic() -> Problem:
    """
    Bản đồ chữ L:
    Xuất phát tại (0, 0) STANDING -> Lăn phải 2 lần tới (0, 3) -> Lăn xuống 2 lần tới (3, 3) GOAL.
    Lời giải kỳ vọng: ['R', 'R', 'D', 'D'] (4 bước)
    """
    grid = {
        (0, 0): TileType.FLOOR,
        (0, 1): TileType.FLOOR,
        (0, 2): TileType.FLOOR,
        (0, 3): TileType.FLOOR,
        (1, 3): TileType.FLOOR,
        (2, 3): TileType.FLOOR,
        (3, 3): TileType.GOAL,
    }
    initial_state = State(Orientation.STANDING, (0, 0))
    return Problem(
        grid=grid,
        goal_pos=(3, 3),
        initial_state=initial_state,
        bridge_indices={},
        switches={},
    )


# =====================================================================
# TEST 2: MÀN CHƠI CÓ Ô MỎNG (FRAGILE) - SO SÁNH CHI PHÍ ĐỒNG NHẤT & RỦI RO
# =====================================================================
def build_test_2_fragile() -> Problem:
    """
    Xuất phát: (0, 0), Đích: (0, 3).
    - Đường 1 (Ngắn nhưng nguy hiểm): Đi thẳng hàng 0 qua (0, 1) và (0, 2) là ô FRAGILE.
      Chỉ mất 2 bước: ['R', 'R'].
    - Đường 2 (Đường vòng an toàn): Đi xuống hàng 1 & 2 toàn bộ là FLOOR rồi vòng lên (0, 3).
      Mất 5 bước: ['D', 'R', 'R', 'R', 'U'].
    """
    grid = {
        # Hàng 0: Đường tắt qua ô mỏng FRAGILE
        (0, 0): TileType.FLOOR,
        (0, 1): TileType.FRAGILE,
        (0, 2): TileType.FRAGILE,
        (0, 3): TileType.GOAL,
        # Hàng 1 & 2: Đường vòng toàn bộ bằng sàn cứng FLOOR
        (1, 0): TileType.FLOOR, (1, 1): TileType.FLOOR, (1, 2): TileType.FLOOR, (1, 3): TileType.FLOOR,
        (2, 0): TileType.FLOOR, (2, 1): TileType.FLOOR, (2, 2): TileType.FLOOR, (2, 3): TileType.FLOOR,
    }
    initial_state = State(Orientation.STANDING, (0, 0))
    return Problem(
        grid=grid,
        goal_pos=(0, 3),
        initial_state=initial_state,
        bridge_indices={},
        switches={},
    )


# =====================================================================
# TEST 3: MÀN CHƠI CÓ CẦU (BRIDGES) VÀ CÔNG TẮC (SOFT & HEAVY SWITCH)
# =====================================================================
def build_test_3_bridges_and_switches() -> Problem:
    """
    Bản đồ thẳng hàng 0 từ cột 0 đến cột 6:
    - (0, 0): Xuất phát STANDING
    - (0, 1): Có SOFT Switch -> Bật cầu tại (0, 4)
    - (0, 3): Có HEAVY Switch (chỉ bật khi STANDING) -> Bật cầu tại (0, 5)
    - (0, 4) và (0, 5): Hai ô BRIDGE ban đầu đều đóng (False, False)
    - (0, 6): GOAL
    Lời giải kỳ vọng: ['R', 'R', 'R', 'R'] (4 bước)
    """
    grid = {
        (0, 0): TileType.FLOOR,
        (0, 1): TileType.FLOOR,
        (0, 2): TileType.FLOOR,
        (0, 3): TileType.FLOOR,
        (0, 4): TileType.BRIDGE,
        (0, 5): TileType.BRIDGE,
        (0, 6): TileType.GOAL,
    }
    bridge_indices = {
        (0, 4): 0,
        (0, 5): 1,
    }
    switches = {
        (0, 1): Switch(
            pos=(0, 1),
            switch_type=SwitchType.SOFT,
            linked_bridges=[(0, 4)],
            mode=SwitchMode.TOGGLE,
        ),
        (0, 3): Switch(
            pos=(0, 3),
            switch_type=SwitchType.HEAVY,
            linked_bridges=[(0, 5)],
            mode=SwitchMode.PERMANENT,
            target_state=True,
        ),
    }
    # Ban đầu cả 2 cây cầu đều đóng (False, False)
    initial_state = State(
        orientation=Orientation.STANDING,
        b1=(0, 0),
        bridges_state=(False, False),
    )
    return Problem(
        grid=grid,
        goal_pos=(0, 6),
        initial_state=initial_state,
        bridge_indices=bridge_indices,
        switches=switches,
    )


# =====================================================================
# TEST 4: MÀN CHƠI TÁCH KHỐI (SPLIT SWITCH), ĐỔI KHỐI ("SWITCH") & GHÉP KHỐI
# =====================================================================
def build_test_4_split_and_merge() -> Problem:
    """
    Kịch bản:
    1. Xuất phát tại (0, 0) -> Lăn 'R', 'R' để đứng thẳng (STANDING) tại (0, 3).
    2. Ô (0, 3) có SPLIT Switch tách khối thành 2 khối đơn tại b1=(1, 2) và b2=(3, 2),
       mặc định điều khiển b1 (active_block = 0).
    3. Giữa (1, 2) và (3, 2) là ô cầu (2, 2) đang ĐÓNG (False), nên b1 bị kẹt tại (1, 2).
    4. Người chơi phải dùng hành động 'SWITCH' để chuyển sang điều khiển b2 tại (3, 2).
    5. Điều khiển b2 đi 'R' sang (3, 3) để dẫm SOFT Switch mở cầu (2, 2),
       sau đó đi 'L' về (3, 2) rồi đi 'U' lên (2, 2).
    6. Tại (2, 2), b2 đứng sát b1 ở (1, 2) -> Tự động GHÉP (Merge) thành khối VERTICAL.
    7. Lăn 'D' một nhịp để khối đứng thẳng (STANDING) vào đúng đích (3, 2).
    Lời giải kỳ vọng: ['R', 'R', 'SWITCH', 'R', 'L', 'U', 'D'] (7 bước)
    """
    grid = {
        # Khu vực đầu màn chơi
        (0, 0): TileType.FLOOR,
        (0, 1): TileType.FLOOR,
        (0, 2): TileType.FLOOR,
        (0, 3): TileType.FLOOR,
        # Khu vực sau khi tách khối
        (1, 2): TileType.FLOOR,
        (2, 2): TileType.BRIDGE,  # Cầu nối giữa 2 khối đơn
        (3, 2): TileType.GOAL,
        (3, 3): TileType.FLOOR,   # Nơi đặt công tắc mở cầu
    }
    bridge_indices = {(2, 2): 0}
    switches = {
        (0, 3): Switch(
            pos=(0, 3),
            switch_type=SwitchType.SPLIT,
            linked_bridges=[],
            split_targets=((1, 2), (3, 2)),
        ),
        (3, 3): Switch(
            pos=(3, 3),
            switch_type=SwitchType.SOFT,
            linked_bridges=[(2, 2)],
            mode=SwitchMode.PERMANENT,
            target_state=True,
        ),
    }
    initial_state = State(
        orientation=Orientation.STANDING,
        b1=(0, 0),
        bridges_state=(False,),
    )
    return Problem(
        grid=grid,
        goal_pos=(3, 2),
        initial_state=initial_state,
        bridge_indices=bridge_indices,
        switches=switches,
    )

# =====================================================================
# TEST 5: MÀN CHƠI LỚN & HÓC BÚA ("THE GAUNTLET" - 10x11)
# =====================================================================
def build_test_5_hardcore_stage() -> Problem:
    """
    Màn chơi lớn kích thước 10x11 gồm 4 cụm đảo, yêu cầu 32-34 bước đi:
    - Đảo 1: Giải bài toán đổi hướng (Parity) có rìa gạch mỏng FRAGILE để đứng lên Heavy Switch.
    - Đảo 2: Vòng tránh bẫy FRAGILE để tiếp cận Split Switch.
    - Đảo 3: Phối hợp 2 khối đơn 1x1x1 mở cầu chéo cho nhau rồi hợp nhất (Merge).
    - Đảo 4: Lựa chọn giữa đường tắt qua 6 ô FRAGILE (32 bước) và đường vòng FLOOR an toàn (34 bước).
    """
    grid = {
        # --- ĐẢO 1 (Tây Bắc): Đổi parity & kích hoạt Heavy Switch tại (2, 3) ---
        (0, 2): TileType.FRAGILE, (0, 3): TileType.FRAGILE,
        (1, 1): TileType.FLOOR,   (1, 2): TileType.FLOOR, (1, 3): TileType.FLOOR, (1, 4): TileType.FLOOR,
        (2, 1): TileType.FLOOR,   (2, 2): TileType.FLOOR, (2, 3): TileType.FLOOR, (2, 4): TileType.FLOOR,
        (3, 1): TileType.FLOOR,   (3, 2): TileType.FLOOR,

        # --- CẦU NỐI ĐẢO 1 -> ĐẢO 2 ---
        (2, 5): TileType.BRIDGE,  (2, 6): TileType.BRIDGE,

        # --- ĐẢO 2 (Đông Bắc): Bẫy Fragile & Split Switch tại (1, 10) ---
        (1, 10): TileType.FLOOR,
        (2, 7): TileType.FLOOR,   (2, 8): TileType.FLOOR, (2, 9): TileType.FRAGILE, (2, 10): TileType.FLOOR,
        (3, 7): TileType.FLOOR,   (3, 8): TileType.FLOOR, (3, 9): TileType.FRAGILE, (3, 10): TileType.FLOOR,
        (4, 7): TileType.FLOOR,   (4, 8): TileType.FLOOR, (4, 9): TileType.FLOOR,

        # --- ĐẢO 3 (Khu vực tách khối & phối hợp mở cầu ở hàng 6, 7) ---
        # Nhánh trái của khối đơn b1 (xuất hiện tại (6, 2))
        (6, 2): TileType.FLOOR,   (6, 3): TileType.FLOOR,
        (7, 2): TileType.FLOOR,   (7, 3): TileType.FLOOR,
        # Cầu số 2 nối b1 vào điểm hợp nhất
        (6, 4): TileType.BRIDGE,
        # Điểm hợp nhất trung tâm & nhánh phải của khối đơn b2 (xuất hiện tại (6, 8))
        (6, 5): TileType.FLOOR,   (6, 6): TileType.FLOOR,
        (6, 7): TileType.BRIDGE,  # Cầu số 3 nối b2 từ (6, 8) vào trung tâm
        (6, 8): TileType.FLOOR,
        (7, 7): TileType.FLOOR,   # Nơi đặt Soft Switch mở cầu cho b1

        # --- ĐẢO 4 (Khu vực về Đích tại (9, 6)) ---
        # Nhánh A: Đường tắt đi qua 6 ô FRAGILE ở cột 4, 5
        (7, 4): TileType.FRAGILE, (7, 5): TileType.FRAGILE,
        (8, 4): TileType.FRAGILE, (8, 5): TileType.FRAGILE,
        (9, 4): TileType.FRAGILE, (9, 5): TileType.FRAGILE,

        # Nhánh B: Đường vòng an toàn toàn bộ bằng FLOOR ở cột 7, 8
        (7, 8): TileType.FLOOR,
        (8, 7): TileType.FLOOR,   (8, 8): TileType.FLOOR,
        (9, 7): TileType.FLOOR,   (9, 8): TileType.FLOOR,

        # Ô Đích (GOAL)
        (9, 6): TileType.GOAL,
    }

    bridge_indices = {
        (2, 5): 0,  # Cầu 0 nối Đảo 1 -> Đảo 2
        (2, 6): 1,  # Cầu 1 nối Đảo 1 -> Đảo 2
        (6, 4): 2,  # Cầu 2 cho khối b1 đi vào điểm ghép
        (6, 7): 3,  # Cầu 3 cho khối b2 đi vào điểm ghép
    }

    switches = {
        # Heavy Switch ở Đảo 1: Phải đứng thẳng (STANDING) tại (2, 3) mới mở được Cầu 0 & 1
        (2, 3): Switch(
            pos=(2, 3),
            switch_type=SwitchType.HEAVY,
            linked_bridges=[(2, 5), (2, 6)],
            mode=SwitchMode.PERMANENT,
            target_state=True,
        ),
        # Split Switch ở Đảo 2: Đứng tại (1, 10) tách thành 2 khối đơn ở (6, 2) và (6, 8)
        (1, 10): Switch(
            pos=(1, 10),
            switch_type=SwitchType.SPLIT,
            linked_bridges=[],
            split_targets=((6, 2), (6, 8)),
        ),
        # Soft Switch bên nhánh trái (7, 3): Khối b1 dẫm lên để mở Cầu 3 (6, 7) cho khối b2
        (7, 3): Switch(
            pos=(7, 3),
            switch_type=SwitchType.SOFT,
            linked_bridges=[(6, 7)],
            mode=SwitchMode.PERMANENT,
            target_state=True,
        ),
        # Soft Switch bên nhánh phải (7, 7): Khối b2 dẫm lên để mở Cầu 2 (6, 4) cho khối b1
        (7, 7): Switch(
            pos=(7, 7),
            switch_type=SwitchType.SOFT,
            linked_bridges=[(6, 4)],
            mode=SwitchMode.PERMANENT,
            target_state=True,
        ),
    }

    initial_state = State(
        orientation=Orientation.STANDING,
        b1=(1, 1),
        bridges_state=(False, False, False, False),
    )

    return Problem(
        grid=grid,
        goal_pos=(9, 6),
        initial_state=initial_state,
        bridge_indices=bridge_indices,
        switches=switches,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Run the Bloxorz sample problems.")
    parser.add_argument(
        "--solver", choices=("dfs", "ucs", "astar"), default="dfs",
        help="Search algorithm to use: dfs, ucs, or astar (default: dfs).",
    )
    parser.add_argument(
        "--heuristic", choices=("manhattan", "orientation", "relaxed"),
        default="relaxed",
        help="A* heuristic (only used with --solver astar; default: relaxed).",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.solver == "astar":
        solver = AstarSolver()
        solver.heuristic = args.heuristic
        solver_label = f"A* ({args.heuristic})"
    elif args.solver == "dfs":
        solver = DFSSolver()
        solver_label = "Depth-First Search (DFS)"
    else:
        solver = UCSSolver()
        solver_label = "Uniform-Cost Search (UCS)"

    print("=" * 70)
    print(f"CHẠY KIỂM THỬ THUẬT TOÁN {solver_label}")
    print("=" * 70)

    # Chạy Test 1
    print("\n--- TEST 1: Màn cơ bản (Basic Rolling) ---")
    p1 = build_test_1_basic()
    sol1 = solver.solve(p1)
    verify_and_replay(p1, sol1, solver.get_metrics())

    # So sánh đường đi với chi phí mặc định và mức phạt fragile cao.
    print("--- TEST 2A: Màn Fragile (Chi phí mặc định) ---")
    p2 = build_test_2_fragile()
    sol2 = solver.solve(p2)
    verify_and_replay(p2, sol2, solver.get_metrics())

    print("--- TEST 2B: Màn Fragile (Tăng phạt ô FRAGILE lên +10) ---")
    # Ghi đè thử nghiệm hàm chi phí phạt nặng ô FRAGILE để xem UCS tự động đi đường vòng
    def high_risk_cost(s: State, a: str, s_new: State) -> int:
        cost = 2
        for cell in s_new.get_occupied_cells():
            if p2.grid.get(cell) == TileType.FRAGILE:
                cost += 10
        return cost

    p2.action_cost = high_risk_cost
    sol2_safe = solver.solve(p2)
    verify_and_replay(p2, sol2_safe, solver.get_metrics())

    # Chạy Test 3
    print("--- TEST 3: Màn có Cầu & Công tắc (Soft + Heavy Switches) ---")
    p3 = build_test_3_bridges_and_switches()
    sol3 = solver.solve(p3)
    verify_and_replay(p3, sol3, solver.get_metrics())

    # Chạy Test 4
    print("--- TEST 4: Màn Tách khối (Split Switch), Đổi khối & Hợp nhất (Merge) ---")
    p4 = build_test_4_split_and_merge()
    sol4 = solver.solve(p4)
    verify_and_replay(p4, sol4, solver.get_metrics())

    # Chạy Test 5 (Bản đồ lớn & phức tạp)
    print("--- TEST 5: Map Lớn 'The Gauntlet' ---")
    p5 = build_test_5_hardcore_stage()
    print_ascii_map(p5)
    sol5_uniform = solver.solve(p5)
    verify_and_replay(p5, sol5_uniform, solver.get_metrics())
