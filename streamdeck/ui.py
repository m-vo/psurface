from StreamDeck.DeviceManager import DeviceManager

from app import App
from common.event import Event
from state.layers import LayerController
from state.session import Session
from streamdeck.surface.input import InputSurface
from streamdeck.surface.output import OutputSurface
from streamdeck.surface.system import SystemSurface


class DeckUI:
    def __init__(self, session: Session, layer_controller: LayerController):
        self._session = session
        self._layer_controller = layer_controller

        devices = {"system": None, "input": None, "output": None}
        devices_config = App.config.streamdeck_devices

        device_mapping = {
            devices_config["system"]: ["system", 15],
            devices_config["input"]: ["input", 32],
            devices_config["output"]: ["output", 32],
        }

        for device in DeviceManager().enumerate():
            device.open()
            serial = device.get_serial_number()

            if serial in device_mapping:
                name, min_key_count = device_mapping[serial]

                if device.key_count() >= min_key_count:
                    devices[name] = device

                    print(f"Found deck '{name}' with serial {serial}.")
                    continue
                else:
                    print(
                        f"Found an invalid deck matching the serial of '{name}'. Needs at least {min_key_count} keys."
                    )

            else:
                print(f"Found a deck with an unknown serial '{serial}'.")

            device.close()

        if not all([devices["system"], devices["input"], devices["output"]]):
            raise RuntimeError("Could not find and map all streamdecks.")

        self._system_surface = SystemSurface(devices["system"], session, layer_controller)
        self._input_surface = InputSurface(devices["input"], session, layer_controller)
        self._output_surface = OutputSurface(devices["output"], session, layer_controller)

        # Displayed entities
        self._displayed_channels = {}

    def init(self) -> None:
        App.settings.set_status("Running UI…")

        all_surfaces = [self._system_surface, self._input_surface, self._output_surface]

        # init surfaces
        for surface in all_surfaces:
            surface.init()

        self._layer_controller.select_default()
        App.settings.set_default_brightness()
