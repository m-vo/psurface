from typing import List, Optional, Set

from app import App
from common.event import Event
from dlive.entity import Channel, Color, InputChannel, Level, OutputChannel
from state.session import Session
from streamdeck.util import ChannelPacking


class LayerController:
    _MODE_MIXING = 0
    _MODE_SENDS_ON_FADER = 1
    _MODE_S_DCA = 2
    _MODE_OUTPUTS = 3
    _MODE_CUSTOM_AUX = 4
    _MODE_CUSTOM_FX = 5
    _MODE_CUSTOM_UTIL = 6

    def __init__(self, session: Session):
        self.selection_update_event = Event()

        self._session = session

        scene_config = App.config.control_scenes
        self._max_input_index = App.config.control_tracking["number_of_inputs"] - 1
        self._max_fx_return_index = App.config.control_tracking["number_of_fx_returns"] - 1

        self._scene_mixing_start = scene_config["mixing_start"]
        self._scene_virtual_left_start = scene_config["virtual_left_start"]
        self._scene_virtual_right = scene_config["virtual_right"]
        self._scene_sends = scene_config["sends"]
        self._scene_custom_aux = scene_config["custom_aux"]
        self._scene_custom_fx = scene_config["custom_fx"]
        self._scene_custom_util = scene_config["custom_util"]

        # global bank, mode and last selected channels
        self._bank: int = 0
        self._mode: int = -1
        self._ignore_next_recall: bool = False
        self._last_output_channel: OutputChannel = session.output_channels[0]
        self._last_input_channel: InputChannel = session.input_channels[0]

        # S-DCA state handling
        self._s_dca_affected_channels: Set[int] = set()
        self._s_dca_enabled = False

        def track_affected_channels(channel: InputChannel):
            hash_identifier = channel.identifier.__hash__()

            if channel.affected_by_s_dca:
                if hash_identifier not in self._s_dca_affected_channels:
                    self._s_dca_affected_channels.add(hash_identifier)
                    self.selection_update_event()
            else:
                if hash_identifier in self._s_dca_affected_channels:
                    self._s_dca_affected_channels.remove(hash_identifier)
                    self.selection_update_event()

        for input_channel in session.input_channels:
            input_channel.s_dca_changed_event.append(track_affected_channels)

        session.scene_update_event.append(self._on_scene_change)

        # update view when filter state changes
        def update_output_view():
            if self._mode == self._MODE_OUTPUTS:
                self.select_output(self._last_output_channel)

        App.settings.filter_changed_event.append(update_output_view)

    @property
    def mixing_selected(self) -> bool:
        return self._mode == self._MODE_MIXING

    @property
    def s_dca_selected(self) -> bool:
        return self._mode == self._MODE_S_DCA

    @property
    def custom_aux_selected(self) -> bool:
        return self._mode == self._MODE_CUSTOM_AUX

    @property
    def custom_fx_selected(self) -> bool:
        return self._mode == self._MODE_CUSTOM_FX

    @property
    def custom_util_selected(self) -> bool:
        return self._mode == self._MODE_CUSTOM_UTIL

    @property
    def s_dca_affected_channels(self) -> int:
        return len(self._s_dca_affected_channels)

    def select_mixing(self):
        # There is a bug in the 1.9 firmware that prevents the bank indicator
        # of the mixing scene to be lit even though a matching scene is loaded.
        # It only happens for certain transitions (output -> input -!-> mixing),
        # so we work around it by calling another scene first and ignoring
        # their action.
        self._ignore_next_recall = True
        self._session.load_scene(self._scene_virtual_left_start)

        self._session.load_scene(self._scene_mixing_start + self._bank)

    def select_output(self, output_channel: OutputChannel) -> None:
        self._last_output_channel = output_channel
        self._session.load_scene(self._scene_virtual_left_start + self._bank)

    def select_input(self, input_channel: InputChannel) -> None:
        if not self._s_dca_enabled:
            self._last_input_channel = input_channel
            self._session.load_scene(self._scene_sends)

            return

        input_channel.select(not input_channel.selected)
        self._configure_s_dca()

    def enable_s_dca_mode(self) -> None:
        self._s_dca_enabled = True
        self._session.load_scene(self._scene_sends)

    def restore_s_dca_values(self) -> None:
        for input_channel in self._session.input_channels:
            identifier_hash = input_channel.identifier.__hash__()

            if identifier_hash in self._s_dca_affected_channels:
                input_channel.restore_sends()

        self._select_exclusively(None)
        self._configure_s_dca()

    def accept_s_dca_values(self) -> None:
        for input_channel in self._session.input_channels:
            identifier_hash = input_channel.identifier.__hash__()

            if identifier_hash in self._s_dca_affected_channels:
                input_channel.drop_sends_backup()

        self._select_exclusively(None)
        self._configure_s_dca()

    def select_custom_aux(self) -> None:
        self._session.load_scene(self._scene_custom_aux)

    def select_custom_fx(self) -> None:
        self._session.load_scene(self._scene_custom_fx)

    def select_custom_util(self) -> None:
        self._session.load_scene(self._scene_custom_util)

    def _on_scene_change(self, scene: int) -> None:
        # todo: this is an ugly hack, that we can hopefully remove anytime in the future
        #       see "select_mixing()"
        if self._ignore_next_recall:
            self._ignore_next_recall = False
            return

        trigger_selection_update = False

        def select_mode(mode: int):
            if self._mode != mode:
                self._mode = mode

                nonlocal trigger_selection_update
                trigger_selection_update = True

        if self._scene_mixing_start <= scene < self._scene_mixing_start + 6:
            select_mode(self._MODE_MIXING)
            self._bank = scene - self._scene_mixing_start
            self._s_dca_enabled = False

            App.settings.set_status(f"Mixing | Bank {self._bank + 1}")
            self._select_exclusively(None)

            for virtual_channel in self._session.virtual_channels:
                virtual_channel.unbind()

            self._session.route_feedback_to_output(None)

        elif self._scene_virtual_left_start <= scene < self._scene_virtual_left_start + 6:
            select_mode(self._MODE_OUTPUTS)
            self._bank = scene - self._scene_virtual_left_start
            self._s_dca_enabled = False
            output_channel = self._last_output_channel

            App.settings.set_status(f"{output_channel.identifier.short_label()} | Bank {self._bank + 1}")
            self._select_exclusively(output_channel)
            self._configure_outputs(output_channel)

            # load scene for right side
            self._session.load_scene(self._scene_virtual_right)

        elif scene == self._scene_sends:
            if self._s_dca_enabled:
                select_mode(self._MODE_S_DCA)

                App.settings.set_status(f"S-DCA")
                self._select_exclusively(None)
                self._configure_s_dca()

            else:
                select_mode(self._MODE_SENDS_ON_FADER)
                input_channel = self._last_input_channel

                App.settings.set_status(f"SendsOnFader | {input_channel.identifier.short_label()}")
                self._select_exclusively(input_channel)
                self._configure_sends_on_fader(input_channel)

        elif scene == self._scene_custom_aux:
            select_mode(self._MODE_CUSTOM_AUX)
            self._s_dca_enabled = False

            App.settings.set_status(f"Custom | AUX")
            self._select_exclusively(None)

            self._session.route_feedback_to_output(None)

        elif scene == self._scene_custom_fx:
            select_mode(self._MODE_CUSTOM_FX)
            self._s_dca_enabled = False

            App.settings.set_status(f"Custom | FX")
            self._select_exclusively(None)

            self._session.route_feedback_to_output(None)

        elif scene == self._scene_custom_util:
            select_mode(self._MODE_CUSTOM_UTIL)
            self._s_dca_enabled = False

            App.settings.set_status(f"Custom | UTIL")
            self._select_exclusively(None)

            self._session.route_feedback_to_output(None)

        if trigger_selection_update:
            self.selection_update_event()

    def _configure_outputs(self, output_channel: OutputChannel) -> None:
        """Patch virtual channels for outputs configuration."""
        virtual_channels = self._session.virtual_channels

        index = 0

        def bind_sends(channels: List[InputChannel], index_from: int, index_to: int):
            nonlocal index

            for channel_index in range(index_from, index_to + 1):
                channel = channels[channel_index]

                if not channel.is_visible or not virtual_channels[index].bind_send(channel, output_channel, True):
                    virtual_channels[index].tie_to_zero()

                index += 1

        if App.settings.output_filter:
            channels: List[InputChannel] = [*self._session.input_channels, *self._session.fx_returns]

            # filtered view
            for channel in channels:
                if not channel.is_visible or channel.get_send_level(output_channel) == Level.VALUE_OFF:
                    continue

                if virtual_channels[index].bind_send(channel, output_channel, True):
                    index += 1

                    if index == 15:
                        break

        else:
            # inputs from banks
            channel_region_from = min(self._bank * 16, self._max_input_index)
            channel_region_to = min(channel_region_from + 14, self._max_input_index)

            bind_sends(self._session.input_channels, channel_region_from, channel_region_to)

        # unused
        for unused_index in range(index, 15):
            virtual_channels[unused_index].tie_to_zero()

        # output master
        self._session.route_feedback_to_output(output_channel)
        virtual_channels[15].bind_master(output_channel)

    def _configure_sends_on_fader(self, input_channel: InputChannel) -> None:
        """Patch virtual channels for sends on fader configuration."""
        virtual_channels = self._session.virtual_channels
        all_keys = list(range(16))

        for index, output_channel in ChannelPacking.get_out_split_packing(
            self._session.aux_channels, self._session.fx_channels
        ).items():
            if index in all_keys and virtual_channels[index].bind_send(input_channel, output_channel):
                all_keys.remove(index)

        for unused_index in all_keys:
            virtual_channels[unused_index].tie_to_zero()

        self._session.route_feedback_to_output(None)

        return

    def _configure_s_dca(self) -> None:
        """Patch virtual channels for S-DCA configuration."""
        affected_channels = list(filter(lambda c: c.selected, self._session.input_channels))

        if len(affected_channels) == 0:
            for virtual_channel in self._session.virtual_channels:
                virtual_channel.tie_to_zero()

            return

        virtual_channels = self._session.virtual_channels
        index = 0
        max_index = 15

        for fx_channel in self._session.fx_channels:
            if not fx_channel.is_visible:
                continue

            if not virtual_channels[index].bind_s_dca(affected_channels, fx_channel):
                virtual_channels[index].tie_to_zero()

            index += 1

            if index > max_index:
                break

        for unused_index in range(index, max_index + 1):
            virtual_channels[unused_index].tie_to_zero()

        self._session.route_feedback_to_output(None)

        return

    def _select_exclusively(self, selected: Optional[Channel]) -> None:
        for channel in self._session.channels:
            channel.select(channel == selected)
