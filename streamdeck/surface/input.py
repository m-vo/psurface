from StreamDeck.Devices import StreamDeck

from app import App
from dlive.api import DLive
from dlive.virtual import LayerController
from streamdeck.surface.surface import Surface
from streamdeck.util import ChannelRenderer


class InputSurface(Surface):
    def __init__(self, device: StreamDeck, dlive: DLive, layer_controller: LayerController) -> None:
        super().__init__(device, dlive, layer_controller)

        self._renderer = ChannelRenderer(dlive, layer_controller)

        for channel in dlive.input_channels:
            self._renderer.add_channel(
                channel,
                (lambda _ch: lambda key: self._set_image(key, self._render_channel(_ch)))(channel),
            )

        self._renderer.enable_color_group_strategy(
            App.config.input_colors, lambda key: self._set_image(key, self._blank_image)
        )

    def _on_key_up(self, key: int) -> None:
        super()._on_key_up(key)

        if (channel := self._renderer.get_channel(key)) is not None:
            self._layer_controller.select_input(channel)

    def _on_key_down_long(self, key: int) -> None:
        super()._on_key_down_long(key)

        if (channel := self._renderer.get_channel(key)) is not None:
            self._dlive.change_mute(channel, not self._dlive.get_mute(channel))
