from typing import Dict, List

from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.Devices import StreamDeck
from StreamDeck.Devices.StreamDeckXL import StreamDeckXL

from app import App
from dlive.api import DLive
from dlive.virtual import LayerController
from streamdeck.surface.input import InputSurface
from streamdeck.surface.output import OutputSurface
from streamdeck.surface.surface import Surface
from streamdeck.surface.system import SystemSurface


class UI:
    BRIGHTNESS_MIN = 0
    BRIGHTNESS_LOW = 1
    BRIGHTNESS_MED = 2
    BRIGHTNESS_HIGH = 3
    BRIGHTNESS_MAX = 4

    def __init__(self) -> None:
        devices_config = App.config.streamdeck_devices
        self._devices: Dict[str, StreamDeck] = {}
        self._surfaces: List[Surface] = []

        self._device_mapping = {
            devices_config["system"]: ["system", 15],
            devices_config["input"]: ["input", 32],
            devices_config["output"]: ["output", 32],
        }

        self._brightness = self.BRIGHTNESS_MAX
        self.shift = False

    def find_devices(self) -> bool:
        all_decks = list(map(lambda v: v[0], self._device_mapping.values()))

        for device in DeviceManager().enumerate():
            device.open()

            if (serial := device.get_serial_number()) not in self._device_mapping:
                print(f"\n[ERR] Found a deck with an unknown serial '{serial}'.")
                device.close()
                continue

            name, min_key_count = self._device_mapping[serial]
            if device.key_count() < min_key_count:
                print(f"\n[ERR] Deck matching the serial of '{name}' must have at least {min_key_count} keys.")
                device.close()
                continue

            self._devices[name] = device
            all_decks.remove(name)

        if len(all_decks) > 0:
            print(f"\n[ERR] Missing deck(s): {', '.join(all_decks)}")
            return False

        return True

    def initialize_ui(self, dlive: DLive, layer_controller: LayerController) -> None:
        self._surfaces.clear()

        if (input_deck := self._devices.get("input", None)) is not None:
            self._surfaces.append(InputSurface(input_deck, dlive, layer_controller))

        if (output_deck := self._devices.get("output", None)) is not None:
            self._surfaces.append(OutputSurface(output_deck, dlive, layer_controller))

        if (system_deck := self._devices.get("system", None)) is not None:
            system_surface = SystemSurface(
                system_deck,
                dlive,
                layer_controller,
                {
                    "brightness": lambda: self.brightness,
                    "toggle_brightness": lambda: self.toggle_brightness(),
                    "direct_action": lambda: self.shift_down,
                    "enable_shift": lambda: self.enable_shift(),
                    "disable_shift": lambda: self.disable_shift(),
                },
            )

            self._surfaces.append(system_surface)

        self._set_direct_action()
        self._set_brightness()

    @property
    def brightness(self) -> int:
        return self._brightness

    @property
    def shift_down(self) -> bool:
        return self.shift

    def toggle_brightness(self) -> None:
        self._brightness = (self._brightness + 1) % (self.BRIGHTNESS_MAX + 1)
        self._set_brightness()

    def _set_brightness(self) -> None:
        streamdeck_original_map = {0: 20, 1: 29, 2: 43, 3: 50, 4: 60}
        streamdeck_xl_map = {0: 18, 1: 28, 2: 43, 3: 65, 4: 100}

        for device in self._devices.values():
            value_mapping = (streamdeck_original_map, streamdeck_xl_map)[isinstance(device, StreamDeckXL)]
            device.set_brightness(value_mapping[self._brightness])

    def enable_shift(self) -> None:
        self.shift = True
        self._set_direct_action()

    def disable_shift(self) -> None:
        self.shift = False
        self._set_direct_action()

    def _set_direct_action(self) -> None:
        for surface in self._surfaces:
            if surface.accepts_shift:
                surface.shift = self.shift
