import typing

from apscheduler.schedulers import SchedulerNotRunningError
from apscheduler.schedulers.background import BackgroundScheduler

from common.event import Event
from common.state import (
    Channel,
    InputChannel,
    OutputChannel,
    Bank,
    Level,
    Color,
    ChannelIdentifier,
    VirtualChannel,
)
from dlive.encoding import Decoder, Encoder


class Session:
    def __init__(self, decoder: Decoder, encoder: Encoder):
        self._decoder = decoder
        self._encoder = encoder

        self._channels: typing.Dict[int, Channel] = {}
        self._inputs: typing.Dict[int, InputChannel] = {}
        self._aux: typing.Dict[int, OutputChannel] = {}
        self._fx: typing.Dict[int, OutputChannel] = {}
        self._virtual: typing.Dict[int, VirtualChannel] = {}
        self._scene: int = -1

        # aux channels
        for index in range(8):
            channel = OutputChannel(ChannelIdentifier(Bank.MONO_AUX, index))
            self._aux[index] = channel
            self._channels[channel.identifier.__hash__()] = channel

        # fx channels
        for index in range(8):
            channel = OutputChannel(ChannelIdentifier(Bank.MONO_FX_SEND, index))
            self._fx[index] = channel
            self._channels[channel.identifier.__hash__()] = channel

        # virtual channels
        for index in range(8, 16):
            channel = VirtualChannel(ChannelIdentifier(Bank.MONO_AUX, index))
            self._virtual[index] = channel
            self._channels[channel.identifier.__hash__()] = channel

        # inputs
        for index in range(96):
            channel = InputChannel(ChannelIdentifier(Bank.INPUT, index))

            # initialize sends for all aux and fx channels
            for to_channel in [
                *self._aux.values(),
                *self._fx.values(),
                *self._virtual.values(),
            ]:
                channel.set_send_level(to_channel)

            self._inputs[index] = channel
            self._channels[channel.identifier.__hash__()] = channel

        # tracking
        self.channel_update_event: Event = Event()
        self.scene_update_event: Event = Event()
        self._tracking: bool = False
        self._scheduler = BackgroundScheduler()

    def __del__(self):
        try:
            self._scheduler.shutdown(wait=False)
        except SchedulerNotRunningError:
            pass

    @property
    def input_channels(self) -> typing.List[InputChannel]:
        return list(self._inputs.values())

    @property
    def aux_channels(self) -> typing.List[OutputChannel]:
        return list(self._aux.values())

    @property
    def fx_channels(self) -> typing.List[OutputChannel]:
        return list(self._fx.values())

    @property
    def output_channels(self) -> typing.List[OutputChannel]:
        return [*self._aux.values(), *self._fx.values()]

    @property
    def virtual_channels(self) -> typing.List[VirtualChannel]:
        return list(self._virtual.values())

    @property
    def channels(self) -> typing.List[Channel]:
        return list(self._channels.values())

    def track_changes(self) -> None:
        if self._tracking:
            raise RuntimeError("Tracking is already enabled")

        self._tracking = True

        # follow changes announced by mixrack
        self._decoder.label_changed_event.append(self._on_update_label)
        self._decoder.color_changed_event.append(self._on_update_color)
        self._decoder.mute_changed_event.append(self._on_update_mute)
        self._decoder.level_changed_event.append(self._on_update_level)
        self._decoder.send_level_changed_event.append(self._on_update_send_level)
        self._decoder.scene_changed_event.append(self._on_recall_scene)

        # initialize values
        for channel in self._channels.values():
            self._encoder.request_label(channel)
            self._encoder.request_color(channel)
            self._encoder.request_mute(channel)
            self._encoder.request_level(channel)

            if isinstance(channel, InputChannel):
                for send_channel in channel.send_channels:
                    self._encoder.request_send_level(channel, send_channel)

        # propagate changes made to channels
        for channel in self._channels.values():
            channel.label_changed_event.append(self._encoder.label)
            channel.color_changed_event.append(self._encoder.color)
            channel.mute_changed_event.append(self._encoder.mute)
            channel.level_changed_event.append(self._encoder.level)
            channel.select_changed_event.append(self.channel_update_event)

        # track S-DCA changes
        for channel in self._inputs.values():
            channel.send_level_changed_event.append(self._encoder.send_level)
            channel.s_dca_changed_event.append(self.channel_update_event)

        # setup virtual channels
        for channel in self._virtual.values():
            channel.reset()
            channel.request_send_level_event.append(self._encoder.request_send_level)
            self._decoder.send_level_changed_event.append(channel.set_send_level)

        # poll color attribute every few seconds, as it is currently not
        # transmitted on change
        def poll_updates():
            for c in self._channels.values():
                if not isinstance(c, VirtualChannel):
                    self._encoder.request_color(c)

        self._scheduler.add_job(
            poll_updates,
            "interval",
            seconds=3,
            id="poll_session_updates",
            replace_existing=True,
        )
        # todo
        # self._scheduler.start()

    def load_scene(self, scene: int):
        self._encoder.recall_scene(scene)

    def _on_update_label(self, identifier: ChannelIdentifier, label: str) -> None:
        if channel := self._lookup_channel(identifier):
            if channel.set_label(label, False):
                self.channel_update_event(channel)

    def _on_update_color(self, identifier: ChannelIdentifier, color: Color) -> None:
        if channel := self._lookup_channel(identifier):
            if channel.set_color(color, False):
                self.channel_update_event(channel)

    def _on_update_mute(self, identifier: ChannelIdentifier, enabled: bool) -> None:
        if channel := self._lookup_channel(identifier):
            if channel.set_mute(enabled, False):
                self.channel_update_event(channel)

    def _on_update_level(self, identifier: ChannelIdentifier, level: Level) -> None:
        if channel := self._lookup_channel(identifier):
            if channel.set_level(level, False):
                self.channel_update_event(channel)

    def _on_update_send_level(
        self,
        identifier: ChannelIdentifier,
        to_channel_identifier: ChannelIdentifier,
        level: Level,
    ) -> None:
        channel = self._lookup_channel(identifier)
        to_channel = self._lookup_channel(to_channel_identifier)

        if (
            isinstance(channel, InputChannel)
            and isinstance(to_channel, OutputChannel)
            and channel.set_send_level(to_channel, level, False)
        ):
            self.channel_update_event(channel)

    def _on_recall_scene(self, scene: int) -> None:
        if self._scene != scene:
            self.scene_update_event(scene)

    def _lookup_channel(
        self, identifier: ChannelIdentifier
    ) -> typing.Optional[Channel]:
        hash_index = identifier.__hash__()

        if hash_index in self._channels:
            return self._channels[hash_index]

        return None


class LayerController:
    _MODE_DEFAULT = 0
    _MODE_SENDS_ON_FADER = 1
    _MODE_S_DCA = 2
    _MODE_OUTPUTS = 3

    def __init__(self, session: Session):
        self._scenes = {
            "default": 199,
            "virtual": 200,
            "output_start": 210,
        }

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

        mix_output_scene = (
            self._scenes["output_start"] + channel.identifier.canonical_index
        )
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

        for channel in filter(
            lambda c: c.affected_by_s_dca, self._session.input_channels
        ):
            channel.restore_sends()

        for channel in self._session.virtual_channels:
            channel.tie_to_zero()

        self._s_dca_active = False

        if self._mode == self._MODE_S_DCA:
            self.select_default()
        else:
            self.selection_update_event()

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
        affected_channels = list(
            filter(lambda c: c.selected, self._session.input_channels)
        )

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

    def _select_exclusively(self, selected: typing.Optional[Channel]) -> None:
        for channel in self._session.channels:
            channel.select(channel == selected)

    def _select_mode(self, mode: int):
        if self._mode != mode:
            self._mode = mode
            self.selection_update_event()

    def _on_scene_change(self, scene: int):
        # todo
        pass
