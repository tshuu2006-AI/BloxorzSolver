
class Problem:

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

    def is_goal(self, s: State) -> bool:
        """Đích chỉ đạt được khi khối đứng thẳng (STANDING) tại ô đích."""
        return s.is_goal(self.goal_pos)

    def action_cost(self, s: State, a, s_new: State) -> int:
        return 1

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

        # 2. Xử lý hợp nhất (merge) nếu đang SPLIT mà 2 khối đứng cạnh nhau
        if new_orient == Orientation.SPLIT:
            merge_res = self._check_merge(new_b1, new_b2)
            if merge_res is not None:
                new_orient, new_b1, new_b2 = merge_res

        # 3. Kiểm tra tính hợp lệ trên mặt sàn (valid tiles check)
        if not self._is_supported(new_orient, new_b1, new_b2, s.bridges_state):
            return None

        # 4. Kích hoạt switch (nếu dẫm lên)
        new_bridges, split_triggered = self._process_switches(
            new_orient, new_b1, new_b2, s.bridges_state
        )

        # Nếu kích hoạt Split Switch: dịch chuyển và tách thành 2 khối 1x1x1
        if split_triggered is not None:
            p1, p2 = split_triggered
            return State(
                orientation=Orientation.SPLIT,
                b1=p1,
                b2=p2,
                active_block=0,
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
        b1: Tuple[int, int],
        b2: Tuple[int, int],
        current_bridges: Tuple[bool, ...],
    ):
        """Xử lý kích hoạt switch và trả về (trạng thái cầu mới, tọa độ split nếu có)."""
        bridges = list(current_bridges)
        cells = [b1] if orient == Orientation.STANDING else [b1, b2]
        split_triggered = None

        for pos in cells:
            sw = self.switches.get(pos)
            if sw is None:
                continue

            # Soft switch: kích hoạt bất kể tư thế hay kích thước khối
            if sw.switch_type == SwitchType.SOFT:
                self._apply_switch(sw, bridges)

            # Heavy switch: chỉ kích hoạt khi khối nguyên vẹn STANDING trên ô đó
            elif (
                sw.switch_type == SwitchType.HEAVY
                and orient == Orientation.STANDING
            ):
                self._apply_switch(sw, bridges)

            # Split switch: chỉ kích hoạt khi khối nguyên vẹn STANDING trên ô đó
            elif (
                sw.switch_type == SwitchType.SPLIT
                and orient == Orientation.STANDING
            ):
                split_triggered = sw.split_targets

        return tuple(bridges), split_triggered

    def _apply_switch(self, sw: Switch, bridges: List[bool]):
        for b_pos in sw.linked_bridges:
            idx = self.bridge_indices[b_pos]
            if sw.mode == SwitchMode.TOGGLE:
                bridges[idx] = not bridges[idx]
            elif sw.mode == SwitchMode.PERMANENT:
                bridges[idx] = sw.target_state

