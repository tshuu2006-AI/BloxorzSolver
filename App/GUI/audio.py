"""Phát hiệu ứng âm thanh tổng hợp qua pygame.mixer; mọi lỗi thiết bị âm thanh chỉ làm game im lặng."""

from __future__ import annotations

from array import array
from typing import Dict, Optional

import pygame

from App.Game import synth


class Audio:
    def __init__(self, enabled: bool = True, volume: float = 0.6):
        self.enabled = enabled
        self.volume = volume
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self.ok = False
        self._rate, self._channels = 22050, 1
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 512)
            init = pygame.mixer.get_init()
            if init:
                self._rate, _fmt, self._channels = init
                self.ok = True
        except pygame.error:
            self.ok = False

    def _sound(self, name: str) -> Optional[pygame.mixer.Sound]:
        snd = self.sounds.get(name)
        if snd is None:
            mono = synth.render(name, self._rate)
            if self._channels > 1:  # lặp mẫu cho mỗi kênh
                data = array("h")
                for v in mono:
                    data.extend([v] * self._channels)
            else:
                data = mono
            try:
                snd = pygame.mixer.Sound(buffer=data.tobytes())
            except pygame.error:
                return None
            snd.set_volume(self.volume)
            self.sounds[name] = snd
        return snd

    def play(self, name: str) -> None:
        if not (self.ok and self.enabled):
            return
        snd = self._sound(name)
        if snd is not None:
            snd.play()

    def set_enabled(self, value: bool) -> None:
        self.enabled = value
        if not value and self.ok:
            pygame.mixer.stop()

    def set_volume(self, value: float) -> None:
        self.volume = max(0.0, min(1.0, value))
        for snd in self.sounds.values():
            snd.set_volume(self.volume)
