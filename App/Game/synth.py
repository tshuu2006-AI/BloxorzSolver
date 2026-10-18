"""Hiệu ứng âm thanh tổng hợp bằng code (không cần file âm thanh), thuần Python nên test được.

``render(name, rate)`` trả về mảng mẫu 16-bit mono. ``App/GUI/audio.py`` đưa chúng vào pygame.mixer.
"""

from __future__ import annotations

import math
import random
from array import array
from typing import Callable, Dict, List, Sequence, Tuple

PEAK = 0.8 * 32767


def _env(n: int, i: int, attack: float = 0.004, decay: float = 5.0, rate: int = 22050) -> float:
    a = min(1.0, i / max(1, attack * rate))
    return a * math.exp(-decay * i / max(1, n))


def _sweep(dur, f0, f1, rate, decay=4.0, wave="sine", noise=0.0, seed=1):
    """Âm quét tần số f0 -> f1 trong ``dur`` giây, tắt dần theo hàm mũ."""
    rng = random.Random(seed)
    n = int(dur * rate)
    out, phase = [], 0.0
    for i in range(n):
        f = f0 + (f1 - f0) * (i / n)
        phase += math.tau * f / rate
        s = math.sin(phase)
        if wave == "square":
            s = 1.0 if s >= 0 else -1.0
        elif wave == "soft":
            s = s + 0.35 * math.sin(2 * phase) + 0.15 * math.sin(3 * phase)
        if noise:
            s = s * (1 - noise) + rng.uniform(-1, 1) * noise
        out.append(s * _env(n, i, decay=decay, rate=rate))
    return out


def _seq(parts: Sequence[Tuple[float, List[float]]], rate: int) -> List[float]:
    """Ghép các đoạn âm, mỗi đoạn bắt đầu sau ``offset`` giây (cộng chồng nếu chồng thời gian)."""
    total = max(int(off * rate) + len(p) for off, p in parts)
    out = [0.0] * total
    for off, p in parts:
        base = int(off * rate)
        for i, v in enumerate(p):
            out[base + i] += v
    return out


def _roll(rate):  # tiếng "thịch" khi khối chạm sàn
    return _sweep(0.13, 150, 55, rate, decay=6.0, wave="soft", noise=0.12)


def _blocked(rate):
    return _sweep(0.14, 95, 80, rate, decay=3.0, wave="square")


def _swap(rate):
    return _seq([(0.0, _sweep(0.06, 660, 700, rate, 3.0)), (0.06, _sweep(0.09, 880, 900, rate, 4.0))], rate)


def _switch(rate):  # tách tách
    return _seq([(0.0, _sweep(0.05, 1500, 1200, rate, 6.0, "soft")), (0.045, _sweep(0.07, 2100, 1800, rate, 6.0))], rate)


def _bridge_open(rate):
    return _sweep(0.28, 320, 760, rate, decay=3.0, wave="soft")


def _bridge_close(rate):
    return _sweep(0.28, 700, 260, rate, decay=3.0, wave="soft")


def _split(rate):  # vút
    return _sweep(0.32, 400, 1500, rate, decay=3.5, wave="soft", noise=0.25)


def _merge(rate):
    return _seq([(0.0, _sweep(0.08, 900, 900, rate, 4.0)), (0.07, _sweep(0.1, 600, 600, rate, 4.0))], rate)


def _fall(rate):  # tiếng huýt rơi
    return _sweep(0.6, 900, 110, rate, decay=3.0, wave="soft")


def _win(rate):  # hợp âm rải C-E-G-C
    notes = (523.25, 659.25, 783.99, 1046.5)
    parts = [(0.09 * k, _sweep(0.45 if k == 3 else 0.3, f, f, rate, decay=3.5, wave="soft")) for k, f in enumerate(notes)]
    return _seq(parts, rate)


def _best(rate):  # kỷ lục mới
    return _seq([(0.0, _sweep(0.12, 1046.5, 1046.5, rate, 4.0)), (0.1, _sweep(0.3, 1568.0, 1568.0, rate, 3.0, "soft"))], rate)


SOUNDS: Dict[str, Callable[[int], List[float]]] = {
    "roll": _roll, "blocked": _blocked, "swap": _swap, "switch": _switch,
    "bridge_open": _bridge_open, "bridge_close": _bridge_close, "split": _split,
    "merge": _merge, "fall": _fall, "win": _win, "best": _best,
}


def render(name: str, rate: int = 22050) -> array:
    """Mẫu 16-bit mono của âm ``name`` (chuẩn hoá để đỉnh khoảng 80% biên độ)."""
    samples = SOUNDS[name](rate)
    peak = max((abs(v) for v in samples), default=0.0) or 1.0
    scale = PEAK / max(peak, 1.0)
    return array("h", (int(max(-32767, min(32767, v * scale))) for v in samples))
