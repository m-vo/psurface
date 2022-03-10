import os

from PIL import Image, ImageDraw, ImageFont, ImageOps
from PIL.ImageDraw import Draw
from StreamDeck.Devices import StreamDeck
from StreamDeck.Devices.StreamDeckXL import StreamDeckXL
from StreamDeck.ImageHelpers import PILHelper

from app import App
from dlive.entity import Channel, OutputChannel
from state.layers import LayerController
from state.session import Session
from streamdeck.surface.surface import Surface
from streamdeck.util import ChannelPacking


class OutputSurface(Surface):
    KEY_FILTER = 24
    KEY_CUSTOM_AUX_MASTER = 25
    KEY_CUSTOM_FX_MASTER = 26
    KEY_CUSTOM_UTIL_MASTER = 27
    KEY_TALK_TO_MONITOR = 29
    KEY_TALK_TO_STAGE = 30
    KEY_HOME = 31

    PREFIX = "out"

    def __init__(
        self,
        device: StreamDeck,
        session: Session,
        layer_controller: LayerController,
    ):
        super(OutputSurface, self).__init__(device, session, layer_controller)

        self._assets["icon_mic"] = os.path.join(self._assets_path, "mic.png")
        self._assets["icon_filter"] = os.path.join(self._assets_path, "filter.png")

    def init(self):
        super(OutputSurface, self).init()

        def render_channel(key: int, c: Channel) -> None:
            self._set_image(key, self._render_channel(c))

        def render_talk_to_monitor(key: int, c: Channel) -> None:
            self._set_image(key, self._render_talk_to_monitor(c))

        def render_talk_to_stage(key: int, c: Channel) -> None:
            self._set_image(key, self._render_talk_to_stage(c))

        def update_channels() -> None:
            self._fragment_renderer.reset()

            # aux/fx
            all_keys = list(range(24))

            def add(key: int, channel: Channel):
                if key in all_keys:
                    self._fragment_renderer.add_fragment(key, channel, render_channel)
                    render_channel(key, channel)
                    all_keys.remove(key)

            for key, channel in ChannelPacking.get_type_packing(self._session.aux_channels).items():
                add(key, channel)

            for key, channel in ChannelPacking.get_color_packing(self._session.fx_channels, 16).items():
                add(key + 8, channel)

            for unmapped in all_keys:
                self._set_image(unmapped, self._render_blank())

            # talk channels
            inputs = self._session.input_channels
            tracking_config = App.config.control_tracking

            channel_talk_to_monitor = inputs[tracking_config["talk_to_monitor"]]
            self._fragment_renderer.add_fragment(
                self.KEY_TALK_TO_MONITOR, channel_talk_to_monitor, render_talk_to_monitor
            )
            render_talk_to_monitor(self.KEY_TALK_TO_MONITOR, channel_talk_to_monitor)

            channel_talk_to_stage = inputs[tracking_config["talk_to_stage"]]
            self._fragment_renderer.add_fragment(self.KEY_TALK_TO_STAGE, channel_talk_to_stage, render_talk_to_stage)
            render_talk_to_stage(self.KEY_TALK_TO_STAGE, channel_talk_to_stage)

        # setup outputs now and when label/color changes occur
        update_channels()
        self._session.channel_mapping_event.append(update_channels)

        def setup_custom_selects() -> None:
            self._set_image(self.KEY_CUSTOM_AUX_MASTER, self._render_custom_aux_master_button())
            self._set_image(self.KEY_CUSTOM_FX_MASTER, self._render_custom_fx_master_button())
            self._set_image(self.KEY_CUSTOM_UTIL_MASTER, self._render_custom_util_master_button())

        self._layer_controller.selection_update_event.append(setup_custom_selects)
        setup_custom_selects()

        def update_filter() -> None:
            self._set_image(self.KEY_FILTER, self._render_filter_button())

        App.settings.filter_changed_event.append(update_filter)
        update_filter()

    def _on_key_down(self, key: int) -> None:
        super()._on_key_down(key)

        if key == self.KEY_CUSTOM_AUX_MASTER:
            self._layer_controller.select_custom_aux()
            return

        if key == self.KEY_CUSTOM_FX_MASTER:
            self._layer_controller.select_custom_fx()
            return

        if key == self.KEY_CUSTOM_UTIL_MASTER:
            self._layer_controller.select_custom_util()
            return

        if key in [self.KEY_TALK_TO_MONITOR, self.KEY_TALK_TO_STAGE]:
            self._on_key_down_long(key)
            return

        if key == self.KEY_FILTER:
            App.settings.toggle_output_filter()

    def _on_key_up(self, key: int) -> None:
        super()._on_key_up(key)

        channel = self._fragment_renderer.get_channel(key)

        if isinstance(channel, OutputChannel) and channel.is_visible:
            self._execute_throttled(lambda: self._layer_controller.select_output(channel))

    def _on_key_down_long(self, key: int) -> None:
        super()._on_key_down_long(key)

        # ignore direct action for select keys
        if key in [self.KEY_CUSTOM_AUX_MASTER, self.KEY_CUSTOM_FX_MASTER, self.KEY_HOME]:
            self._on_key_down(key)
            self._on_key_up(key)

            return

        channel = self._fragment_renderer.get_channel(key)

        if channel and channel.is_visible:
            channel.set_mute(not channel.mute)

    def _render_custom_aux_master_button(self) -> Image:
        return self._render_custom_select("AUX", self._layer_controller.custom_aux_selected)

    def _render_custom_fx_master_button(self) -> Image:
        return self._render_custom_select("FX", self._layer_controller.custom_fx_selected)

    def _render_custom_util_master_button(self) -> Image:
        return self._render_custom_select("UTIL", self._layer_controller.custom_util_selected)

    def _render_talk_to(self, channel: Channel, label: str) -> Image:
        image = PILHelper.create_scaled_image(
            self._deck,
            Image.open(self._assets["icon_mic"]),
            margins=[5, 37, 42, 0],
        )

        color = ((240, 240, 240), (100, 100, 100))[channel.mute]

        if channel.mute:
            image = ImageOps.colorize(image.convert("L"), black="black", white=color)

        draw = ImageDraw.Draw(image)

        if channel.mute:
            draw.line((10, 44, 46, 12), fill=color, width=2)

        draw.text(
            (image.width / 2, 73),
            text=label,
            font=ImageFont.truetype(self._assets["font"], 20),
            anchor="mm",
            fill=color,
        )

        draw.text(
            (57, 46),
            text=f"{channel.identifier.bank.short_name} {channel.identifier.canonical_index + 1}",
            font=ImageFont.truetype(self._assets["font"], 12),
            anchor="lb",
            fill=((100, 100, 100), (50, 50, 50))[channel.selected],
        )

        return image

    def _render_talk_to_monitor(self, channel: Channel) -> Image:
        return self._render_talk_to(channel, "MON.")

    def _render_talk_to_stage(self, channel: Channel) -> Image:
        return self._render_talk_to(channel, "STAGE")

    def _render_filter_button(self) -> Image:
        image = PILHelper.create_scaled_image(
            self._deck,
            Image.open(self._assets["icon_filter"]),
            margins=[26, 24, 23, 24],
        )

        if App.settings.output_filter:
            active_color = (255, 0, 50)
            image = ImageOps.colorize(image.convert("L"), black="black", white=active_color)

            draw = ImageDraw.Draw(image)
            draw.ellipse(
                (8, 8, image.width - 8, image.height - 8),
                outline=active_color,
                width=5,
            )

        return image
