from PIL import ImageDraw

from dlive.entity import Channel, InputChannel
from streamdeck.surface.surface import Surface
from streamdeck.util import ChannelPacking


class InputSurface(Surface):
    def init(self):
        super(InputSurface, self).init()

        def render_channel(key: int, c: Channel) -> None:
            self._set_image(key, self._render_channel(c))

        def update_inputs() -> None:
            self._fragment_renderer.reset()
            all_keys = list(range(32))
            packing = ChannelPacking.get_color_packing(self._session.input_channels)

            for key, channel in packing.items():
                if key in all_keys:
                    self._fragment_renderer.add_fragment(key, channel, render_channel)
                    render_channel(key, channel)
                    all_keys.remove(key)

            for unmapped in all_keys:
                self._set_image(unmapped, self._render_blank())

        # setup inputs now and when label/color changes occur
        self._session.channel_mapping_event.append(update_inputs)
        update_inputs()

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
