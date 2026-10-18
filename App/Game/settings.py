"""Cài đặt của người chơi (bật/tắt gợi ý, heuristic của A*, tốc độ replay...), lưu ra file JSON nhỏ.

Giống ``Progress``: file thiếu hoặc hỏng thì dùng mặc định, giá trị sai kiểu bị bỏ qua.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

DEFAULTS: Dict[str, Any] = {
    "show_compass": True,       # thẻ "Move keys" ở góc dưới trái
    "show_camera_help": True,   # thẻ "Camera" hướng dẫn xoay/zoom
    "show_floor_arrows": True,  # mũi tên vàng trên sàn quanh khối đang điều khiển
    "show_link_lines": False,   # đường nét đứt nối công tắc với cầu nó điều khiển
    "show_path": True,          # lớp phủ đường đi của lời giải
    "show_tips": True,          # gợi ý hướng dẫn lần đầu gặp mỗi cơ chế
    "astar_heuristic": "relaxed",
    "replay_speed": 1.5,
    "tilt_deg": 15.0,           # độ nghiêng ngược chiều kim đồng hồ của trục cột (góc nhìn mặc định)
    "sound_on": True,           # hiệu ứng âm thanh (phím M để tắt/bật)
    "volume": 0.6,
    "tips_seen": [],
}

_NUMERIC_RANGE = {"replay_speed": (0.5, 4.0), "tilt_deg": (0.0, 45.0), "volume": (0.0, 1.0)}


def _clean(key: str, value: Any):
    """Trả về giá trị hợp lệ cho ``key`` hoặc ``None`` nếu không dùng được."""
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return value if isinstance(value, bool) else None
    if isinstance(default, float):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        lo, hi = _NUMERIC_RANGE[key]
        return float(min(hi, max(lo, value)))
    if isinstance(default, str):
        return value if isinstance(value, str) and value else None
    if isinstance(default, list):
        return [v for v in value if isinstance(v, str)] if isinstance(value, list) else None
    return None


class Settings:
    def __init__(self, path):
        self.path = Path(path)
        self._v: Dict[str, Any] = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        for key in DEFAULTS:
            if key in raw:
                value = _clean(key, raw[key])
                if value is not None:
                    self._v[key] = value

    def save(self) -> None:
        try:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps(self._v, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass  # không ghi được thì thôi, cài đặt chỉ mất khi thoát

    # ------------------------------------------------------------------ truy cập
    def __getattr__(self, name: str):
        # chỉ gọi khi thuộc tính thường không tồn tại
        if name in DEFAULTS:
            return self._v[name]
        raise AttributeError(name)

    def set(self, key: str, value: Any) -> None:
        if key not in DEFAULTS:
            raise KeyError(key)
        cleaned = _clean(key, value)
        if cleaned is None:
            raise ValueError(f"giá trị không hợp lệ cho {key}: {value!r}")
        if self._v[key] != cleaned:
            self._v[key] = cleaned
            self.save()

    def mark_tip_seen(self, tip: str) -> None:
        if tip not in self._v["tips_seen"]:
            self._v["tips_seen"] = [*self._v["tips_seen"], tip]
            self.save()

    def reset_tips(self) -> None:
        self._v["tips_seen"] = []
        self.save()
