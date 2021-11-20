from typing import Optional

from common.event import Event
from dlive.entity import Channel, InputChannel, OutputChannel
from state.session import Session


class LayerController:
    _MODE_DEFAULT = 0
    _MODE_SENDS_ON_FADER = 1
    _MODE_S_DCA = 2
    _MODE_OUTPUTS = 3

    def __init__(self, session: Session):
        # todo -> config
        self._scenes = {
            "virtual_left_bank_start": 489,
            "virtual_left_bank_end": 494,
            "virtual_right": 495,
            "default": 199,
            "virtual": 200,
            "output_start": 210,
        }

        self._input_bank: Optional[int] = None

        self._session = session
        self._mode = -1
        self._s_dca_active = False

        self._session.scene_update_event.append(self._on_scene_change)
        self.selection_update_event = Event()

    @property
    def default_selected(self) -> bool:
        return self._mode == self._MODE_DEFAULT

    @property
    def s_dca_selected(self) -> bool:
        return self._mode == self._MODE_S_DCA

    @property
    def s_dca_active(self) -> bool:
        return self._s_dca_active

    def select_default(self):
        self._select_mode(self._MODE_DEFAULT)
        self._select_exclusively(None)
        self._session.load_scene(self._scenes["default"])

    def select_output(self, channel: OutputChannel) -> None:
        self._select_mode(self._MODE_OUTPUTS)

        if channel.selected:
            self.select_default()
            return

        self._select_exclusively(channel)

        mix_output_scene = self._scenes["output_start"] + channel.identifier.canonical_index
        self._session.load_scene(mix_output_scene)

    def select_input(self, channel: InputChannel) -> None:
        if self._mode == self._MODE_S_DCA:
            self._toggle_s_dca_channel(channel)
            return

        if channel.selected:
            self.select_default()
            return

        self._sends_on_fader(channel)

    def toggle_s_dca_mode(self) -> None:
        if self._mode == self._MODE_S_DCA:
            self.select_default()
            return

        self._select_exclusively(None)

        if not self._s_dca_active:
            for channel in self._session.input_channels:
                channel.backup_sends()

            self._s_dca_active = True

        self._select_mode(self._MODE_S_DCA)

        for channel in self._session.virtual_channels:
            channel.tie_to_zero()

        self._session.load_scene(self._scenes["virtual"])

    def clear_s_dca(self) -> None:
        if not self._s_dca_active:
            return

        for channel in filter(lambda c: c.affected_by_s_dca, self._session.input_channels):
            channel.restore_sends()

        for channel in self._session.virtual_channels:
            channel.tie_to_zero()

        self._s_dca_active = False

        if self._mode == self._MODE_S_DCA:
            self.select_default()
        else:
            self.selection_update_event()

    def _on_scene_change(self, scene: int):
        if scene == self._scenes["virtual_right"]:
            # ignore virtual channel right loads; they are issued when
            # selecting a bank on the left side
            return

        if self._scenes["virtual_left_bank_start"] <= scene <= self._scenes["virtual_left_bank_end"]:
            self._input_bank = scene - self._scenes["virtual_left_bank_start"]

            # load scene for right side
            self._session.load_scene(self._scenes["virtual_right"])

        """Handle manual scene changes and try to find a suitable mode."""
        if scene == self._scenes["default"] and self._mode != self._MODE_DEFAULT:
            self.select_default()
            return

        scene_offset = scene - self._scenes["output_start"]
        if 0 <= scene_offset < len(self._session.output_channels):
            channel = self._session.output_channels[scene_offset]

            if not channel.selected:
                self.select_output(channel)

    def _sends_on_fader(self, channel: InputChannel) -> None:
        self._select_mode(self._MODE_SENDS_ON_FADER)
        self._select_exclusively(channel)

        # patch virtual channels
        virtual_channels = self._session.virtual_channels
        index = 0
        max_index = len(virtual_channels) - 1

        for output_channel in self._session.output_channels:
            if not output_channel.is_visible:
                continue

            virtual_channels[index].bind_send(channel, output_channel)
            index += 1

            if index > max_index:
                break

        for unused_index in range(index, max_index + 1):
            virtual_channels[unused_index].tie_to_zero()

        self._session.load_scene(self._scenes["virtual"])

    def _toggle_s_dca_channel(self, channel: InputChannel):
        channel.select(not channel.selected)
        affected_channels = list(filter(lambda c: c.selected, self._session.input_channels))

        # patch virtual channels
        virtual_channels = self._session.virtual_channels
        index = 0
        max_index = len(virtual_channels) - 1

        for output_channel in self._session.output_channels:
            if not output_channel.is_visible:
                continue

            virtual_channels[index].bind_s_dca(affected_channels, output_channel)
            index += 1

            if index > max_index:
                break

        for unused_index in range(index, max_index + 1):
            virtual_channels[unused_index].tie_to_zero()

        self._session.load_scene(self._scenes["virtual"])

    def _select_exclusively(self, selected: Optional[Channel]) -> None:
        for channel in self._session.channels:
            channel.select(channel == selected)

    def _select_mode(self, mode: int):
        if self._mode != mode:
            self._mode = mode
            self.selection_update_event()
