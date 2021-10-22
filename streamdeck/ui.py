import os
from datetime import datetime, timedelta
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageDraw import Draw
from StreamDeck.DeviceManager import DeviceManager
from StreamDeck.Devices import StreamDeck
from StreamDeck.Devices.StreamDeckXL import StreamDeckXL
from StreamDeck.ImageHelpers import PILHelper
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from tzlocal import get_localzone

from common.event import Event
from common.session import Session, LayerController
from dlive.entity import (
    Channel,
    Color,
    OutputChannel,
    InputChannel,
)
from streamdeck.util import FragmentRenderer


class DeckUI:
    def __init__(
        self, devices_config: dict, session: Session, layer_controller: LayerController
    ):
        self._session = session
        self._layer_controller = layer_controller

        devices = {"system": None, "input": None, "output": None}

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

        self._system_surface = SystemSurface(
            devices["system"], session, layer_controller
        )
        self._input_surface = InputSurface(devices["input"], session, layer_controller)
        self._output_surface = OutputSurface(
            devices["output"], session, layer_controller
        )

        # Displayed entities
        self._displayed_channels = {}

    def init(self) -> None:
        all_surfaces = [self._system_surface, self._input_surface, self._output_surface]

        # setup events
        def set_brightness(level: int) -> None:
            for surface in all_surfaces:
                surface.set_brightness(level)

        self._system_surface.brightness_changed_event.append(set_brightness)

        # init surfaces
        for surface in all_surfaces:
            surface.init()


class Surface:
    def __init__(
        self, device: StreamDeck, session: Session, layer_controller: LayerController
    ):
        device.reset()
        self._deck: StreamDeck = device

        self._session: Session = session
        self._layer_controller: LayerController = layer_controller
        self._fragment_renderer = FragmentRenderer()
        self._scheduler = BackgroundScheduler()
        self._brightness = 0

        self._keys_down: {}

        self._assets_path = os.path.join(os.path.dirname(__file__), "../assets")
        self._assets = {
            "font": os.path.join(self._assets_path, "Roboto-Regular.ttf"),
        }

    def __del__(self):
        self._deck.close()

    def init(self):
        def key_change(_, key: int, state: bool) -> None:
            if state:
                self._scheduler.add_job(
                    self._on_key_down_long,
                    DateTrigger(datetime.now(get_localzone()) + timedelta(seconds=1.0)),
                    [key],
                    id=repr(key),
                    replace_existing=True,
                )
                self._on_key_down(key)
            else:
                try:
                    self._scheduler.remove_job(repr(key))
                except JobLookupError:
                    #  skip handler if no job is present - it was already executed (_on_key_down_long)
                    return

                self._on_key_up(key)

        self._deck.set_key_callback(key_change)
        self._session.channel_update_event.append(self._on_channel_update)
        self._scheduler.start()

        pass

    def set_brightness(self, level: int):
        self._brightness = level
        self._update_brightness()

    def _on_key_down(self, key: int):
        pass

    def _on_key_up(self, key: int):
        pass

    def _on_key_down_long(self, key: int):
        pass

    def _on_channel_update(self, channel: Channel):
        self._fragment_renderer.update(channel)

    def _update_brightness(self):
        streamdeck_original_map = {0: 20, 1: 29, 2: 43, 3: 50, 4: 60}
        streamdeck_xl_map = {0: 18, 1: 28, 2: 43, 3: 65, 4: 100}

        value_set = (streamdeck_original_map, streamdeck_xl_map)[
            isinstance(self._deck, StreamDeckXL)
        ]
        self._deck.set_brightness(value_set[self._brightness])

    def _set_image(self, key: int, image: Image):
        with self._deck:
            self._deck.set_key_image(key, PILHelper.to_native_format(self._deck, image))

    def _render_component_top_label(self, draw: Draw, channel: Channel) -> None:
        inverted = channel.color in [Color.OFF, Color.RED, Color.PURPLE, Color.BLUE]

        draw.rectangle((0, 0, 96, 28), fill=channel.color.rgb)
        draw.line((0, 29, 96, 29), fill="black", width=3)

        draw.text(
            (48, 7),
            text=channel.label,
            font=ImageFont.truetype(self._assets["font"], 20),
            anchor="mt",
            fill=("black", "white")[inverted],
        )

    def _render_component_level_indicator(
        self, draw: Draw, channel: Channel, coords_bl: Tuple[int, int], height: int = 38
    ) -> None:
        draw.text(
            (coords_bl[0], coords_bl[1] - height - 18),
            text=f"{channel.level}",
            font=ImageFont.truetype(self._assets["font"], 16),
            anchor="mt",
            fill=((200, 200, 200), (10, 10, 10))[channel.selected],
        )

        width = 8
        outline = 2
        y_level = channel.level * (height - 2 * outline) / 127

        draw.rectangle(
            (*coords_bl, coords_bl[0] + width, coords_bl[1] - height),
            fill="black",
            outline=(50, 50, 50),
            width=outline,
        )

        draw.rectangle(
            (
                coords_bl[0] + outline,
                coords_bl[1] - outline,
                coords_bl[0] + width - outline,
                coords_bl[1] - outline - y_level,
            ),
            fill="white",
            outline=None,
        )

    def _render_component_badge(
        self, draw: Draw, coords_bl: Tuple[int, int], label: str, fill, stroke
    ) -> None:
        draw.rounded_rectangle(
            (coords_bl[0], coords_bl[1], coords_bl[0] + 52, coords_bl[1] + 18),
            radius=4,
            fill=fill,
        )

        draw.text(
            (coords_bl[0] + 27, coords_bl[1] + 10),
            text=label,
            font=ImageFont.truetype(self._assets["font"], 15),
            anchor="mm",
            fill=stroke,
        )

    def _render_component_mute_badge(
        self, draw: Draw, channel: Channel, coords_bl: Tuple[int, int]
    ) -> None:
        self._render_component_badge(
            draw,
            coords_bl,
            "MUTE",
            fill=((50, 50, 50), (200, 0, 0))[channel.mute],
            stroke=("black", "white")[channel.selected],
        )

    def _render_component_s_dca_badge(
        self, draw: Draw, coords_bl: Tuple[int, int], enabled: bool = True
    ) -> None:
        self._render_component_badge(
            draw,
            coords_bl,
            "S-DCA",
            fill=((50, 50, 50), (90, 200, 0))[enabled],
            stroke="black",
        )

    def _render_channel(self, channel: Channel):
        image = Image.new(
            "RGB",
            self._deck.key_image_format()["size"],
            ("black", (240, 240, 240))[channel.selected],
        )

        draw = ImageDraw.Draw(image)
        label_prefix = channel.identifier.bank.short_name

        if not channel.is_visible:
            draw.text(
                (image.width / 2, 10),
                text=f"{label_prefix} {channel.identifier.canonical_index + 1}",
                font=ImageFont.truetype(self._assets["font"], 16),
                anchor="mt",
                fill=(100, 100, 100),
            )

            return image

        self._render_component_top_label(draw, channel)
        self._render_component_level_indicator(draw, channel, (76, 92))
        self._render_component_mute_badge(draw, channel, (11, 73))

        draw.text(
            (6, 46),
            text=f"{label_prefix} {channel.identifier.canonical_index + 1}",
            font=ImageFont.truetype(self._assets["font"], 12),
            anchor="lb",
            fill=((100, 100, 100), (50, 50, 50))[channel.selected],
        )

        return image


class InputSurface(Surface):
    def init(self):
        super(InputSurface, self).init()

        def render_channel(key: int, c: Channel) -> None:
            self._set_image(key, self._render_channel(c))

        key = 0
        for channel in self._session.input_channels:
            self._fragment_renderer.add_fragment(key, channel, render_channel)
            key += 1

            if key == 32:
                return

    def _on_key_up(self, key: int):
        channel = self._fragment_renderer.get_channel(key)

        if isinstance(channel, InputChannel) and channel.is_visible:
            self._layer_controller.select_input(channel)

    def _on_key_down_long(self, key: int):
        channel = self._fragment_renderer.get_channel(key)
        if channel and channel.is_visible:
            channel.set_mute(not channel.mute)

    def _render_channel(self, channel: Channel):
        image = super(InputSurface, self)._render_channel(channel)
        draw = ImageDraw.Draw(image)

        if isinstance(channel, InputChannel) and channel.affected_by_s_dca:
            self._render_component_s_dca_badge(draw, (11, 51))

        return image


class OutputSurface(Surface):
    def init(self):
        super(OutputSurface, self).init()

        def render_channel(key: int, c: Channel) -> None:
            self._set_image(key, self._render_channel(c))

        key = 0
        for channel in self._session.aux_channels:
            self._fragment_renderer.add_fragment(key, channel, render_channel)
            key += 1

        for channel in self._session.fx_channels:
            self._fragment_renderer.add_fragment(key, channel, render_channel)
            key += 1

    def _on_key_up(self, key: int):
        channel = self._fragment_renderer.get_channel(key)

        if isinstance(channel, OutputChannel) and channel.is_visible:
            self._layer_controller.select_output(channel)

    def _on_key_down_long(self, key: int):
        channel = self._fragment_renderer.get_channel(key)
        if channel and channel.is_visible:
            channel.set_mute(not channel.mute)


class SystemSurface(Surface):
    KEY_BRIGHTNESS = 14
    KEY_INPUTS = 0
    KEY_S_DCA = 5

    def __init__(
        self, device: StreamDeck, session: Session, layer_controller: LayerController
    ):
        super(SystemSurface, self).__init__(device, session, layer_controller)

        self._assets["icon_brightness"] = os.path.join(
            self._assets_path, "brightness.png"
        )

        self._assets["icon_left"] = os.path.join(self._assets_path, "left.png")

        self.brightness_changed_event = Event()

    def init(self):
        super(SystemSurface, self).init()

        self._layer_controller.selection_update_event.append(self._on_select_change)
        self._layer_controller.select_default()

        self.brightness_changed_event(2)

    def _on_select_change(self):
        self._set_image(self.KEY_INPUTS, self._render_inputs_button())
        self._set_image(self.KEY_S_DCA, self._render_s_dca_button())

    def _on_key_down(self, key: int):
        if key == self.KEY_BRIGHTNESS:
            new_brightness = (self._brightness + 1) % 5
            self.brightness_changed_event(new_brightness)

    def _on_key_up(self, key: int):
        if key == self.KEY_INPUTS:
            self._layer_controller.select_default()
            return

        if key == self.KEY_S_DCA:
            self._layer_controller.toggle_s_dca_mode()

    def _on_key_down_long(self, key: int):
        if key == self.KEY_S_DCA:
            self._layer_controller.clear_s_dca()
            return

    def _update_brightness(self):
        super(SystemSurface, self)._update_brightness()

        self._set_image(self.KEY_BRIGHTNESS, self._render_brightness_indicator())

    def _render_brightness_indicator(self) -> Image:
        image = PILHelper.create_scaled_image(
            self._deck,
            Image.open(self._assets["icon_brightness"]),
            margins=[10, 20, 10, 15],
        )

        x = image.width - 10
        y_bot = image.height - 12
        y_top = 12
        y_level = y_bot - 8 - (self._brightness * (y_bot - y_top - 8) / 4)
        width = 3

        draw = ImageDraw.Draw(image)

        draw.line((x, y_bot, x, y_top), fill=(50, 50, 50), width=width)
        draw.line((x, y_bot, x, y_level), fill="white", width=width)

        return image

    def _render_inputs_button(self) -> Image:
        selected = self._layer_controller.default_selected

        image = Image.new(
            "RGB",
            self._deck.key_image_format()["size"],
            ("black", (240, 240, 240))[selected],
        )

        draw = ImageDraw.Draw(image)

        self._render_component_badge(
            draw,
            (7, 10),
            "Inputs",
            fill=(50, 50, 50),
            stroke=("black", "white")[selected],
        )

        return image

    def _render_s_dca_button(self) -> Image:
        active = self._layer_controller.s_dca_active

        image = Image.new(
            "RGB",
            self._deck.key_image_format()["size"],
            ("black", (240, 240, 240))[self._layer_controller.s_dca_selected],
        )

        draw = ImageDraw.Draw(image)

        self._render_component_s_dca_badge(draw, (7, 10), active)

        if active:
            draw.text(
                (12, 34),
                text="hold to\nrestore",
                font=ImageFont.truetype(self._assets["font"], 14),
                fill=((255, 255, 255), (50, 50, 50))[active],
            )

        return image
