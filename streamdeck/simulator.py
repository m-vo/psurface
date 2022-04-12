"""
 This file is part of the pSurface project. For the full copyright and license
 information, see the LICENSE file that was distributed with this source code.
"""
from collections import OrderedDict
from queue import Empty, Queue
from threading import Thread

import dearpygui.dearpygui as dpg
from StreamDeck.Devices import StreamDeck


class Simulator:
    def __init__(self) -> None:
        self._instances: OrderedDict[str, SimulatedDevice] = OrderedDict()

    def get_device(self, device_type, name: str):
        instance = _get_simulator_for(device_type)(name)
        self._instances[name] = instance
        return instance

    @property
    def has_devices(self) -> bool:
        return len(self._instances) > 0

    def run(self):
        thread = Thread(target=self._run)
        thread.start()

    def _run(self):
        dpg.create_context()

        device_gap = 8
        dpg.create_viewport(
            title="pSurface Simulator",
            width=sum(map(lambda i: i._get_width(), self._instances.values()))
            + device_gap * (len(self._instances) - 1),
            height=max(map(lambda i: i._get_height(), self._instances.values())),
            resizable=False,
            always_on_top=True,
        )

        offset = 0
        for instance in self._instances.values():
            instance._setup(offset)
            offset += instance._get_width() + device_gap

        dpg.setup_dearpygui()
        dpg.show_viewport()

        while dpg.is_dearpygui_running():
            for instance in self._instances.values():
                instance._loop()

            dpg.render_dearpygui_frame()

        dpg.start_dearpygui()
        dpg.destroy_context()


class Memoize:
    def __init__(self, f):
        self.f = f
        self.memo = {}

    def __call__(self, *args):
        return self.memo.setdefault(args, self.f(*args))


@Memoize
def _get_simulator_for(base):
    return type("SimulatedDevice", (SimulatedDevice, base), {})


class SimulatedDevice:  # virtual base class: StreamDeck
    GAP = 8
    """
    KEY_ROWS = 4
    KEY_COLS = 8
    KEY_PIXEL_WIDTH = 96
    KEY_PIXEL_HEIGHT = 96
    """

    # noinspection PyMissingConstructor
    def __init__(self, name: str):
        self._render_queue = Queue()
        self.key_callback = lambda ref, key, state: None
        self._name = name

    def __del__(self):
        pass

    def __enter__(self):
        pass

    def __exit__(self, type, value, traceback):
        pass

    def _read_key_states(self):
        pass

    def _reset_key_stream(self):
        pass

    def reset(self):
        pass

    def open(self):
        pass

    def close(self):
        pass

    def connected(self):
        return True

    def id(self):
        return "simulator"

    def is_open(self):
        return True

    def set_brightness(self, percent):
        pass

    def get_serial_number(self):
        return "simulator"

    def get_firmware_version(self):
        return "simulator"

    def set_key_image(self, key, image):
        self._render_queue.put((key, image))

    def _get_width(self) -> int:
        return (self.KEY_PIXEL_WIDTH + self.GAP) * self.KEY_COLS + self.GAP

    def _get_height(self) -> int:
        return (self.KEY_PIXEL_HEIGHT + self.GAP) * self.KEY_ROWS + self.GAP

    def _setup(self, offset: int = 0) -> None:
        rows = self.KEY_ROWS
        cols = self.KEY_COLS
        tile_size = self.KEY_PIXEL_WIDTH

        # create textures for all keys
        base_texture = [0, 0, 0, 1] * (tile_size * tile_size)
        for i in range(rows * cols):
            with dpg.texture_registry():
                dpg.add_dynamic_texture(tile_size, tile_size, base_texture, tag=f"tx_{self._name}_{i}")

        # create layout and handlers
        def on_mouse_click(sender, app_data):
            index = int(app_data[1][len(f"btn_{self._name}_") :])
            self.key_callback(self, index, True)

        with dpg.item_handler_registry(tag=f"btn_handler_{self._name}") as handler:
            dpg.add_item_clicked_handler(callback=on_mouse_click, button=dpg.mvMouseButton_Left)

        with dpg.window(
            tag=self._name,
            no_title_bar=True,
            width=self._get_width(),
            height=self._get_height(),
            no_close=True,
            no_resize=True,
            pos=[offset, 0],
            no_move=True,
        ):
            for row in range(rows):
                for col in range(cols):
                    index = (row * cols) + col
                    dpg.add_image(
                        f"tx_{self._name}_{index}",
                        pos=[col * (tile_size + self.GAP) + self.GAP, row * (tile_size + self.GAP) + self.GAP],
                        tag=f"btn_{self._name}_{index}",
                    )
                    dpg.bind_item_handler_registry(f"btn_{self._name}_{index}", f"btn_handler_{self._name}")

    def _loop(self):
        try:
            (key, image) = self._render_queue.get_nowait()

            # update texture
            texture_data = []
            for index, byte in enumerate(list(image.tobytes())):
                texture_data.append(byte / 255)
                if index % 3 == 2:
                    texture_data.append(1)  # alpha channel

            dpg.set_value(f"tx_{self._name}_{key}", texture_data)

        except Empty:
            pass
