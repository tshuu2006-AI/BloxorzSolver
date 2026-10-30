"""Trình tải và dựng mô hình 3D cho Chim Cánh Cụt (Penguin) trong Bloxorz.

Hỗ trợ:
1. Đọc file ``Penguin.obj`` từ thư mục gốc hoặc thư mục ``assets/``.
2. Chuẩn hóa kích thước, căn giữa tại gốc tọa độ (0, 0, 0) để có thể xoay và lộn nhào 3D
   chính xác theo hệ trục định hướng của khối hộp 2x1x1.
3. Cung cấp hệ trục quay 3D (Frame3D) để theo dõi hướng đầu (head), mặt trước (front)
   và cánh phải (right) của chú chim sau mỗi cú lăn, lộn nhào hoặc nằm ngang.
4. Tích hợp sẵn mô hình low-poly nếu chưa có file .obj ngoài.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parents[2]

PENGUIN_SEARCH_PATHS = [
    Path(__file__).resolve().parent / "Penguin.obj",
    Path("App/GUI/Penguin.obj"),
    Path("Penguin.obj"),
    Path("assets/Penguin.obj"),
    ROOT_DIR / "App" / "GUI" / "Penguin.obj",
    ROOT_DIR / "Penguin.obj",
    ROOT_DIR / "assets" / "Penguin.obj",
    ROOT_DIR / "App" / "GUI" / "assets" / "Penguin.obj",
]

Vector3 = Tuple[int, int, int]
Frame3D = Tuple[Vector3, Vector3, Vector3]

# Trục mặc định khi khối đứng thẳng:
# - head: hướng đầu chim (hướng dọc theo trục dài của khối), mặc định hướng lên (+Z)
# - front: hướng bụng/mỏ chim, mặc định hướng về phía hàng tăng (+R)
# - right: hướng cánh phải chim, mặc định hướng về phía cột tăng (+C)
INITIAL_FRAME: Frame3D = ((0, 0, 1), (1, 0, 0), (0, 1, 0))


def roll_frame(frame: Frame3D, action: str) -> Frame3D:
    """Xoay hệ trục 3D của chim cánh cụt theo hướng lăn của khối (D, U, R, L).

    - Lăn D (+R): quay 90 độ quanh trục C: (r, c, z) -> (z, c, -r)
    - Lăn U (-R): quay 90 độ quanh trục -C: (r, c, z) -> (-z, c, r)
    - Lăn R (+C): quay 90 độ quanh trục R: (r, c, z) -> (r, z, -c)
    - Lăn L (-C): quay 90 độ quanh trục -R: (r, c, z) -> (r, -z, c)
    """
    head, front, right = frame
    act = action.strip().upper()[:1] if action else ""

    def _rot(v: Vector3) -> Vector3:
        r, c, z = v
        if act == "D":
            return (z, c, -r)
        elif act == "U":
            return (-z, c, r)
        elif act == "R":
            return (r, z, -c)
        elif act == "L":
            return (r, -z, c)
        return v

    return _rot(head), _rot(front), _rot(right)


def frame_for_orientation(orientation) -> Frame3D:
    """Duyệt frame cơ bản tương ứng với Orientation của khối khi chưa có lịch sử lăn."""
    from App.Components.state import Orientation

    if orientation == Orientation.STANDING:
        return ((0, 0, 1), (1, 0, 0), (0, 1, 0))
    elif orientation == Orientation.HORIZONTAL:
        return ((0, 1, 0), (1, 0, 0), (0, 0, -1))
    elif orientation == Orientation.VERTICAL:
        return ((1, 0, 0), (0, 0, -1), (0, 1, 0))
    return ((0, 0, 1), (1, 0, 0), (0, 1, 0))


def _find_penguin_file() -> Optional[Path]:
    for p in PENGUIN_SEARCH_PATHS:
        try:
            if p.is_file():
                return p.resolve()
        except OSError:
            continue
    return None


def parse_obj(path: Path) -> Tuple[List[Tuple[float, float, float]], List[List[int]]]:
    """Phân tích cú pháp file .obj: trả về danh sách đỉnh (x, y, z) và danh sách mặt tam giác."""
    raw_verts: List[Tuple[float, float, float]] = []
    faces: List[List[int]] = []

    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            cmd = parts[0].lower()
            if cmd == "v" and len(parts) >= 4:
                try:
                    vx, vy, vz = float(parts[1]), float(parts[2]), float(parts[3])
                    raw_verts.append((vx, vy, vz))
                except ValueError:
                    continue
            elif cmd == "f" and len(parts) >= 4:
                face = []
                for p in parts[1:]:
                    idx_str = p.split("/")[0]
                    try:
                        idx = int(idx_str)
                        if idx > 0:
                            face.append(idx - 1)
                        elif idx < 0:
                            face.append(len(raw_verts) + idx)
                    except ValueError:
                        continue
                if len(face) >= 3:
                    for k in range(1, len(face) - 1):
                        faces.append([face[0], face[k], face[k + 1]])

    return raw_verts, faces


def _classify_face_color(
    pts: List[Tuple[float, float, float]],
    bounds: Tuple[float, float, float, float, float, float],
) -> Tuple[int, int, int]:
    """To mau mat chim canh cut:
    - Chan & Mo: Cam ruc ro
    - Bung truoc: Trang tuyet
    - Ma: Trang nga
    - Than & Lung & Dau: Xanh den sam (Dark Navy)
    """
    min_r, max_r, min_c, max_c, min_z, max_z = bounds
    cz = sum(p[2] for p in pts) / len(pts)
    cr = sum(p[0] for p in pts) / len(pts)
    cc = sum(p[1] for p in pts) / len(pts)

    h_span = max(1e-5, max_z - min_z)
    norm_z = (cz - min_z) / h_span

    # Ban chan cam o day
    if norm_z < 0.08:
        return (245, 130, 25)

    # Mo cam nhon o dinh truoc
    if 0.80 <= norm_z <= 0.94 and cr > 0.28 and abs(cc) < 0.09:
        return (255, 145, 15)

    # Bung trang tuyet o mat truoc
    if 0.08 <= norm_z <= 0.78 and cr > 0.01 and abs(cc) < 0.22:
        return (248, 250, 255)

    # Ma trang
    if 0.78 < norm_z <= 0.91 and cr > 0.04 and 0.05 <= abs(cc) <= 0.18:
        return (235, 242, 250)

    # Than va lung den xanh
    return (22, 30, 46)


def normalize_obj_to_box(
    raw_verts: List[Tuple[float, float, float]],
    faces: List[List[int]],
    is_cube: bool = False,
) -> Tuple[List[Tuple[float, float, float]], List[List[int]], List[Tuple[int, int, int]]]:
    """Căn chỉnh mô hình .obj có TÂM TẠI (0, 0, 0) để có thể xoay tự do trong không gian."""
    if not raw_verts or not faces:
        return build_fallback_penguin(is_cube)

    xs = [v[0] for v in raw_verts]
    ys = [v[1] for v in raw_verts]
    zs = [v[2] for v in raw_verts]

    dx = max(xs) - min(xs)
    dy = max(ys) - min(ys)
    dz = max(zs) - min(zs)

    # Nhận diện trục đứng (chiều cao lớn nhất)
    if dy >= dx and dy >= dz:
        h_idx, r_idx, c_idx = 1, 2, 0
    elif dz >= dx and dz >= dy:
        h_idx, r_idx, c_idx = 2, 0, 1
    else:
        h_idx, r_idx, c_idx = 0, 1, 2

    h_min, h_max = min(v[h_idx] for v in raw_verts), max(v[h_idx] for v in raw_verts)
    r_min, r_max = min(v[r_idx] for v in raw_verts), max(v[r_idx] for v in raw_verts)
    c_min, c_max = min(v[c_idx] for v in raw_verts), max(v[c_idx] for v in raw_verts)

    h_span = max(1e-5, h_max - h_min)
    r_span = max(1e-5, r_max - r_min)
    c_span = max(1e-5, c_max - c_min)

    # Chiều dài thân chuẩn 1.70 (trong khối 2.0), ngang 0.70 (trong khối 1.0)
    avail_h = 0.85 if is_cube else 1.65
    avail_w = 0.45 if is_cube else 0.82

    scale_h = avail_h / h_span
    scale_w = avail_w / max(r_span, c_span)
    scale = min(scale_h, scale_w)

    h_mid = (h_min + h_max) / 2.0
    r_mid = (r_min + r_max) / 2.0
    c_mid = (c_min + c_max) / 2.0

    # Căn giữa tại (0, 0, 0)
    verts: List[Tuple[float, float, float]] = []
    for v in raw_verts:
        r = (v[r_idx] - r_mid) * scale
        c = (v[c_idx] - c_mid) * scale
        z = (v[h_idx] - h_mid) * scale
        verts.append((r, c, z))

    vr = [v[0] for v in verts]
    vc = [v[1] for v in verts]
    vz = [v[2] for v in verts]
    bounds = (min(vr), max(vr), min(vc), max(vc), min(vz), max(vz))

    colors: List[Tuple[int, int, int]] = []
    for f in faces:
        pts = [verts[i] for i in f]
        colors.append(_classify_face_color(pts, bounds))

    return verts, faces, colors


def build_fallback_penguin(
    is_cube: bool = False,
) -> Tuple[List[Tuple[float, float, float]], List[List[int]], List[Tuple[int, int, int]]]:
    """Tạo mô hình 3D low-poly chim cánh cụt hoàn chỉnh (thân, đầu tròn, mắt, má, mỏ 3D, cánh, chân).
    Căn giữa tại (0, 0, 0), xoay tự do theo Frame3D.
    - Chân cam vững chắc ở đáy.
    - Thân mập mạp với bụng trắng tuyết phía trước, lông xanh đen sẫm phía sau.
    - Cổ thon nhẹ kết nối thân và đầu mượt mà.
    - Đầu tròn đầy đặn (không bị cụt/mất đầu), má trắng.
    - Đôi mắt to tròn hoạt hình với con ngươi đen và đốm sáng long lanh.
    - Má hồng baby dễ thương.
    - Mỏ nhọn 3D màu cam chĩa về phía trước (+R), pháp tuyến chuẩn không bị culling.
    - Hai cánh 3D hai mặt hai bên sườn.
    """
    scale = 0.52 if is_cube else 1.0
    verts: List[Tuple[float, float, float]] = []
    faces: List[List[int]] = []
    colors: List[Tuple[int, int, int]] = []

    def add_box(r0, r1, c0, c1, z0, z1, col):
        idx = len(verts)
        box_pts = [
            (r0 * scale, c0 * scale, z0 * scale),
            (r0 * scale, c1 * scale, z0 * scale),
            (r1 * scale, c1 * scale, z0 * scale),
            (r1 * scale, c0 * scale, z0 * scale),
            (r0 * scale, c0 * scale, z1 * scale),
            (r0 * scale, c1 * scale, z1 * scale),
            (r1 * scale, c1 * scale, z1 * scale),
            (r1 * scale, c0 * scale, z1 * scale),
        ]
        verts.extend(box_pts)
        for f in [
            [idx, idx + 1, idx + 2, idx + 3],          # đáy (-Z)
            [idx + 4, idx + 7, idx + 6, idx + 5],      # đỉnh (+Z)
            [idx, idx + 4, idx + 5, idx + 1],          # mặt sau (-R)
            [idx + 1, idx + 5, idx + 6, idx + 2],      # mặt phải (+C)
            [idx + 2, idx + 6, idx + 7, idx + 3],      # mặt trước (+R)
            [idx + 3, idx + 7, idx + 4, idx],          # mặt trái (-C)
        ]:
            faces.append(f)
            colors.append(col)

    # 1. Bàn chân cam vững chãi ở đáy (z từ -0.86 đến -0.73)
    col_foot = (245, 125, 20)
    add_box(0.04, 0.36, -0.28, -0.06, -0.86, -0.73, col_foot)
    add_box(0.04, 0.36, 0.06, 0.28, -0.86, -0.73, col_foot)

    # 2. Thân & Đầu theo các tầng tròn (N = 10 cạnh quanh thân)
    N = 10
    tiers = [
        (-0.72, 0.23, 0.23),  # Đáy thân
        (-0.45, 0.34, 0.33),  # Bụng dưới mập
        (-0.12, 0.36, 0.34),  # Bụng ngực lớn nhất
        (+0.20, 0.30, 0.29),  # Ngực trên / vai
        (+0.42, 0.23, 0.23),  # Cổ thon nhẹ
        (+0.56, 0.27, 0.27),  # Cằm / má nở to
        (+0.70, 0.27, 0.27),  # Đầu ngang mắt mỏ
        (+0.82, 0.22, 0.22),  # Trán trên
        (+0.88, 0.13, 0.13),  # Đỉnh đầu vát tròn
    ]

    tier_start_indices = []
    for z_pos, rad_r, rad_c in tiers:
        tier_start_indices.append(len(verts))
        for i in range(N):
            ang = i * math.tau / N
            r = rad_r * math.cos(ang)
            c = rad_c * math.sin(ang)
            verts.append((r * scale, c * scale, z_pos * scale))

    col_white = (248, 250, 255)
    col_navy = (22, 28, 44)

    for layer in range(len(tiers) - 1):
        idx_a = tier_start_indices[layer]
        idx_b = tier_start_indices[layer + 1]
        for i in range(N):
            next_i = (i + 1) % N
            quad = [idx_a + i, idx_a + next_i, idx_b + next_i, idx_b + i]
            faces.append(quad)
            ang = (i + 0.5) * math.tau / N
            cos_a = math.cos(ang)

            if layer <= 3:
                # Thân & ngực: bụng trắng tuyết phía trước
                if cos_a > 0.05:
                    colors.append(col_white)
                else:
                    colors.append(col_navy)
            elif layer in (4, 5):
                # Vùng mặt / đầu: má trắng phía trước, mảng đầu và sau gáy màu đen
                if cos_a > 0.15:
                    colors.append(col_white)
                else:
                    colors.append(col_navy)
            else:
                # Đỉnh đầu & trán: màu đen
                colors.append(col_navy)

    # Đỉnh chóp đầu (hình chóp tròn mịn lên đỉnh apex)
    apex_idx = len(verts)
    verts.append((0.0, 0.0, 0.90 * scale))
    top_ring = tier_start_indices[-1]
    for i in range(N):
        next_i = (i + 1) % N
        faces.append([top_ring + i, top_ring + next_i, apex_idx])
        colors.append(col_navy)

    # Đáy thân phẳng
    bot_ring = tier_start_indices[0]
    bot_face = [bot_ring + i for i in reversed(range(N))]
    faces.append(bot_face)
    colors.append(col_navy)

    # 3. Đôi mắt to hoạt hình biểu cảm ở mặt trước
    col_pupil = (18, 20, 26)
    col_blush = (255, 155, 170)
    eye_z = 0.69 * scale
    eye_r = 0.278 * scale

    for sign in (-1, 1):
        eye_c = sign * 0.115 * scale

        # Tròng trắng mắt
        w_start = len(verts)
        eye_rad = 0.058 * scale
        for k in range(6):
            ang = k * math.tau / 6
            c_off = eye_rad * math.sin(ang)
            z_off = eye_rad * math.cos(ang)
            verts.append((eye_r, eye_c + c_off, eye_z + z_off))
        faces.append([w_start + k for k in reversed(range(6))])
        colors.append((255, 255, 255))

        # Con ngươi đen
        p_start = len(verts)
        p_r = 0.282 * scale
        p_rad = 0.035 * scale
        for k in range(5):
            ang = k * math.tau / 5
            c_off = p_rad * math.sin(ang)
            z_off = p_rad * math.cos(ang)
            verts.append((p_r, eye_c + (sign * 0.008 * scale) + c_off, eye_z + z_off))
        faces.append([p_start + k for k in reversed(range(5))])
        colors.append(col_pupil)

        # Chấm sáng long lanh trong mắt
        glint_start = len(verts)
        g_r = 0.284 * scale
        g_rad = 0.012 * scale
        for k in range(4):
            ang = k * math.tau / 4
            c_off = g_rad * math.sin(ang)
            z_off = g_rad * math.cos(ang)
            verts.append((g_r, eye_c + 0.012 * scale + c_off, eye_z + 0.016 * scale + z_off))
        faces.append([glint_start + k for k in reversed(range(4))])
        colors.append((255, 255, 255))

        # Má hồng dễ thương
        blush_start = len(verts)
        bl_r = 0.275 * scale
        bl_c = sign * 0.165 * scale
        bl_z = 0.58 * scale
        for k in range(4):
            ang = k * math.tau / 4
            c_off = 0.035 * scale * math.sin(ang)
            z_off = 0.022 * scale * math.cos(ang)
            verts.append((bl_r, bl_c + c_off, bl_z + z_off))
        faces.append([blush_start + k for k in reversed(range(4))])
        colors.append(col_blush)

    # 4. Mỏ cam 3D hoàn chỉnh hình kim tự tháp 4 mặt
    beak_start = len(verts)
    col_beak_top = (255, 140, 0)
    col_beak_bot = (235, 110, 0)
    # 4 đỉnh đế mỏ gắn trên mặt
    b_base_top = (0.280 * scale, 0.0, 0.68 * scale)
    b_base_left = (0.276 * scale, -0.065 * scale, 0.61 * scale)
    b_base_right = (0.276 * scale, 0.065 * scale, 0.61 * scale)
    b_base_bot = (0.280 * scale, 0.0, 0.54 * scale)
    # Đỉnh nhọn chĩa ra trước
    b_tip = (0.46 * scale, 0.0, 0.60 * scale)
    verts.extend([b_base_top, b_base_left, b_base_right, b_base_bot, b_tip])

    # 4 mặt mỏ (thứ tự đỉnh xoay ngược chiều kim đồng hồ nhìn từ ngoài vào để pháp tuyến hướng ra ngoài)
    faces.append([beak_start, beak_start + 4, beak_start + 2])  # trên phải
    colors.append(col_beak_top)
    faces.append([beak_start, beak_start + 1, beak_start + 4])  # trên trái
    colors.append(col_beak_top)
    faces.append([beak_start + 3, beak_start + 2, beak_start + 4])  # dưới phải
    colors.append(col_beak_bot)
    faces.append([beak_start + 3, beak_start + 4, beak_start + 1])  # dưới trái
    colors.append(col_beak_bot)

    # 5. Hai cánh 3D (dày, 2 mặt để nhìn từ góc nào cũng không bị culling)
    for sign in (-1, 1):
        w_start = len(verts)
        p_sh_top = (0.05 * scale, sign * 0.30 * scale, 0.28 * scale)
        p_sh_back = (-0.12 * scale, sign * 0.27 * scale, 0.24 * scale)
        p_tip = (-0.04 * scale, sign * 0.36 * scale, -0.28 * scale)
        p_mid = (0.08 * scale, sign * 0.33 * scale, -0.05 * scale)
        verts.extend([p_sh_top, p_sh_back, p_tip, p_mid])
        if sign == 1:
            faces.append([w_start, w_start + 3, w_start + 2, w_start + 1])
            colors.append(col_navy)
            faces.append([w_start, w_start + 1, w_start + 2, w_start + 3])
            colors.append((238, 242, 248))
        else:
            faces.append([w_start, w_start + 1, w_start + 2, w_start + 3])
            colors.append(col_navy)
            faces.append([w_start, w_start + 3, w_start + 2, w_start + 1])
            colors.append((238, 242, 248))

    return verts, faces, colors


_CACHE: Dict[Tuple[str, bool], Tuple[List, List, List]] = {}


def get_penguin_mesh(
    is_cube: bool = False,
) -> Tuple[List[Tuple[float, float, float]], List[List[int]], List[Tuple[int, int, int]]]:
    """Trả về mô hình 3D low-poly chim cánh cụt siêu nhẹ, mượt mà 0% giật lag."""
    cache_key = ("lowpoly_penguin", is_cube)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    mesh = build_fallback_penguin(is_cube)
    _CACHE[cache_key] = mesh
    return mesh


def build_cactus_mesh(
    is_cube: bool = False,
) -> Tuple[List[Tuple[float, float, float]], List[List[int]], List[Tuple[int, int, int]]]:
    """Mô hình 3D cây xương rồng low-poly cho Desert Theme.
    Căn giữa tại (0, 0, 0), xoay tự do theo Frame3D.
    - Cây xương rồng hình trụ lăng trụ 10 cạnh có vát đầu & đáy.
    - Bông hoa 5 cánh màu hồng rực rỡ kèm nhụy vàng ở đỉnh.
    - Khuôn mặt biểu cảm: mắt to hoạt hình, con ngươi đen, má hồng, miệng chữ O ngạc nhiên.
    - Gai xương rồng hình chữ V trắng dọc theo các đường gờ.
    """
    scale = 0.55 if is_cube else 1.0
    verts: List[Tuple[float, float, float]] = []
    faces: List[List[int]] = []
    colors: List[Tuple[int, int, int]] = []

    N = 10  # 10 cạnh quanh thân trụ

    # 1. Các tầng độ cao thân xương rồng (z, bán kính)
    # Phần chân thu nhỏ vát thon rõ rệt để dễ phân biệt đỉnh đầu (nở tròn + gắn hoa) và chân
    tiers = [
        (-0.84, 0.16),  # chân đáy nhỏ vát gọn
        (-0.65, 0.24),  # chân nở dần lên
        (-0.15, 0.34),  # thân dưới
        (+0.35, 0.40),  # thân trên tròn đầy
        (+0.72, 0.39),  # vai đầu tròn nở
        (+0.82, 0.24),  # vát đỉnh nơi gắn hoa
    ]

    tier_start_indices = []
    for z_pos, rad in tiers:
        tier_start_indices.append(len(verts))
        for i in range(N):
            ang = i * math.tau / N
            r = rad * math.cos(ang)
            c = rad * math.sin(ang)
            verts.append((r * scale, c * scale, z_pos * scale))

    col_green_base = (76, 175, 70)
    col_green_ridge = (64, 158, 58)
    col_green_light = (86, 192, 80)

    for layer in range(len(tiers) - 1):
        idx_a = tier_start_indices[layer]
        idx_b = tier_start_indices[layer + 1]
        for i in range(N):
            next_i = (i + 1) % N
            quad = [idx_a + i, idx_a + next_i, idx_b + next_i, idx_b + i]
            faces.append(quad)
            if i % 2 == 0:
                col = col_green_light if layer >= 3 else col_green_base
            else:
                col = col_green_ridge
            colors.append(col)

    # Đáy dưới cùng
    idx_bot = tier_start_indices[0]
    bot_face = [idx_bot + i for i in reversed(range(N))]
    faces.append(bot_face)
    colors.append((45, 120, 42))

    # Đỉnh trên cùng (nắp vát phẳng)
    idx_top = tier_start_indices[-1]
    top_face = [idx_top + i for i in range(N)]
    faces.append(top_face)
    colors.append((90, 195, 84))

    # 2. Bông hoa màu hồng 5 cánh ở đỉnh (z = +0.81 đến +0.86)
    flower_z = 0.82
    flower_rad = 0.22
    pistil_rad = 0.08
    center_idx = len(verts)
    verts.append((0.0, 0.0, (flower_z + 0.03) * scale))  # đỉnh nhụy

    petals = 5
    for p in range(petals):
        ang_mid = p * math.tau / petals
        ang_left = ang_mid - 0.35
        ang_right = ang_mid + 0.35

        v_mid = (flower_rad * math.cos(ang_mid) * scale, flower_rad * math.sin(ang_mid) * scale, (flower_z + 0.02) * scale)
        v_left = (pistil_rad * 1.5 * math.cos(ang_left) * scale, pistil_rad * 1.5 * math.sin(ang_left) * scale, flower_z * scale)
        v_right = (pistil_rad * 1.5 * math.cos(ang_right) * scale, pistil_rad * 1.5 * math.sin(ang_right) * scale, flower_z * scale)

        pi0 = len(verts)
        verts.extend([v_mid, v_left, v_right])
        faces.append([pi0 + 1, pi0, pi0 + 2])
        colors.append((245, 82, 130))  # Cánh hoa hồng tươi

    # Nhụy vàng ở trung tâm bông hoa
    pistil_idx = len(verts)
    p_pts = []
    for p in range(6):
        ang = p * math.tau / 6
        verts.append((pistil_rad * math.cos(ang) * scale, pistil_rad * math.sin(ang) * scale, (flower_z + 0.04) * scale))
        p_pts.append(pistil_idx + p)
    faces.append(p_pts)
    colors.append((255, 215, 55))  # Nhụy vàng óng

    # 3. Khuôn mặt biểu cảm ở mặt trước (+R):
    for sign in (-1, 1):
        eye_c = sign * 0.12 * scale
        eye_r = 0.405 * scale
        eye_z = 0.40 * scale
        eye_rad = 0.075 * scale

        # Tròng trắng
        w_start = len(verts)
        for k in range(6):
            ang = k * math.tau / 6
            c_off = eye_rad * math.sin(ang)
            z_off = eye_rad * math.cos(ang)
            verts.append((eye_r, eye_c + c_off, eye_z + z_off))
        faces.append([w_start + k for k in reversed(range(6))])
        colors.append((252, 252, 255))

        # Con ngươi đen
        pupil_start = len(verts)
        pupil_r = 0.410 * scale
        pupil_c = eye_c + (sign * 0.02) * scale
        pupil_z = eye_z + 0.01 * scale
        pupil_rad = 0.042 * scale
        for k in range(5):
            ang = k * math.tau / 5
            c_off = pupil_rad * math.sin(ang)
            z_off = pupil_rad * math.cos(ang)
            verts.append((pupil_r, pupil_c + c_off, pupil_z + z_off))
        faces.append([pupil_start + k for k in reversed(range(5))])
        colors.append((22, 25, 30))

        # Má hồng
        blush_start = len(verts)
        blush_r = 0.40 * scale
        blush_c = sign * 0.18 * scale
        blush_z = 0.24 * scale
        for k in range(4):
            ang = k * math.tau / 4
            c_off = 0.045 * math.sin(ang) * scale
            z_off = 0.025 * math.cos(ang) * scale
            verts.append((blush_r, blush_c + c_off, blush_z + z_off))
        faces.append([blush_start + k for k in reversed(range(4))])
        colors.append((255, 145, 168))

        # Lông mày xanh sẫm
        brow_start = len(verts)
        br_r = 0.405 * scale
        br_c = sign * 0.12 * scale
        br_z = 0.51 * scale
        tilt = sign * 0.015 * scale
        verts.append((br_r, br_c - 0.04 * scale, br_z - tilt))
        verts.append((br_r, br_c + 0.04 * scale, br_z + tilt))
        verts.append((br_r, br_c + 0.03 * scale, br_z + 0.025 * scale + tilt))
        verts.append((br_r, br_c - 0.03 * scale, br_z + 0.025 * scale - tilt))
        faces.append([brow_start, brow_start + 1, brow_start + 2, brow_start + 3])
        colors.append((38, 105, 34))

    # Miệng chữ O ngạc nhiên dễ thương ở giữa (r ~ +0.40, c ~ 0, z ~ 0.18)
    mouth_start = len(verts)
    m_r = 0.408 * scale
    m_z = 0.18 * scale
    for k in range(6):
        ang = k * math.tau / 6
        c_off = 0.05 * math.sin(ang) * scale
        z_off = 0.07 * math.cos(ang) * scale
        verts.append((m_r, c_off, m_z + z_off))
    faces.append([mouth_start + k for k in reversed(range(6))])
    colors.append((150, 32, 45))  # Đỏ rượu sâu

    # 4. Gai xương rồng chữ V trắng (kim xương rồng) trên các sườn
    spine_locs = [
        (0.0, -0.45),
        (0.0, 0.58),
        (math.pi * 0.25, -0.15),
        (-math.pi * 0.25, -0.15),
        (math.pi * 0.5, 0.25),
        (-math.pi * 0.5, 0.25),
        (math.pi * 0.75, 0.10),
        (-math.pi * 0.75, 0.10),
        (math.pi, 0.35),
        (math.pi, -0.35),
    ]
    for ang, sz in spine_locs:
        rad = 0.402 if sz >= 0 else 0.34
        rad *= 1.01
        ct, st = math.cos(ang), math.sin(ang)
        t_r, t_c = -st, ct
        c_r, c_c = ct * rad, st * rad
        sp_start = len(verts)
        p0 = ((c_r - 0.035 * t_r) * scale, (c_c - 0.035 * t_c) * scale, (sz + 0.03) * scale)
        p1 = (c_r * scale, c_c * scale, (sz - 0.03) * scale)
        p2 = ((c_r + 0.035 * t_r) * scale, (c_c + 0.035 * t_c) * scale, (sz + 0.03) * scale)
        verts.extend([p0, p1, p2])
        faces.append([sp_start, sp_start + 1, sp_start + 2])
        colors.append((250, 252, 242))

    return verts, faces, colors


def get_cactus_mesh(
    is_cube: bool = False,
) -> Tuple[List[Tuple[float, float, float]], List[List[int]], List[Tuple[int, int, int]]]:
    """Trả về mô hình 3D low-poly cây xương rồng cho Desert Theme."""
    cache_key = ("lowpoly_cactus", is_cube)
    if cache_key in _CACHE:
        return _CACHE[cache_key]
    mesh = build_cactus_mesh(is_cube)
    _CACHE[cache_key] = mesh
    return mesh
