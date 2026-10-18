"""Tiến độ chơi: màn nào đã qua và số nước ít nhất, lưu ra một file JSON nhỏ.

File là tuỳ chọn: thiếu hoặc hỏng thì game vẫn chạy bình thường (tiến độ rỗng).
Khoá là tên màn (ổn định khi đổi số thứ tự file).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional


class Progress:
    def __init__(self, path):
        self.path = Path(path)
        self._best: Dict[str, int] = {}
        self._load()

    def _load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            best = raw.get("best", {}) if isinstance(raw, dict) else {}
            self._best = {
                str(k): int(v) for k, v in best.items() if isinstance(v, int) and v >= 0
            }
        except (OSError, ValueError, AttributeError):
            self._best = {}

    def _save(self) -> None:
        try:
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps({"best": self._best}, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            pass  # không ghi được (thư mục chỉ đọc...) cũng không sao

    def best(self, name: str) -> Optional[int]:
        return self._best.get(name)

    def is_cleared(self, name: str) -> bool:
        return name in self._best

    def record_win(self, name: str, moves: int) -> bool:
        """Ghi lại một lần thắng. Trả về True nếu đây là kỷ lục mới (hoặc lần đầu)."""
        old = self._best.get(name)
        if old is not None and old <= moves:
            return False
        self._best[name] = moves
        self._save()
        return True
