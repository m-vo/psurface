from typing import Optional, Callable, Dict

from PIL import Image, ImageDraw, ImageFont, ImageOps
from StreamDeck.Devices import StreamDeck
from StreamDeck.ImageHelpers import PILHelper

from app import App
from dlive.api import DLive
from dlive.entity import ChannelIdentifier
from dlive.virtual import LayerController, LayerMode
from streamdeck.surface.surface import Surface, Assets
from streamdeck.util import ChannelRenderer


class SystemSurface(Surface):
    accepts_direct_action = False

    KEY_BRIGHTNESS = 4
    KEY_INFO = 3
    KEY_MIXING = 14
    KEY_CUSTOM_AUX_MASTER = 7
    KEY_CUSTOM_FX_MASTER = 6
    KEY_CUSTOM_UTIL_MASTER = 9
    KEY_CUSTOM_GROUP_MASTER = 8
    KEY_CUSTOM_DCA_MASTER = 5
    KEY_TALK_TO_MONITOR = 1
    KEY_TALK_TO_STAGE = 0
    KEY_SENDS_TARGET = 10
    KEY_CHANNEL_FILTER = 11
    KEY_DIRECT_ACTION = 13

    def __init__(
        self,
        device: StreamDeck,
        dlive: DLive,
        layer_controller: LayerController,
        delegates: Dict[str, Callable],
    ) -> None:
        super().__init__(device, dlive, layer_controller)

        self._ui_delegates = delegates

        self._set_image(self.KEY_INFO, self._render_static_info())

        # Mixing and other layer modes
        def display_mode_selects(mode: LayerMode) -> None:
            self._set_image(self.KEY_MIXING, self._render_mixing_button(mode == LayerMode.MIXING))
            self._set_image(self.KEY_CUSTOM_AUX_MASTER, self._render_custom_select("AUX", mode == LayerMode.CUSTOM_AUX))
            self._set_image(self.KEY_CUSTOM_FX_MASTER, self._render_custom_select("FX", mode == LayerMode.CUSTOM_FX))
            self._set_image(
                self.KEY_CUSTOM_UTIL_MASTER, self._render_custom_select("UTIL", mode == LayerMode.CUSTOM_UTIL)
            )
            self._set_image(
                self.KEY_CUSTOM_GROUP_MASTER, self._render_custom_select("GRP", mode == LayerMode.CUSTOM_GROUP)
            )
            self._set_image(self.KEY_CUSTOM_DCA_MASTER, self._render_custom_select("DCA", mode == LayerMode.CUSTOM_DCA))

        display_mode_selects(self._layer_controller.get_mode())
        layer_controller.on_mode_changed.append(display_mode_selects)

        # Filter and send target modifiers
        def display_layer_modifiers(target: Optional[str] = None, value: bool = False) -> None:
            if not target or target == "filter":
                self._set_image(self.KEY_CHANNEL_FILTER, self._render_channel_filter_toggle(value))

            if not target or target == "sends_target":
                self._set_image(self.KEY_SENDS_TARGET, self._render_sends_target_toggle(value))

        display_layer_modifiers()
        layer_controller.on_modifier_changed.append(display_layer_modifiers)

        # Direct action, brightness and other UI only modifiers
        self._display_action_modifier()
        self._display_brightness_selector()

        # Channels
        self._channel_renderer = ChannelRenderer(dlive, layer_controller, 2)

        self._channel_renderer.add_channel(
            dlive.talk_to_stage_channel,
            lambda k: self._set_image(
                self.KEY_TALK_TO_STAGE, self._render_talk_to("STAGE.", dlive.talk_to_stage_channel)
            ),
        )

        self._channel_renderer.add_channel(
            dlive.talk_to_monitor_channel,
            lambda k: self._set_image(
                self.KEY_TALK_TO_MONITOR, self._render_talk_to("MON.", dlive.talk_to_monitor_channel)
            ),
        )

        self._channel_renderer.enable_static_strategy()

    def _display_action_modifier(self) -> None:
        self._set_image(self.KEY_DIRECT_ACTION, self._render_direct_action_toggle())

    def _display_brightness_selector(self) -> None:
        self._set_image(self.KEY_BRIGHTNESS, self._render_brightness_indicator())

    def _on_key_down(self, key: int):
        super()._on_key_down(key)

        if key == self.KEY_MIXING:
            self._layer_controller.select_mixing_mode()
            return

        if key == self.KEY_CUSTOM_AUX_MASTER:
            self._layer_controller.select_custom_aux_mode()
            return

        if key == self.KEY_CUSTOM_FX_MASTER:
            self._layer_controller.select_custom_fx_mode()
            return

        if key == self.KEY_CUSTOM_UTIL_MASTER:
            self._layer_controller.select_custom_util_mode()
            return

        if key == self.KEY_CUSTOM_GROUP_MASTER:
            self._layer_controller.select_custom_group_mode()
            return

        if key == self.KEY_CUSTOM_DCA_MASTER:
            self._layer_controller.select_custom_dca_mode()
            return

        if key == self.KEY_SENDS_TARGET:
            self._layer_controller.toggle_sends_target()
            return

        if key == self.KEY_CHANNEL_FILTER:
            self._layer_controller.toggle_channel_filter()
            return

        if key == self.KEY_DIRECT_ACTION:
            self._ui_delegates["toggle_direct_action"]()
            self._display_action_modifier()
            return

        if key == self.KEY_BRIGHTNESS:
            self._ui_delegates["toggle_brightness"]()
            self._display_brightness_selector()
            return

        if key == self.KEY_TALK_TO_STAGE:
            self._dlive.change_mute(
                self._dlive.talk_to_stage_channel, not self._dlive.get_mute(self._dlive.talk_to_stage_channel)
            )
            return

        if key == self.KEY_TALK_TO_MONITOR:
            self._dlive.change_mute(
                self._dlive.talk_to_monitor_channel, not self._dlive.get_mute(self._dlive.talk_to_monitor_channel)
            )
            return

        if key == self.KEY_INFO:
            App.notify(self._dlive.__str__())
            return

    def _render_static_info(self) -> Image:
        image = Image.new("RGB", self._device.key_image_format()["size"], (0, 0, 0))
        draw = ImageDraw.Draw(image)

        draw.text(
            (5, 12),
            text="pSurface",
            font=ImageFont.truetype(Assets.font, 14),
            fill=(200, 200, 200),
        )

        draw.text(
            (5, 30),
            text=f"{App.version}",
            font=ImageFont.truetype(Assets.font, 10),
            fill=(200, 200, 200),
        )

        return image

    def _render_brightness_indicator(self) -> Image:
        image = PILHelper.create_scaled_image(
            self._device,
            Image.open(Assets.icon_brightness),
            margins=[10, 20, 10, 15],
        )

        x = image.width - 10
        y_bot = image.height - 12
        y_top = 12
        y_level = y_bot - 8 - (self._ui_delegates["brightness"]() * (y_bot - y_top - 8) / 4)
        width = 3

        draw = ImageDraw.Draw(image)

        draw.line((x, y_bot, x, y_top), fill=(50, 50, 50), width=width)
        draw.line((x, y_bot, x, y_level), fill="white", width=width)

        return image

    def _render_custom_select(self, label: str, selected: bool) -> Image:
        image = Image.new(
            "RGB",
            self._device.key_image_format()["size"],
            ("black", (240, 240, 240))[selected],
        )

        draw = ImageDraw.Draw(image)
        draw.text(
            (image.width / 2, image.height / 2),
            text=label,
            font=ImageFont.truetype(Assets.font, 25),
            anchor="mm",
            fill=((240, 240, 240), (50, 50, 50))[selected],
        )

        return image

    def _render_mixing_button(self, selected: bool) -> Image:
        image = PILHelper.create_scaled_image(
            self._device,
            Image.open(Assets.icon_home),
            margins=[16, 18, 18, 15],
        )

        if selected:
            image = ImageOps.colorize(image.convert("L"), black="white", white="black")

        return image

    def _render_talk_to(self, label: str, channel: ChannelIdentifier) -> Image:
        image = PILHelper.create_scaled_image(
            self._device,
            Image.open(Assets.icon_mic),
            margins=[8, 35, 37, 0],
        )

        mute = self._dlive.get_mute(channel)
        color = ((240, 240, 240), (100, 100, 100))[mute]

        if mute:
            image = ImageOps.colorize(image.convert("L"), black="black", white=color)

        draw = ImageDraw.Draw(image)

        if mute:
            draw.line((9, 34, 28, 10), fill=color, width=2)

        draw.text(
            (image.width / 2, 54),
            text=label,
            font=ImageFont.truetype(Assets.font, 16),
            anchor="mm",
            fill=color,
        )

        draw.text(
            (35, 30),
            text=f"{channel.bank.short_name} {channel.canonical_index + 1}",
            font=ImageFont.truetype(Assets.font, 12),
            anchor="lb",
            fill=(100, 100, 100),
        )

        return image

    def _render_sends_target_toggle(self, selected: bool) -> Image:
        image = self._blank_image
        draw = ImageDraw.Draw(image)

        self._render_component_badge(
            draw,
            (7, 12),
            "AUX",
            fill=((50, 50, 50), (170, 0, 170))[not selected],
            stroke="black",
        )

        self._render_component_badge(
            draw,
            (7, 41),
            "FX",
            fill=((50, 50, 50), (0, 255, 0))[selected],
            stroke="black",
        )

        return image

    def _render_channel_filter_toggle(self, selected: bool) -> Image:
        image = PILHelper.create_scaled_image(
            self._device,
            Image.open(Assets.icon_filter),
            margins=[16, 18, 16, 14],
        )

        if selected:
            active_color = (255, 0, 0)
            image = ImageOps.colorize(image.convert("L"), black="black", white=active_color)

            draw = ImageDraw.Draw(image)
            draw.ellipse(
                (6, 6, image.width - 12, image.height - 12),
                outline=active_color,
                width=4,
            )

        return image

    def _render_direct_action_toggle(self) -> Image:
        image = PILHelper.create_scaled_image(
            self._device,
            Image.open(Assets.icon_direct),
            margins=[14, 18, 18, 15],
        )

        if self._ui_delegates["direct_action"]():
            active_color = (255, 0, 0)
            image = ImageOps.colorize(image.convert("L"), black="black", white=active_color)

            draw = ImageDraw.Draw(image)
            draw.ellipse(
                (6, 6, image.width - 12, image.height - 12),
                outline=active_color,
                width=4,
            )

        return image
