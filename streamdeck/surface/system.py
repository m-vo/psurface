import os

from PIL import Image, ImageDraw, ImageFont, ImageOps
from StreamDeck.Devices import StreamDeck
from StreamDeck.ImageHelpers import PILHelper

from app import App
from state.layers import LayerController
from state.session import Session
from streamdeck.surface.surface import Surface


class SystemSurface(Surface):
    KEY_BRIGHTNESS = 4
    KEY_S_DCA = 0
    KEY_S_DCA_RESTORE = 1
    KEY_S_DCA_ACCEPT = 2
    KEY_STATUS = 9
    KEY_DIRECT_ACTION = 13
    KEY_HOME = 14

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
        self._assets["icon_back"] = os.path.join(self._assets_path, "back.png")
        self._assets["icon_check"] = os.path.join(self._assets_path, "check.png")

        # listen to and display status updates
        def update_status() -> None:
            self._set_image(self.KEY_STATUS, self._render_status())

        App.settings.status_changed_event.append(update_status)
        update_status()

    def init(self):
        super(SystemSurface, self).init()

        def setup_selects() -> None:
            self._set_image(self.KEY_S_DCA, self._render_s_dca_button())
            self._set_image(self.KEY_S_DCA + 1, self._render_s_dca_restore_button())
            self._set_image(self.KEY_S_DCA + 2, self._render_s_dca_accept_button())

        self._layer_controller.selection_update_event.append(setup_selects)
        setup_selects()

        def update_direct_action() -> None:
            self._set_image(self.KEY_DIRECT_ACTION, self._render_direct_action_button())

        App.settings.direct_action_changed_event.append(update_direct_action)
        update_direct_action()

        # init brightness
        self._update_brightness()

    def _on_key_down(self, key: int) -> None:
        super()._on_key_down(key)

        if key == self.KEY_BRIGHTNESS:
            App.settings.increase_brightness()
            return

        if key == self.KEY_DIRECT_ACTION:
            App.settings.toggle_direct_action()

    def _on_key_up(self, key: int) -> None:
        super()._on_key_up(key)

        if key == self.KEY_S_DCA:
            self._layer_controller.enable_s_dca_mode()
            return

        if key == self.KEY_S_DCA_RESTORE:
            self._layer_controller.restore_s_dca_values()
            return

        if key == self.KEY_S_DCA_ACCEPT:
            self._layer_controller.accept_s_dca_values()

    def _on_key_down_long(self, key: int) -> None:
        super()._on_key_down_long(key)

        # ignore direct action for system keys
        self._on_key_down(key)
        self._on_key_up(key)

    def _update_brightness(self) -> None:
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
        selected = self._layer_controller.mixing_selected

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
        selected = self._layer_controller.s_dca_selected
        active = self._layer_controller.s_dca_affected_channels > 0

        image = Image.new(
            "RGB",
            self._deck.key_image_format()["size"],
            ("black", (240, 240, 240))[selected],
        )

        draw = ImageDraw.Draw(image)

        if selected or active:
            draw.line((0, 7, 64, 7), fill=(100, 100, 100), width=1)
            draw.line((0, 58, 64, 58), fill=(100, 100, 100), width=1)

        self._render_component_s_dca_badge(draw, (7, 24), selected)

        return image

    def _render_s_dca_restore_button(self) -> Image:
        selected = self._layer_controller.s_dca_selected
        active = self._layer_controller.s_dca_affected_channels > 0

        if not selected and not active:
            return self._render_blank()
        else:
            image = PILHelper.create_scaled_image(
                self._deck,
                Image.open(self._assets["icon_back"]),
                margins=[18, 20, 20, 15],
            )

        background_color = ("black", (40, 40, 40))[selected]
        active_values_color = ((100, 100, 100), "red")[active]
        image = ImageOps.colorize(image.convert("L"), black=background_color, white=active_values_color)
        draw = ImageDraw.Draw(image)

        draw.line((0, 7, 64, 7), fill=(100, 100, 100), width=1)
        draw.line((0, 58, 64, 58), fill=(100, 100, 100), width=1)

        return image

    def _render_s_dca_accept_button(self) -> Image:
        selected = self._layer_controller.s_dca_selected
        affected_channels = self._layer_controller.s_dca_affected_channels
        active = affected_channels > 0

        if not selected and not active:
            return self._render_blank()
        else:
            image = PILHelper.create_scaled_image(
                self._deck,
                Image.open(self._assets["icon_check"]),
                margins=[17, 20, 18, 15],
            )

        background_color = ("black", (40, 40, 40))[selected]
        active_values_color = ((100, 100, 100), "green")[active]
        image = ImageOps.colorize(image.convert("L"), black=background_color, white=active_values_color)
        draw = ImageDraw.Draw(image)

        if active:
            draw.text(
                (41, 41),
                text=f"{affected_channels}",
                font=ImageFont.truetype(self._assets["font"], 14),
                anchor="lt",
                fill=active_values_color,
            )

        draw.line((0, 7, 64, 7), fill=(100, 100, 100), width=1)
        draw.line((0, 58, 64, 58), fill=(100, 100, 100), width=1)

        return image

    def _render_status(self) -> Image:
        image = Image.new("RGB", self._deck.key_image_format()["size"], "black")

        draw = ImageDraw.Draw(image)

        text = App.settings.status.replace(" | ", "\n")

        draw.text(
            (4, 10),
            text=text,
            font=ImageFont.truetype(self._assets["font"], 9),
            fill=(200, 200, 200),
        )

        return image
