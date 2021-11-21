from common.event import Event


class GlobalSettings:
    def __init__(self):
        self._brightness: int = 0  # 0-4
        self._direct_action: bool = False
        self._status: str = ""

        self.brightness_changed_event = Event()
        self.status_changed_event = Event()

    @property
    def brightness(self) -> int:
        return self._brightness

    def set_default_brightness(self) -> None:
        self._brightness = 2
        self.brightness_changed_event()

    def increase_brightness(self) -> None:
        self._brightness = (self._brightness + 1) % 5
        self.brightness_changed_event()

    @property
    def direct_action(self) -> bool:
        return self._direct_action

    def toggle_direct_action(self) -> None:
        self._direct_action = not self._direct_action

    def disable_direct_action(self) -> None:
        self._direct_action = False

    @property
    def status(self) -> str:
        return self._status

    def set_status(self, status: str):
        self._status = status
        self.status_changed_event()