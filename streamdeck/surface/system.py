import os

from PIL import Image, ImageDraw, ImageFont, ImageOps
from StreamDeck.Devices import StreamDeck
from StreamDeck.ImageHelpers import PILHelper

from app import App
from state.layers import LayerController
from state.session import Session
from streamdeck.surface.surface import Surface


class SystemSurface(Surface):
    KEY_BRIGHTNESS = 14
    KEY_INPUTS = 0
    KEY_S_DCA = 5
    KEY_DIRECT_ACTION = 4
    KEY_STATUS = 12

    def __init__(
        self,
        device: StreamDeck,
        session: Session,
        layer_controller: LayerController,
    ):
        super(SystemSurface, self).__init__(device, session, layer_controller)

        self._assets["icon_brightness"] = os.path.join(self._assets_path, "brightness.png")
        self._assets["icon_direct"] = os.path.join(self._assets_path, "direct.png")
        self._assets["icon_left"] = os.path.join(self._assets_path, "left.png")

        # listen to and display status updates
        def update_status() -> None:
            self._set_image(self.KEY_STATUS, self._render_status())

        App.settings.status_changed_event.append(update_status)
        update_status()

    def init(self):
        super(SystemSurface, self).init()

        self._layer_controller.selection_update_event.append(self._on_select_change)

        self._update_brightness()
        self._update_direct_action()

    def _on_select_change(self):
        self._set_image(self.KEY_INPUTS, self._render_inputs_button())
        self._set_image(self.KEY_S_DCA, self._render_s_dca_button())

    def _on_key_down(self, key: int):
        if key == self.KEY_BRIGHTNESS:
            App.settings.increase_brightness()
            return

        if key == self.KEY_DIRECT_ACTION:
            App.settings.toggle_direct_action()
            self._update_direct_action()

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

        # ignore direct action for other system keys
        self._on_key_down(key)
        self._on_key_up(key)

    def _update_brightness(self):
        super(SystemSurface, self)._update_brightness()

        self._set_image(self.KEY_BRIGHTNESS, self._render_brightness_indicator())

    def _update_direct_action(self):
        self._set_image(self.KEY_DIRECT_ACTION, self._render_direct_action_button())

    def _render_brightness_indicator(self) -> Image:
        image = PILHelper.create_scaled_image(
            self._deck,
            Image.open(self._assets["icon_brightness"]),
            margins=[10, 20, 10, 15],
        )

        x = image.width - 10
        y_bot = image.height - 12
        y_top = 12
        y_level = y_bot - 8 - (App.settings.brightness * (y_bot - y_top - 8) / 4)
        width = 3

        draw = ImageDraw.Draw(image)

        draw.line((x, y_bot, x, y_top), fill=(50, 50, 50), width=width)
        draw.line((x, y_bot, x, y_level), fill="white", width=width)

        return image

    def _render_direct_action_button(self) -> Image:
        image = PILHelper.create_scaled_image(
            self._deck,
            Image.open(self._assets["icon_direct"]),
            margins=[16, 18, 18, 15],
        )

        if App.settings.direct_action:
            active_color = (255, 0, 50)
            image = ImageOps.colorize(image.convert("L"), black="black", white=active_color)

            draw = ImageDraw.Draw(image)
            draw.ellipse(
                (5, 5, image.width - 10, image.height - 10),
                outline=active_color,
                width=4,
            )

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

    def _render_status(self) -> Image:
        image = Image.new("RGB", self._deck.key_image_format()["size"], "black")

        draw = ImageDraw.Draw(image)

        draw.text(
            (5, 10),
            text=App.settings.status,
            font=ImageFont.truetype(self._assets["font"], 10),
            anchor="lt",
            fill=(200, 200, 200),
        )

        return image
