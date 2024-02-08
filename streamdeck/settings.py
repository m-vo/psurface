"""
 This file is part of the pSurface project. For the full copyright and license
 information, see the LICENSE file that was distributed with this source code.
"""
from common.event import Event


class GlobalSettings:
    def __init__(self):
        self._brightness: int = 0  # 0-4
        self._direct_action: bool = False
        self._output_filter: bool = False
        self._status: str = ""

        self.brightness_changed_event = Event()
        self.status_changed_event = Event()
        self.direct_action_changed_event = Event()
        self.filter_changed_event = Event()

    @property
    def brightness(self) -> int:
        return self._brightness

    def set_default_brightness(self) -> None:
        self._brightness = 4
        self.brightness_changed_event()

    def increase_brightness(self) -> None:
        self._brightness = (self._brightness + 1) % 5
        self.brightness_changed_event()

    @property
    def direct_action(self) -> bool:
        return self._direct_action

    def toggle_direct_action(self) -> None:
        self._direct_action = not self._direct_action
        self.direct_action_changed_event()

    @property
    def output_filter(self) -> bool:
        return self._output_filter

    def toggle_output_filter(self) -> None:
        self._output_filter = not self._output_filter
        self.filter_changed_event()

    def disable_output_filter(self) -> None:
        if self._output_filter:
            self._output_filter = False
            self.filter_changed_event()
