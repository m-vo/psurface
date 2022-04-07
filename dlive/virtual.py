from enum import Enum, auto
from threading import Lock
from time import sleep
from typing import Set, List, Optional, Callable

from app import App
from common.event import AsyncEvent
from dlive.api import DLive
from dlive.entity import Scene, ChannelIdentifier, Label, Color, Level


class LayerMode(Enum):
    MIXING = auto()
    SENDS_ON_FADER = auto()
    OUTPUTS = auto()
    CUSTOM_AUX = auto()
    CUSTOM_FX = auto()
    CUSTOM_UTIL = auto()


class LayerController:
    SENDS_TO_AUX = False
    SENDS_TO_FX = True

    def __init__(self, dlive: DLive) -> None:
        self._dlive = dlive

        # state (bank, mode, last selected channels, filter, …)
        self._bank: int = 0
        self._mode: LayerMode = LayerMode.MIXING
        self._last_output_channel: ChannelIdentifier = dlive.output_channels[0]
        self._last_input_channel: ChannelIdentifier = dlive.input_channels[0]
        self._channel_filter: bool = False
        self._sends_target: bool = self.SENDS_TO_AUX
        self._selected_channel: Optional[ChannelIdentifier] = None

        self._configure_lock = Lock()
        self._reconfigure_callback: Callable = lambda: None

        # init virtual channel objects
        self._virtual_channels: List[VirtualChannel] = list(
            map(lambda c: VirtualChannel(dlive, c), dlive.virtual_channels)
        )

        # scene settings
        scene_config = App.config.control_scenes
        self._scene_mixing_start = Scene(scene_config["mixing_start"])
        self._scene_virtual_left_start = Scene(scene_config["virtual_left_start"])
        self._scene_virtual_right = Scene(scene_config["virtual_right"])
        self._scene_sends = Scene(scene_config["sends"])
        self._scene_custom_aux = Scene(scene_config["custom_aux"])
        self._scene_custom_fx = Scene(scene_config["custom_fx"])
        self._scene_custom_util = Scene(scene_config["custom_util"])

        # events
        dlive.on_update_scene.append(self._on_scene_change)
        self.on_selection_changed = AsyncEvent("layer_controller.on_selection_changed")
        self.on_mode_changed = AsyncEvent("layer_controller.on_mode_changed")
        self.on_modifier_changed = AsyncEvent("layer_controller.on_modifier_changed")

    def select_mixing_mode(self):
        if self._channel_filter:
            self.toggle_channel_filter()

        self._call_scene_or_handler(self._scene_mixing_start.with_offset(self._bank))

    def select_output(self, output_channel: ChannelIdentifier) -> None:
        with self._configure_lock:
            self._last_output_channel = output_channel

        # load virtual right first, otherwise there is a flaky issue where the
        # dLive director does not show the correct state for the bank indicator
        # (LED not lit even if matching scene was recalled)
        if self._mode != LayerMode.OUTPUTS and self._dlive.get_scene() != self._scene_virtual_right:
            self._on_scene_change(self._scene_virtual_right)

        self._call_scene_or_handler(self._scene_virtual_left_start.with_offset(self._bank))

    def select_input(self, input_channel: ChannelIdentifier) -> None:
        with self._configure_lock:
            self._last_input_channel = input_channel

        self._call_scene_or_handler(self._scene_sends)

    def select_custom_aux_mode(self) -> None:
        self._call_scene_or_handler(self._scene_custom_aux)

    def select_custom_fx_mode(self) -> None:
        self._call_scene_or_handler(self._scene_custom_fx)

    def select_custom_util_mode(self) -> None:
        self._call_scene_or_handler(self._scene_custom_util)

    def _call_scene_or_handler(self, scene: Scene):
        if scene == self._dlive.get_scene():
            self._on_scene_change(scene)
        else:
            self._dlive.change_scene(scene)

    def toggle_channel_filter(self) -> None:
        new = self._channel_filter = not self._channel_filter
        self._reconfigure_callback()
        self.on_modifier_changed("filter", new)
        App.notify(f"Channel filter -> {('Off', 'On')[new]}")

    def toggle_sends_target(self) -> None:
        new = self._sends_target = not self._sends_target
        self._reconfigure_callback()
        self.on_modifier_changed("sends_target", new)
        App.notify(f"Sends target -> {('Aux', 'FX')[new == self.SENDS_TO_FX]}")

    def is_selected(self, channel: ChannelIdentifier) -> bool:
        return self._selected_channel == channel

    def get_mode(self) -> LayerMode:
        return self._mode

    def _on_scene_change(self, scene: Scene):
        def select_mode(mode: LayerMode):
            if self._mode != mode:
                self._mode = mode
                self.on_mode_changed(mode)

        def select_channel(channel: Optional[ChannelIdentifier]):
            if self._selected_channel != channel:
                self._selected_channel = channel
                self.on_selection_changed(channel)

        with self._configure_lock:
            # mixing
            if self._scene_mixing_start <= scene < self._scene_mixing_start + 6:
                select_mode(LayerMode.MIXING)
                self._bank = scene - self._scene_mixing_start
                App.notify(f"Mixing | Bank {self._bank + 1}")
                select_channel(None)
                self._dlive.change_feedback_source(None)

            # outputs
            elif scene == self._scene_virtual_right:
                # ignore
                pass

            elif self._scene_virtual_left_start <= scene < self._scene_virtual_left_start + 6:
                select_mode(LayerMode.OUTPUTS)
                self._bank = scene - self._scene_virtual_left_start
                self._configure_outputs(self._last_output_channel)
                App.notify(f"{self._last_output_channel.short_label()} | Bank {self._bank + 1}")
                select_channel(self._last_output_channel)

            # sends
            elif scene == self._scene_sends:
                select_mode(LayerMode.SENDS_ON_FADER)
                App.notify(f"SendsOnFader | {self._last_input_channel.short_label()}")
                select_channel(self._last_input_channel)
                self._configure_sends_on_fader(self._last_input_channel)

            # custom
            elif scene == self._scene_custom_aux:
                select_mode(LayerMode.CUSTOM_AUX)
                App.notify(f"Custom | AUX")
                select_channel(None)
                self._dlive.change_feedback_source(None)

            elif scene == self._scene_custom_fx:
                select_mode(LayerMode.CUSTOM_FX)
                App.settings.set_status(f"Custom | FX")
                select_channel(None)
                self._dlive.change_feedback_source(None)

            elif scene == self._scene_custom_util:
                select_mode(LayerMode.CUSTOM_UTIL)
                App.notify(f"Custom | UTIL")
                select_channel(None)
                self._dlive.change_feedback_source(None)

    def _configure_outputs(self, output_channel: ChannelIdentifier) -> None:
        self._reconfigure_callback = lambda: self._configure_outputs(output_channel)

        channels = self._dlive.input_channels
        max_index = len(channels) - 1

        if filtered := self._channel_filter:
            channel_from = 0
            channel_to = max_index
        else:
            channel_from = min(self._bank * 16, max_index)
            channel_to = min(channel_from + 14, max_index)

        def _show_channel(ch: ChannelIdentifier) -> bool:
            return self._dlive.get_label(ch).has_name and (
                not filtered or self._dlive.get_send_level(ch, output_channel) != Level.VALUE_OFF
            )

        # 0..14: send levels
        v_index = 0
        for index in range(channel_from, channel_to):
            if _show_channel(channel := channels[index]):
                self._virtual_channels[v_index].bind_send(channel, output_channel, True)
                v_index += 1

            if v_index == 15:
                break

        for unused_index in range(v_index, 15):
            self._virtual_channels[unused_index].tie_to_zero()

        # 15: output master
        self._dlive.change_feedback_source(output_channel)
        self._virtual_channels[15].bind_master(output_channel)

    def _configure_sends_on_fader(self, input_channel: ChannelIdentifier) -> None:
        self._reconfigure_callback = lambda: self._configure_sends_on_fader(input_channel)

        channels = ([*self._dlive.fx_channels, *self._dlive.external_fx_channels], self._dlive.aux_channels)[
            self._sends_target == self.SENDS_TO_AUX
        ]
        filtered = self._channel_filter

        def _show_channel(ch: ChannelIdentifier) -> bool:
            return self._dlive.get_label(ch).has_name and (
                not filtered or self._dlive.get_send_level(input_channel, ch) != Level.VALUE_OFF
            )

        # 0..15: send levels
        v_index = 0
        for index in range(len(channels)):
            if _show_channel(channel := channels[index]):
                self._virtual_channels[v_index].bind_send(input_channel, channel)
                v_index += 1

            if v_index == 16:
                break

        for unused_index in range(v_index, 15):
            self._virtual_channels[unused_index].tie_to_zero()

        self._dlive.change_feedback_source(None)


class VirtualChannel:
    _MODE_NONE = -1
    _MODE_TIE_TO_ZERO = 0
    _MODE_TRACK_SEND_LEVEL = 1
    _MODE_TRACK_MASTER_LEVEL = 2

    def __init__(self, dlive: DLive, channel: ChannelIdentifier) -> None:
        self._dlive = dlive
        self._channel = channel

        self._mode_lock = Lock()
        self._mode = self._MODE_NONE
        self._base_channel: Optional[ChannelIdentifier] = None
        self._to_channel: Optional[ChannelIdentifier] = None

        self._dlive.on_update_level.append(self._on_level_changed)
        self._dlive.on_update_mute.append(self._on_mute_changed)

    def _on_level_changed(self, channel: ChannelIdentifier, level: Level) -> None:
        if channel != self._channel or self._mode == self._MODE_NONE:
            return

        with self._mode_lock:
            mode = self._mode
            base_channel = self._base_channel
            to_channel = self._to_channel

        if mode == self._MODE_TIE_TO_ZERO:
            if level > 0:
                self._dlive.change_level(self._channel, Level.VALUE_OFF)
            return

        if mode == self._MODE_TRACK_SEND_LEVEL:
            self._dlive.change_send_level(base_channel, to_channel, level)
            return

        if mode == self._MODE_TRACK_MASTER_LEVEL:
            self._dlive.change_level(base_channel, level)

    def _on_mute_changed(self, channel: ChannelIdentifier, mute: bool) -> None:
        if channel != self._channel or self._mode == self._MODE_NONE:
            return

        with self._mode_lock:
            mode = self._mode
            base_channel = self._base_channel

        if mode in [self._MODE_TRACK_SEND_LEVEL, self._MODE_TIE_TO_ZERO]:
            if mute:
                self._dlive.change_mute(self._channel, False)
            return

        if mode == self._MODE_TRACK_MASTER_LEVEL:
            self._dlive.change_mute(base_channel, mute)

    def tie_to_zero(self) -> None:
        """
        Make the fader stick to the -inf/bottom position.
        """
        self._dlive.change_label(self._channel, Label())
        self._dlive.change_color(self._channel, Color.OFF)
        self._dlive.change_mute(self._channel, False)
        self._dlive.change_level(self._channel, Level.VALUE_OFF)

        with self._mode_lock:
            self._mode = self._MODE_TIE_TO_ZERO
            self._base_channel = None
            self._to_channel = None

    def bind_send(
        self, base_channel: ChannelIdentifier, to_channel: ChannelIdentifier, label_from_base: bool = False
    ) -> None:
        """
        Set the send-level (base_channel -> to_channel) based on the virtual channel's level.
        """
        if label_from_base:
            self._dlive.change_label(self._channel, self._dlive.get_label(base_channel).with_bind_send_prefix())
            self._dlive.change_color(self._channel, self._dlive.get_color(base_channel))
        else:
            self._dlive.change_label(self._channel, self._dlive.get_label(to_channel).with_bind_send_prefix())
            self._dlive.change_color(self._channel, self._dlive.get_color(to_channel))

        self._dlive.change_mute(self._channel, False)
        self._dlive.change_level(self._channel, self._dlive.get_send_level(base_channel, to_channel))

        with self._mode_lock:
            self._base_channel = base_channel
            self._to_channel = to_channel
            self._mode = self._MODE_TRACK_SEND_LEVEL

    def bind_master(self, base_channel: ChannelIdentifier) -> None:
        """
        Set the level and mute status of the base_channel based on the virtual channel's level and mute status.
        """
        self._dlive.change_label(self._channel, self._dlive.get_label(base_channel).with_bind_master_prefix())
        self._dlive.change_color(self._channel, self._dlive.get_color(base_channel))
        self._dlive.change_mute(self._channel, self._dlive.get_mute(base_channel))
        self._dlive.change_level(self._channel, self._dlive.get_level(base_channel))

        with self._mode_lock:
            self._base_channel = base_channel
            self._to_channel = None
            self._mode = self._MODE_TRACK_MASTER_LEVEL

    def unbind(self) -> None:
        """
        Release the binding.
        """
        self._dlive.change_label(self._channel, Label("[V-Ch]"))
        self._dlive.change_color(self._channel, Color.OFF)
        self._dlive.change_mute(self._channel, True)
        self._dlive.change_level(self._channel, Level.VALUE_OFF)

        with self._mode_lock:
            self._base_channel = None
            self._to_channel = None
            self._mode = self._MODE_NONE
