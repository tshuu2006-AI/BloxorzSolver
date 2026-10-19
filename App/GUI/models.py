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
    Path("Penguin.obj"),
    Path("assets/Penguin.obj"),
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

    def _rot(v: Vector3) -> Vector3:
        r, c, z = v
        if action == "D":
            return (z, c, -r)
        elif action == "U":
            return (-z, c, r)
        elif action == "R":
            return (r, z, -c)
        elif action == "L":
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
    """Tô màu mặt chim cánh cụt dựa trên hình học:

    - Chân & Mỏ: Cam rực rỡ
    - Bụng trước: Trắng tuyết
    - Thân & Lưng & Đầu: Xanh đen sẫm (Dark Navy)
    """
    min_r, max_r, min_c, max_c, min_z, max_z = bounds
    cz = sum(p[2] for p in pts) / len(pts)
    cr = sum(p[0] for p in pts) / len(pts)
    cc = sum(p[1] for p in pts) / len(pts)

    h_span = max(1e-5, max_z - min_z)
    r_span = max(1e-5, max_r - min_r)
    c_span = max(1e-5, max_c - min_c)

    norm_z = (cz - min_z) / h_span
    norm_r = cr / (r_span * 0.5) if r_span else 0.0
    norm_c = cc / (c_span * 0.5) if c_span else 0.0

    # Chân cam ở đáy
    if norm_z < 0.12:
        return (245, 130, 25)

    # Mỏ cam ở trên cao phía trước
    if 0.70 <= norm_z <= 0.88 and norm_r > 0.35 and abs(norm_c) < 0.30:
        return (255, 145, 15)

    # Bụng trắng tuyết ở mặt trước
    if 0.12 <= norm_z <= 0.75 and norm_r > 0.05 and abs(norm_c) < 0.55:
        return (246, 248, 252)

    # Má trắng
    if 0.75 < norm_z <= 0.88 and norm_r > 0.20 and 0.25 <= abs(norm_c) <= 0.60:
        return (235, 240, 245)

    # Thân và lưng đen xanh
    return (28, 36, 52)


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
    avail_h = 0.85 if is_cube else 1.70
    avail_w = 0.40 if is_cube else 0.70

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
    """Tạo mô hình 3D low-poly chim cánh cụt tích hợp sẵn, CĂN GIỮA TẠI (0, 0, 0)."""
    scale = 0.5 if is_cube else 1.0
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
            [idx, idx + 1, idx + 2, idx + 3],
            [idx + 4, idx + 7, idx + 6, idx + 5],
            [idx, idx + 4, idx + 5, idx + 1],
            [idx + 1, idx + 5, idx + 6, idx + 2],
            [idx + 2, idx + 6, idx + 7, idx + 3],
            [idx + 3, idx + 7, idx + 4, idx],
        ]:
            faces.append(f)
            colors.append(col)

    # 1. Bàn chân cam ở đáy (z từ -0.85 đến -0.73)
    add_box(0.05, 0.32, -0.28, -0.06, -0.85, -0.73, (245, 130, 20))
    add_box(0.05, 0.32, 0.06, 0.28, -0.85, -0.73, (245, 130, 20))

    # 2. Thân chim (các tầng elip từ z = -0.70 đến z = +0.80)
    n = 8
    rings = [
        (-0.70, 0.22, 0.22),  # đáy thân
        (-0.35, 0.34, 0.32),  # bụng dưới
        (+0.10, 0.35, 0.31),  # ngực
        (+0.48, 0.25, 0.23),  # cổ
        (+0.80, 0.18, 0.18),  # đỉnh đầu
    ]

    ring_start_indices = []
    for z_pos, rad_r, rad_c in rings:
        ring_start_indices.append(len(verts))
        for i in range(n):
            ang = i * math.tau / n
            r = rad_r * math.cos(ang)
            c = rad_c * math.sin(ang)
            verts.append((r * scale, c * scale, z_pos * scale))

    for layer in range(len(rings) - 1):
        idx_a = ring_start_indices[layer]
        idx_b = ring_start_indices[layer + 1]
        for i in range(n):
            next_i = (i + 1) % n
            quad = [idx_a + i, idx_a + next_i, idx_b + next_i, idx_b + i]
            faces.append(quad)
            ang = i * math.tau / n
            is_front = math.cos(ang) > 0.1
            if is_front and layer in (0, 1, 2):
                colors.append((248, 250, 254))  # bụng trắng
            else:
                colors.append((26, 34, 50))  # lưng đen xanh

    head_top = ring_start_indices[-1]
    faces.append([head_top + i for i in reversed(range(n))])
    colors.append((26, 34, 50))

    # 3. Mỏ cam
    beak_tip = len(verts)
    verts.append((0.44 * scale, 0.0, 0.55 * scale))
    idx_head = ring_start_indices[3]
    faces.append([idx_head, idx_head + 1, beak_tip])
    colors.append((255, 145, 15))
    faces.append([idx_head, beak_tip, idx_head + n - 1])
    colors.append((255, 145, 15))

    # 4. Hai cánh
    for sign in (-1, 1):
        w_idx = len(verts)
        verts.append((0.0, sign * 0.33 * scale, 0.35 * scale))
        verts.append((0.0, sign * 0.38 * scale, -0.25 * scale))
        verts.append((-0.18 * scale, sign * 0.32 * scale, 0.05 * scale))
        faces.append([w_idx, w_idx + 1, w_idx + 2])
        colors.append((22, 28, 42))

    return verts, faces, colors


_CACHE: Dict[Tuple[str, bool], Tuple[List, List, List]] = {}


def get_penguin_mesh(
    is_cube: bool = False,
) -> Tuple[List[Tuple[float, float, float]], List[List[int]], List[Tuple[int, int, int]]]:
    """Trả về mô hình 3D chim cánh cụt căn giữa tại (0,0,0) (tự động nạp file .obj nếu có)."""
    obj_file = _find_penguin_file()
    cache_key = (str(obj_file) if obj_file else "builtin", is_cube)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    if obj_file is not None:
        try:
            raw_v, raw_f = parse_obj(obj_file)
            if raw_v and raw_f:
                mesh = normalize_obj_to_box(raw_v, raw_f, is_cube)
                _CACHE[cache_key] = mesh
                return mesh
        except Exception as exc:
            print(f"[PenguinLoader] Lỗi nạp {obj_file}: {exc}")

    mesh = build_fallback_penguin(is_cube)
    _CACHE[cache_key] = mesh
    return mesh
