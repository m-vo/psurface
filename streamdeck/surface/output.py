from PIL.Image import Image

from dlive.entity import Channel, OutputChannel
from streamdeck.surface.surface import Surface
from streamdeck.util import ChannelPacking


class OutputSurface(Surface):
    KEY_HOME = 31
    KEY_CUSTOM_AUX_MASTER = 24
    KEY_CUSTOM_FX_MASTER = 25

    def init(self):
        super(OutputSurface, self).init()

        def render_channel(key: int, c: Channel) -> None:
            self._set_image(key, self._render_channel(c))

        def update_outputs() -> None:
            self._fragment_renderer.reset()
            all_keys = list(range(16))

            def add(key: int, channel: Channel):
                if key in all_keys:
                    self._fragment_renderer.add_fragment(key, channel, render_channel)
                    render_channel(key, channel)
                    all_keys.remove(key)

            for key, channel in ChannelPacking.get_type_packing(self._session.aux_channels).items():
                add(key, channel)

            for key, channel in ChannelPacking.get_type_packing(self._session.fx_channels).items():
                add(key + 8, channel)

            for unmapped in all_keys:
                self._set_image(unmapped, self._render_blank())

        # setup outputs now and when label/color changes occur
        update_outputs()
        self._session.channel_mapping_event.append(update_outputs)

        def setup_custom_selects() -> None:
            self._set_image(self.KEY_CUSTOM_AUX_MASTER, self._render_custom_aux_master_button())
            self._set_image(self.KEY_CUSTOM_FX_MASTER, self._render_custom_fx_master_button())

        self._layer_controller.selection_update_event.append(setup_custom_selects)
        setup_custom_selects()

    def _on_key_up(self, key: int) -> None:
        super()._on_key_up(key)

        if key == self.KEY_CUSTOM_AUX_MASTER:
            self._layer_controller.select_custom_aux()
            return

        if key == self.KEY_CUSTOM_FX_MASTER:
            self._layer_controller.select_custom_fx()
            return

        channel = self._fragment_renderer.get_channel(key)

        if isinstance(channel, OutputChannel) and channel.is_visible:
            self._layer_controller.select_output(channel)

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
