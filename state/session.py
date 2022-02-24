import time
from typing import Dict, List, Optional

from app import App
from common.event import Event
from dlive.encoding import Decoder, Encoder
from dlive.entity import (
    Bank,
    Channel,
    ChannelIdentifier,
    Color,
    InputChannel,
    Level,
    MultiChannel,
    OutputChannel,
    VirtualChannel,
)


class Session:
    _DEBUG = False

    def __init__(self, decoder: Decoder, encoder: Encoder):
        self._decoder = decoder
        self._encoder = encoder

        self._channels: Dict[int, Channel] = {}
        self._inputs: List[InputChannel] = []
        self._fx_returns: List[InputChannel] = []
        self._aux: List[MultiChannel] = []
        self._fx: List[MultiChannel] = []
        self._virtual: List[VirtualChannel] = []
        self._scene: int = -1

        tracking_config = App.config.control_tracking

        # aux channels
        for index in range(
            tracking_config["mono_aux_start"], tracking_config["mono_aux_start"] + tracking_config["number_of_mono_aux"]
        ):
            channel = MultiChannel(ChannelIdentifier(Bank.MONO_AUX, index))
            self._aux.append(channel)
            self._channels[channel.identifier.__hash__()] = channel

        for index in range(tracking_config["number_of_stereo_aux"]):
            channel = MultiChannel(ChannelIdentifier(Bank.STEREO_AUX, index))
            self._aux.append(channel)
            self._channels[channel.identifier.__hash__()] = channel

        # external fx channels
        for index in range(
            tracking_config["external_fx_start"],
            tracking_config["external_fx_start"] + tracking_config["number_of_external_fx"],
        ):
            channel = MultiChannel(ChannelIdentifier(Bank.MONO_AUX, index))
            self._fx.append(channel)
            self._channels[channel.identifier.__hash__()] = channel

        # fx channels
        for index in range(tracking_config["number_of_mono_fx"]):
            channel = MultiChannel(ChannelIdentifier(Bank.MONO_FX_SEND, index))
            self._fx.append(channel)
            self._channels[channel.identifier.__hash__()] = channel

        for index in range(tracking_config["number_of_stereo_fx"]):
            channel = MultiChannel(ChannelIdentifier(Bank.STEREO_FX_SEND, index))
            self._fx.append(channel)
            self._channels[channel.identifier.__hash__()] = channel

        # virtual channels
        for index in range(tracking_config["virtual_start"], tracking_config["virtual_start"] + 16):
            channel = VirtualChannel(ChannelIdentifier(Bank.INPUT, index))
            self._virtual.append(channel)
            self._channels[channel.identifier.__hash__()] = channel

        self._virtual_feedback: OutputChannel = OutputChannel(
            ChannelIdentifier(Bank.MONO_MATRIX, tracking_config["feedback_matrix"])
        )
        self._channels[self._virtual_feedback.identifier.__hash__()] = self._virtual_feedback

        # inputs
        # let inputs hydrate sends on demand as it's an expensive operation
        def hydrate_sends_callback(input_channel: InputChannel) -> None:
            for to_channel in self.output_channels:
                self._encoder.request_send_level(input_channel, to_channel)

        for index in range(tracking_config["number_of_inputs"]):
            channel = InputChannel(ChannelIdentifier(Bank.INPUT, index), hydrate_sends_callback)

            # initialize sends
            for to_channel in [*self._aux, *self._fx, self._virtual_feedback]:
                channel.set_send_level(to_channel)

            self._inputs.append(channel)
            self._channels[channel.identifier.__hash__()] = channel

        for index in range(tracking_config["number_of_fx_returns"]):
            channel = InputChannel(ChannelIdentifier(Bank.FX_RETURN, index), hydrate_sends_callback)

            # initialize sends
            for to_channel in [*self._aux, *self._fx, self._virtual_feedback]:
                channel.set_send_level(to_channel)

            self._fx_returns.append(channel)
            self._channels[channel.identifier.__hash__()] = channel

        # tracking
        self.channel_update_event: Event = Event()
        self.scene_update_event: Event = Event()
        self.channel_mapping_event: Event = Event()

        self._tracking: bool = False

    @property
    def input_channels(self) -> List[InputChannel]:
        return self._inputs

    @property
    def fx_returns(self) -> List[InputChannel]:
        return self._fx_returns

    @property
    def aux_channels(self) -> List[OutputChannel]:
        return self._aux

    @property
    def fx_channels(self) -> List[OutputChannel]:
        return self._fx

    @property
    def output_channels(self) -> List[OutputChannel]:
        return [*self._aux, *self._fx]

    @property
    def virtual_channels(self) -> List[VirtualChannel]:
        return self._virtual

    @property
    def virtual_feedback_channel(self) -> OutputChannel:
        return self._virtual_feedback

    @property
    def channels(self) -> List[Channel]:
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

        # propagate changes made to channels
        for channel in self._channels.values():
            channel.label_changed_event.append(self._encoder.label)
            channel.color_changed_event.append(self._encoder.color)
            channel.mute_changed_event.append(self._encoder.mute)
            channel.level_changed_event.append(self._encoder.level)
            channel.select_changed_event.append(self.channel_update_event)

            if isinstance(channel, InputChannel):
                channel.send_level_changed_event.append(self._encoder.send_level)

        # track S-DCA changes
        for channel in self._inputs:
            channel.s_dca_changed_event.append(self.channel_update_event)

        # initialize channels, do not sync sends
        App.settings.set_status("Syncing…")
        timing_config = App.config.timing

        for channel in self._virtual:
            channel.unbind()

        self.route_feedback_to_output(None)
        self.virtual_feedback_channel.set_mute(False)
        self.virtual_feedback_channel.set_color(Color.OFF)
        self.virtual_feedback_channel.set_label("VFeedb.")

        for channel in self._channels.values():
            self._encoder.request_label(channel)
            self._encoder.request_color(channel)
            self._encoder.request_mute(channel)
            self._encoder.request_level(channel)

            # wait some time - otherwise the stupid mixrack begins sending
            # nonsense at some point…
            time.sleep(timing_config["channel_init_grace"])

        # poll color attribute every few seconds, as it is currently not
        # transmitted on change
        def poll_color_updates() -> None:
            for c in self._channels.values():
                if not isinstance(c, VirtualChannel):
                    self._encoder.request_color(c)

        App.scheduler.execute_interval(
            "poll_session_color_updates",
            max(
                len(self._channels) * timing_config["session_poll_channel_multiplier"],
                timing_config["session_poll_min"],
            ),
            poll_color_updates,
        )

        # periodically poll other channel attributes if enabled
        def poll_channel_updates() -> None:
            App.settings.set_status("Init. update")
            for c in self._channels.values():
                if not isinstance(c, VirtualChannel):
                    self._encoder.request_label(channel)
                    self._encoder.request_mute(channel)
                    self._encoder.request_level(channel)

        if timing_config["channel_poll"] > 0:
            App.scheduler.execute_interval(
                "poll_session_channel_updates",
                timing_config["channel_poll"],
                poll_channel_updates,
            )

        def hydrate_sends() -> None:
            grace_time = len(self.output_channels) * timing_config["hydration_grace_multiplier"]
            print(f"Begin hydrating with grace interval of {round(grace_time, 2)}s…")
            App.settings.set_status("Hydrating…")

            for c in [*self._inputs, *self._fx_returns]:
                if c.hydrate_sends():
                    time.sleep(grace_time)

            App.settings.set_status("Fully hydrated")

        App.scheduler.execute_delayed("hydrate_sends", 4, hydrate_sends)

    def load_scene(self, scene: int) -> None:
        self._encoder.recall_scene(scene)

    def route_feedback_to_output(self, target_channel: Optional[OutputChannel]) -> None:
        for channel in self.output_channels:
            if isinstance(channel, InputChannel):
                level = (Level.VALUE_OFF, Level.VALUE_0DB)[target_channel == channel]
                channel.set_send_level(self._virtual_feedback, level)

    def _on_update_label(self, identifier: ChannelIdentifier, label: str) -> None:
        if channel := self._lookup_channel(identifier):
            if self._DEBUG:
                print("label:  ", channel, "  ::  ", label)

            if channel.set_label(label, False):
                self.channel_update_event(channel)
                self.channel_mapping_event()

    def _on_update_color(self, identifier: ChannelIdentifier, color: Color) -> None:
        if channel := self._lookup_channel(identifier):
            if self._DEBUG:
                print("color:  ", channel, "  ::  ", color)

            if channel.set_color(color, False):
                self.channel_update_event(channel)
                self.channel_mapping_event()

    def _on_update_mute(self, identifier: ChannelIdentifier, enabled: bool) -> None:
        if channel := self._lookup_channel(identifier):
            if self._DEBUG:
                print("mute:   ", channel, "  ::  ", enabled)

            if channel.set_mute(enabled, False):
                self.channel_update_event(channel)

    def _on_update_level(self, identifier: ChannelIdentifier, level: Level) -> None:
        if channel := self._lookup_channel(identifier):
            if self._DEBUG:
                print("level:  ", channel, "  ::  ", level)

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

        if self._DEBUG:
            print("send:   ", channel, "  ==>  ", to_channel_identifier, "  ::  ", level)

        if not isinstance(channel, InputChannel) or not isinstance(to_channel, OutputChannel):
            return

        if channel.set_send_level(to_channel, level, False):
            self.channel_update_event(channel)

    def _on_recall_scene(self, scene: int) -> None:
        if self._scene != scene:
            self.scene_update_event(scene)

    def _lookup_channel(self, identifier: ChannelIdentifier) -> Optional[Channel]:
        hash_index = identifier.__hash__()

        if hash_index in self._channels:
            return self._channels[hash_index]

        return None
