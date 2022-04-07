import os
from abc import ABC
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont
from PIL.ImageDraw import Draw
from StreamDeck.Devices import StreamDeck
from StreamDeck.ImageHelpers import PILHelper

from app import App
from dlive.api import DLive
from dlive.entity import ChannelIdentifier, Color
from dlive.virtual import LayerController


class Assets(ABC):
    assets_path = os.path.join(os.path.dirname(__file__), "../../assets")

    font = os.path.join(assets_path, "Roboto-Regular.ttf")
    icon_home = os.path.join(assets_path, "home.png")
    icon_mic = os.path.join(assets_path, "mic.png")
    icon_filter = os.path.join(assets_path, "filter.png")
    icon_brightness = os.path.join(assets_path, "brightness.png")
    icon_direct = os.path.join(assets_path, "direct.png")
    icon_left = os.path.join(assets_path, "left.png")
    icon_back = os.path.join(assets_path, "back.png")
    icon_check = os.path.join(assets_path, "check.png")


class Surface:
    direct_action: bool = False
    accepts_direct_action = True

    def __init__(self, device: StreamDeck, dlive: DLive, layer_controller: LayerController) -> None:
        self._device = device
        self._dlive = dlive
        self._layer_controller = layer_controller

        self._blank_image = Image.new(
            "RGB",
            self._device.key_image_format()["size"],
            "black",
        )

        device.reset()
        self._handle_key_presses()

    def __del__(self):
        self._device.close()

    ###############
    # Key actions #
    ###############
    def _handle_key_presses(self):
        prefix = self._device.get_serial_number()

        def key_change(_, key: int, state: bool) -> None:
            if state:
                if self.direct_action:
                    self._on_key_down_long(key)
                    return

                App.scheduler.execute_delayed(prefix + "_key_" + repr(key), 1.0, self._on_key_down_long, [key])

                self._on_key_down(key)
            else:
                if not App.scheduler.cancel(prefix + "_key_" + repr(key)):
                    #  skip handler if job was already executed (_on_key_down_long)
                    return

                if self.direct_action:
                    return

                self._on_key_up(key)

        self._device.set_key_callback(key_change)

    def _on_key_down(self, key: int):
        pass

    def _on_key_up(self, key: int):
        pass

    def _on_key_down_long(self, key: int):
        pass

    #############
    # Rendering #
    #############
    def _set_image(self, key: int, image: Image):
        with self._device:
            self._device.set_key_image(key, PILHelper.to_native_format(self._device, image))

    def _render_channel(self, channel: ChannelIdentifier):
        image = Image.new(
            "RGB",
            self._device.key_image_format()["size"],
            ("black", (240, 240, 240))[self._layer_controller.is_selected(channel)],
        )

        draw = ImageDraw.Draw(image)
        label_prefix = channel.bank.short_name
        label = self._dlive.get_label(channel)

        if not label.has_name:
            draw.text(
                (image.width / 2, 10),
                text=f"{label_prefix} {channel.canonical_index + 1}",
                font=ImageFont.truetype(Assets.font, 16),
                anchor="mt",
                fill=(100, 100, 100),
            )

            return image

        self._render_component_top_label(draw, channel)
        self._render_component_level_indicator(draw, channel, (76, 92))
        self._render_component_mute_badge(draw, channel, (11, 73))

        draw.text(
            (6, 46),
            text=f"{label_prefix} {channel.canonical_index + 1}",
            font=ImageFont.truetype(Assets.font, 12),
            anchor="lb",
            fill=((100, 100, 100), (50, 50, 50))[self._layer_controller.is_selected(channel)],
        )

        return image

    def _render_component_top_label(self, draw: Draw, channel: ChannelIdentifier) -> None:
        color = self._dlive.get_color(channel)

        draw.rectangle((0, 0, 96, 28), fill=color.rgb)
        draw.line((0, 29, 96, 29), fill="black", width=3)

        inverted = color in [Color.OFF, Color.RED, Color.PURPLE, Color.BLUE]

        draw.text(
            (48, 7),
            text=self._dlive.get_label(channel),
            font=ImageFont.truetype(Assets.font, 20),
            anchor="mt",
            fill=("black", "white")[inverted],
        )

    def _render_component_level_indicator(
        self, draw: Draw, channel: ChannelIdentifier, coords_bl: Tuple[int, int], height: int = 38
    ) -> None:
        level = self._dlive.get_level(channel)

        draw.text(
            (coords_bl[0], coords_bl[1] - height - 18),
            text=f"{level}",
            font=ImageFont.truetype(Assets.font, 16),
            anchor="mt",
            fill=((200, 200, 200), (10, 10, 10))[self._layer_controller.is_selected(channel)],
        )

        width = 8
        outline = 2
        y_level = level * (height - 2 * outline) / 127

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

    def _render_component_mute_badge(self, draw: Draw, channel: ChannelIdentifier, coords_bl: Tuple[int, int]) -> None:
        self._render_component_badge(
            draw,
            coords_bl,
            "MUTE",
            fill=((50, 50, 50), (200, 0, 0))[self._dlive.get_mute(channel)],
            stroke=("black", "white")[self._layer_controller.is_selected(channel)],
        )

    def _render_component_badge(self, draw: Draw, coords_bl: Tuple[int, int], label: str, fill, stroke) -> None:
        draw.rounded_rectangle(
            (coords_bl[0], coords_bl[1], coords_bl[0] + 52, coords_bl[1] + 18),
            radius=4,
            fill=fill,
        )

        draw.text(
            (coords_bl[0] + 27, coords_bl[1] + 10),
            text=label,
            font=ImageFont.truetype(Assets.font, 15),
            anchor="mm",
            fill=stroke,
        )
