import os
from abc import ABC
from typing import Tuple

from PIL import Image, ImageDraw, ImageFont, ImageOps
from PIL.ImageDraw import Draw
from StreamDeck.Devices import StreamDeck
from StreamDeck.Devices.StreamDeckXL import StreamDeckXL
from StreamDeck.ImageHelpers import PILHelper

from app import App
from dlive.entity import Channel, Color
from state.layers import LayerController
from state.session import Session
from streamdeck.util import FragmentRenderer


class Surface(ABC):
    KEY_HOME: int

    def __init__(
        self,
        device: StreamDeck,
        session: Session,
        layer_controller: LayerController,
    ):
        device.reset()
        self._deck: StreamDeck = device

        self._session: Session = session
        self._layer_controller: LayerController = layer_controller
        self._fragment_renderer = FragmentRenderer()

        self._keys_down: {}

        self._assets_path = os.path.join(os.path.dirname(__file__), "../../assets")
        self._assets = {
            "font": os.path.join(self._assets_path, "Roboto-Regular.ttf"),
            "icon_home": os.path.join(self._assets_path, "home.png"),
        }

    def __del__(self):
        self._deck.close()

    def init(self):
        # handle brightness update
        App.settings.brightness_changed_event.append(self._update_brightness)

        # handle key presses
        def key_change(_, key: int, state: bool) -> None:
            if state:
                if App.settings.direct_action:
                    self._on_key_down_long(key)
                    return

                App.scheduler.execute_delayed("key_" + repr(key), 1.0, self._on_key_down_long, [key])

                self._on_key_down(key)
            else:
                if not App.scheduler.cancel("key_" + repr(key)):
                    #  skip handler if job was already executed (_on_key_down_long)
                    return

                if App.settings.direct_action:
                    return

                self._on_key_up(key)

        self._deck.set_key_callback(key_change)

        # handle external channel updates
        self._session.channel_update_event.append(self._fragment_renderer.update)

        # add home button
        def render_home_button() -> None:
            self._set_image(self.KEY_HOME, self._render_home_button())

        self._layer_controller.selection_update_event.append(render_home_button)
        render_home_button()

    def _on_key_down(self, key: int):
        pass

    def _on_key_up(self, key: int):
        if key == self.KEY_HOME:
            self._layer_controller.select_mixing()

    def _on_key_down_long(self, key: int):
        pass

    def _update_brightness(self):
        streamdeck_original_map = {0: 20, 1: 29, 2: 43, 3: 50, 4: 60}
        streamdeck_xl_map = {0: 18, 1: 28, 2: 43, 3: 65, 4: 100}

        value_set = (streamdeck_original_map, streamdeck_xl_map)[isinstance(self._deck, StreamDeckXL)]
        self._deck.set_brightness(value_set[App.settings.brightness])

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

    def _render_component_badge(self, draw: Draw, coords_bl: Tuple[int, int], label: str, fill, stroke) -> None:
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

    def _render_component_mute_badge(self, draw: Draw, channel: Channel, coords_bl: Tuple[int, int]) -> None:
        self._render_component_badge(
            draw,
            coords_bl,
            "MUTE",
            fill=((50, 50, 50), (200, 0, 0))[channel.mute],
            stroke=("black", "white")[channel.selected],
        )

    def _render_component_s_dca_badge(self, draw: Draw, coords_bl: Tuple[int, int], enabled: bool = True) -> None:
        self._render_component_badge(
            draw,
            coords_bl,
            "S-DCA",
            fill=((50, 50, 50), (90, 200, 0))[enabled],
            stroke="black",
        )

    def _render_custom_select(self, label: str, selected: bool) -> Image:
        image = Image.new(
            "RGB",
            self._deck.key_image_format()["size"],
            ("black", (240, 240, 240))[selected],
        )

        draw = ImageDraw.Draw(image)
        draw.text(
            (image.width / 2, image.height / 2),
            text=label,
            font=ImageFont.truetype(self._assets["font"], 25),
            anchor="mm",
            fill=((240, 240, 240), (50, 50, 50))[selected],
        )

        return image

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

    def _render_home_button(self) -> Image:
        image = PILHelper.create_scaled_image(
            self._deck,
            Image.open(self._assets["icon_home"]),
            margins=[16, 18, 18, 15],
        )

        if self._layer_controller.mixing_selected:
            image = ImageOps.colorize(image.convert("L"), black="white", white="black")

        return image

    def _render_blank(self):
        return Image.new(
            "RGB",
            self._deck.key_image_format()["size"],
            "black",
        )
