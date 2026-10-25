"""Bloxorz board rules, transitions, goal checks, and action costs."""

from typing import Dict, List, Optional, Tuple

from App.Components.features import TileType, Switch, SwitchType, SwitchMode
from App.Components.state import State, Orientation


class Problem:
    """Bloxorz board rules, transitions, and goal definition."""

    def __init__(
        self,
        grid: Dict[Tuple[int, int], TileType],
        goal_pos: Tuple[int, int],
        initial_state: State,
        bridge_indices: Dict[Tuple[int, int], int],
        switches: Dict[Tuple[int, int], Switch],
    ):
        """Khởi tạo bài toán Bloxorz.

        :param grid: Bản đồ lưu loại ô tại từng tọa độ (r, c).
        :param goal_pos: Tọa độ đích (r, c).
        :param initial_state: Trạng thái ban đầu.
        :param bridge_indices: Ánh xạ từ tọa độ cầu (r, c) sang index trong
        state.bridges_state.
        :param switches: Ánh xạ từ tọa độ switch (r, c) sang đối tượng Switch.
        """
        self.grid = grid
        self.goal_pos = goal_pos
        self.initial: State = initial_state
        self.bridge_indices = bridge_indices
        self.switches = switches

    @property
    def initial_state(self) -> State:
        """Return the initial game state."""
        return self.initial

    def is_goal(self, s: State) -> bool:
        """Đích chỉ đạt được khi khối đứng thẳng (STANDING) tại ô đích."""
        return s.is_goal(self.goal_pos)

    def action_cost(self, s: State, a: str, s_new: State) -> int:
        # 1. Đổi khối điều khiển khi đang SPLIT tốn ít chi phí nhất
        if a == "SWITCH":
            return 1

        cost = 2  # Chi phí lăn cơ bản trên mặt sàn thường

        # 2. Phạt chi phí nếu lăn đè lên ô mỏng (FRAGILE) vì độ rủi ro cao
        for cell in s_new.get_occupied_cells():
            if self.grid.get(cell) == TileType.FRAGILE:
                cost += 1
                break

        # 3. Nếu dựng khối từ nằm lên đứng thẳng (STANDING), tốn thêm lực nâng trọng tâm
        # if s.orientation != Orientation.STANDING and s_new.orientation == Orientation.STANDING:
        #     cost += 1

        # 4. Khuyến khích (giảm chi phí) nếu nước đi kích hoạt công tắc làm mở/đổi trạng thái cầu
        if s.bridges_state != s_new.bridges_state:
            cost = max(1, cost - 1)

        return cost

    def actions(self, s: State) -> list:
        """Trả về các hành động hợp lệ từ trạng thái s."""
        possible_moves = ["U", "D", "L", "R"]
        if s.is_split:
            possible_moves.append("SWITCH")

        valid_actions = []
        for a in possible_moves:
            next_state = self.result(s, a)
            if next_state is not None:
                valid_actions.append(a)
        return valid_actions

    def result(self, s: State, a: str) -> Optional[State]:
        """Tính toán trạng thái kế tiếp khi thực hiện hành động a.

        Trả về None nếu nước đi không hợp lệ (rơi ra ngoài, đứng lên fragile,
        v.v.).
        """
        if a == "SWITCH":
            if not s.is_split:
                return None
            return State(
                orientation=Orientation.SPLIT,
                b1=s._b1,
                b2=s._b2,
                active_block=1 - s.active_block,
                bridges_state=s.bridges_state,
            )

        # 1. Tính toán vị trí và hướng hình học mới sau khi lăn
        res = self._compute_next_geometry(s, a)
        if res is None:
            return None
        new_orient, new_b1, new_b2 = res

        # 1b. Khối đơn 1x1x1 lăn vào ô đích sẽ rơi xuống hố và thua
        if s.is_split:
            moved = new_b1 if s.active_block == 0 else new_b2
            if moved == self.goal_pos:
                return None

        # 2. Xử lý hợp nhất (merge) nếu đang SPLIT mà 2 khối đứng cạnh nhau
        if new_orient == Orientation.SPLIT:
            merge_res = self._check_merge(new_b1, new_b2)
            if merge_res is not None:
                new_orient, new_b1, new_b2 = merge_res

        # 3. Kiểm tra tính hợp lệ trên mặt sàn (valid tiles check)
        if not self._is_supported(new_orient, new_b1, new_b2, s.bridges_state):
            return None

        # 4. Kích hoạt switch (nếu dẫm lên). Khi đang SPLIT chỉ khối vừa lăn
        # mới dẫm vào ô mới; khối đứng yên không kích hoạt lại switch dưới nó.
        if s.is_split:
            landed = (res[1],) if s.active_block == 0 else (res[2],)
        elif new_orient == Orientation.STANDING:
            landed = (new_b1,)
        else:
            landed = (new_b1, new_b2)
        new_bridges, split_triggered = self._process_switches(
            new_orient, landed, s.bridges_state
        )

        # Cầu đóng lại ngay dưới khối (do switch vừa kích hoạt) => rơi
        if new_bridges != s.bridges_state and not self._is_supported(
            new_orient, new_b1, new_b2, new_bridges
        ):
            return None

        # Nếu kích hoạt Split Switch: dịch chuyển và tách thành 2 khối 1x1x1
        # (cầu được xử lý trước, dịch chuyển sau)
        if split_triggered is not None:
            (p1, p2), active = split_triggered
            if not self._is_supported(Orientation.SPLIT, p1, p2, new_bridges):
                return None
            return State(
                orientation=Orientation.SPLIT,
                b1=p1,
                b2=p2,
                active_block=active,
                bridges_state=new_bridges,
            )

        return State(
            orientation=new_orient,
            b1=new_b1,
            b2=new_b2,
            active_block=s.active_block,
            bridges_state=new_bridges,
        )

    # ---------------- Các hàm bổ trợ logic chuyển động ----------------

    def _compute_next_geometry(self, s: State, a: str):
        """Compute the block orientation and occupied cells after a roll."""
        delta = {"U": (-1, 0), "D": (1, 0), "L": (0, -1), "R": (0, 1)}
        dr, dc = delta[a]

        if s.orientation == Orientation.STANDING:
            r, c = s._b1
            if a == "L":
                return Orientation.HORIZONTAL, (r, c - 2), (r, c - 1)
            elif a == "R":
                return Orientation.HORIZONTAL, (r, c + 1), (r, c + 2)
            elif a == "U":
                return Orientation.VERTICAL, (r - 2, c), (r - 1, c)
            elif a == "D":
                return Orientation.VERTICAL, (r + 1, c), (r + 2, c)

        elif s.orientation == Orientation.HORIZONTAL:
            r, c = s._b1  # Chiếm (r, c) và (r, c + 1)
            if a == "L":
                return Orientation.STANDING, (r, c - 1), (r, c - 1)
            elif a == "R":
                return Orientation.STANDING, (r, c + 2), (r, c + 2)
            elif a == "U":
                return Orientation.HORIZONTAL, (r - 1, c), (r - 1, c + 1)
            elif a == "D":
                return Orientation.HORIZONTAL, (r + 1, c), (r + 1, c + 1)

        elif s.orientation == Orientation.VERTICAL:
            r, c = s._b1  # Chiếm (r, c) và (r + 1, c)
            if a == "L":
                return Orientation.VERTICAL, (r, c - 1), (r + 1, c - 1)
            elif a == "R":
                return Orientation.VERTICAL, (r, c + 1), (r + 1, c + 1)
            elif a == "U":
                return Orientation.STANDING, (r - 1, c), (r - 1, c)
            elif a == "D":
                return Orientation.STANDING, (r + 2, c), (r + 2, c)

        elif s.orientation == Orientation.SPLIT:
            r1, c1 = s._b1
            r2, c2 = s._b2
            if s.active_block == 0:
                new_b1 = (r1 + dr, c1 + dc)
                if new_b1 == s._b2:  # Không được đi đè lên khối còn lại
                    return None
                return Orientation.SPLIT, new_b1, s._b2
            else:
                new_b2 = (r2 + dr, c2 + dc)
                if new_b2 == s._b1:
                    return None
                return Orientation.SPLIT, s._b1, new_b2

        return None

    def _check_merge(self, b1: Tuple[int, int], b2: Tuple[int, int]):
        """Kiểm tra 2 khối 1x1 có đứng sát nhau để ghép lại thành khối 1x1x2 hay không."""
        r1, c1 = b1
        r2, c2 = b2
        # Cùng hàng, kề cột -> HORIZONTAL
        if r1 == r2 and abs(c1 - c2) == 1:
            left_col = min(c1, c2)
            return (
                Orientation.HORIZONTAL,
                (r1, left_col),
                (r1, left_col + 1),
            )
        # Cùng cột, kề hàng -> VERTICAL
        if c1 == c2 and abs(r1 - r2) == 1:
            top_row = min(r1, r2)
            return (
                Orientation.VERTICAL,
                (top_row, c1),
                (top_row + 1, c1),
            )
        return None

    def _is_supported(
        self,
        orient: Orientation,
        b1: Tuple[int, int],
        b2: Tuple[int, int],
        bridges_state: Tuple[bool, ...],
    ) -> bool:
        """Kiểm tra khối có được đỡ hoàn toàn bởi các ô hợp lệ hay không."""
        cells = [b1] if orient == Orientation.STANDING else [b1, b2]

        for r, c in cells:
            tile = self.grid.get((r, c), TileType.VOID)
            if tile == TileType.VOID:
                return False
            if tile == TileType.BRIDGE:
                idx = self.bridge_indices.get((r, c))
                if idx is None or not bridges_state[idx]:
                    return False  # Cầu đang đóng coi như khoảng trống

        # Khối 1x1x2 đứng thẳng trên ô mỏng (FRAGILE) sẽ làm sập gạch và rơi
        if orient == Orientation.STANDING:
            if self.grid.get(b1) == TileType.FRAGILE:
                return False

        return True

    def _process_switches(
        self,
        orient: Orientation,
        landed: Tuple[Tuple[int, int], ...],
        current_bridges: Tuple[bool, ...],
    ):
        """Xử lý kích hoạt switch tại các ô vừa được dẫm lên.

        Trả về (trạng thái cầu mới, ((p1, p2), khối đang điều khiển) nếu có split).

        Quy tắc khi một nước đi kích hoạt nhiều switch:
        - Với mỗi cầu, "mở" + "đóng" cùng lúc, hoặc hai lần "toggle" => triệt
          tiêu nhau (cầu giữ nguyên).
        - Các trường hợp còn lại: áp dụng tất cả hiệu ứng.
        - Cầu được xử lý trước, dịch chuyển (split) xử lý sau.
        """
        # idx -> [số lệnh mở, số lệnh đóng, số lệnh toggle]
        effects: Dict[int, List[int]] = {}
        split_triggered = None

        for pos in landed:
            sw = self.switches.get(pos)
            if sw is None:
                continue

            # Soft switch: kích hoạt bất kể tư thế hay kích thước khối.
            # Heavy / Split switch: chỉ kích hoạt khi khối nguyên vẹn STANDING.
            if sw.switch_type != SwitchType.SOFT and orient != Orientation.STANDING:
                continue

            for b_pos, mode, target in sw.bridge_effects():
                counts = effects.setdefault(self.bridge_indices[b_pos], [0, 0, 0])
                if mode == SwitchMode.TOGGLE:
                    counts[2] += 1
                elif target:
                    counts[0] += 1
                else:
                    counts[1] += 1

            if sw.switch_type == SwitchType.SPLIT:
                split_triggered = (sw.split_targets, sw.split_active)

        bridges = list(current_bridges)
        for idx, (opens, closes, toggles) in effects.items():
            if opens and not closes:
                bridges[idx] = True
            elif closes and not opens:
                bridges[idx] = False
            if toggles % 2:
                bridges[idx] = not bridges[idx]

        return tuple(bridges), split_triggered
