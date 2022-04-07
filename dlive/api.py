from time import sleep
from threading import Thread
from typing import List, Dict, Optional

from tabulate import tabulate

from app import App
from common.event import AsyncEvent
from dlive.connection import DLiveSocketPort
from dlive.encoding import (
    Encoder,
    Decoder,
    MuteMessage,
    SceneMessage,
    ColorMessage,
    LabelMessage,
    LevelMessage,
    SendLevelMessage,
)
from dlive.entity import Color, Level, ChannelIdentifier, Bank, Scene, Label
from dlive.value import TrackedValue, ImmediateValue


class DLive:
    def __init__(self, outbound_connection: DLiveSocketPort, inbound_connection: DLiveSocketPort):
        # events sent on update
        self.on_update_scene: AsyncEvent = AsyncEvent("api.on_update_scene")
        self.on_update_color: AsyncEvent = AsyncEvent("api.on_update_color")
        self.on_update_label: AsyncEvent = AsyncEvent("api.on_update_label")
        self.on_update_mute: AsyncEvent = AsyncEvent("api.on_update_mute")
        self.on_update_level: AsyncEvent = AsyncEvent("api.on_update_level")
        self.on_update_send_level: AsyncEvent = AsyncEvent("api.on_update_send_level")

        # connection
        self._outbound_connection: DLiveSocketPort = outbound_connection
        self._inbound_connection: DLiveSocketPort = inbound_connection

        self._listener_enabled: bool = False
        self._encoder: Encoder = Encoder()
        self._decoder: Decoder = Decoder()

        # internal state storage
        self._scene: TrackedValue[Scene] = TrackedValue(self.on_update_scene)
        self._feedback_source: Optional[ChannelIdentifier] = None

        self._colors: Dict[ChannelIdentifier, ImmediateValue[Color]] = {}
        self._labels: Dict[ChannelIdentifier, TrackedValue[Label]] = {}
        self._mutes: Dict[ChannelIdentifier, TrackedValue[bool]] = {}
        self._levels: Dict[ChannelIdentifier, TrackedValue[Level]] = {}
        self._send_levels: Dict[ChannelIdentifier, Dict[ChannelIdentifier, TrackedValue[Level]]] = {}

        config = App.config.control_tracking

        self._channels: List[ChannelIdentifier] = []
        self._input_channels: List[ChannelIdentifier] = []
        self._send_channels: List[ChannelIdentifier] = []
        self._aux_channels: List[ChannelIdentifier] = []
        self._fx_channels: List[ChannelIdentifier] = []
        self._external_fx_channels: List[ChannelIdentifier] = []
        self._virtual_channels: List[ChannelIdentifier] = []

        def register_channel_updates(ch: ChannelIdentifier, no_label_and_color_feedback: bool = False) -> None:
            self._mutes[ch] = TrackedValue((lambda _ch: lambda v: self.on_update_mute(_ch, v))(ch))
            self._levels[ch] = TrackedValue((lambda _ch: lambda v: self.on_update_level(_ch, v))(ch))

            if no_label_and_color_feedback:
                self._colors[ch] = ImmediateValue()
                self._labels[ch] = TrackedValue()
            else:
                self._colors[ch] = ImmediateValue((lambda _ch: lambda v: self.on_update_color(_ch, v))(ch))
                self._labels[ch] = TrackedValue((lambda _ch: lambda v: self.on_update_label(_ch, v))(ch))

        def register_channel_sends_updates(ch: ChannelIdentifier) -> None:
            send_map = self._send_levels.get(ch, dict())
            for send_ch in self._send_channels:
                send_map[send_ch] = TrackedValue(
                    (lambda _ch, _send_ch: lambda v: self.on_update_send_level(_ch, _send_ch, v))(ch, send_ch)
                )

            self._send_levels[ch] = send_map

        # … aux channels
        for index in range(mono_aux_start := config["mono_aux_start"], mono_aux_start + config["number_of_mono_aux"]):
            mono_aux_ch = ChannelIdentifier(Bank.MONO_AUX, index)
            register_channel_updates(mono_aux_ch)
            self._send_channels.append(mono_aux_ch)
            self._aux_channels.append(mono_aux_ch)
            self._channels.append(mono_aux_ch)

        for index in range(
            external_fx_start := config["external_fx_start"], external_fx_start + config["number_of_external_fx"]
        ):
            mono_aux_ch = ChannelIdentifier(Bank.MONO_AUX, index)
            register_channel_updates(mono_aux_ch)
            self._send_channels.append(mono_aux_ch)
            self._external_fx_channels.append(mono_aux_ch)
            self._channels.append(mono_aux_ch)

        for index in range(config["number_of_stereo_aux"]):
            stereo_aux_ch = ChannelIdentifier(Bank.STEREO_AUX, index)
            register_channel_updates(stereo_aux_ch)
            self._send_channels.append(stereo_aux_ch)
            self._aux_channels.append(stereo_aux_ch)
            self._channels.append(stereo_aux_ch)

        # … fx channels
        for index in range(config["number_of_mono_fx"]):
            mono_fx_ch = ChannelIdentifier(Bank.MONO_FX_SEND, index)
            register_channel_updates(mono_fx_ch)
            self._send_channels.append(mono_fx_ch)
            self._fx_channels.append(mono_fx_ch)
            self._channels.append(mono_fx_ch)

        for index in range(config["number_of_stereo_fx"]):
            stereo_fx_ch = ChannelIdentifier(Bank.STEREO_FX_SEND, index)
            register_channel_updates(stereo_fx_ch)
            self._send_channels.append(stereo_fx_ch)
            self._fx_channels.append(stereo_fx_ch)
            self._channels.append(stereo_fx_ch)

        # … input channels
        for index in range(config["number_of_inputs"]):
            input_ch = ChannelIdentifier(Bank.INPUT, index)
            register_channel_updates(input_ch)
            register_channel_sends_updates(input_ch)
            self._input_channels.append(input_ch)
            self._channels.append(input_ch)

        # … virtual input channels
        for index in range(virtual_start := config["virtual_start"], virtual_start + 16):
            virtual_channel = ChannelIdentifier(Bank.INPUT, index)
            register_channel_updates(virtual_channel, no_label_and_color_feedback=True)
            self._virtual_channels.append(virtual_channel)
            self._channels.append(virtual_channel)

        # … virtual feedback channel
        self._virtual_feedback_channel = ChannelIdentifier(Bank.MONO_MATRIX, config["feedback_matrix"])

        # … aliases for special individual input channels
        self._talk_to_stage_channel: ChannelIdentifier = self._input_channels[config["talk_to_stage"]]
        self._talk_to_monitor_channel: ChannelIdentifier = self._input_channels[config["talk_to_monitor"]]

    @property
    def output_channels(self) -> List[ChannelIdentifier]:
        return self._send_channels

    @property
    def aux_channels(self) -> List[ChannelIdentifier]:
        return self._aux_channels

    @property
    def fx_channels(self) -> List[ChannelIdentifier]:
        return self._fx_channels

    @property
    def external_fx_channels(self) -> List[ChannelIdentifier]:
        return self._external_fx_channels

    @property
    def input_channels(self) -> List[ChannelIdentifier]:
        return self._input_channels

    @property
    def virtual_channels(self) -> List[ChannelIdentifier]:
        return self._virtual_channels

    @property
    def talk_to_stage_channel(self) -> ChannelIdentifier:
        return self._talk_to_stage_channel

    @property
    def talk_to_monitor_channel(self) -> ChannelIdentifier:
        return self._talk_to_monitor_channel

    def listen(self) -> None:
        if self._listener_enabled:
            return

        self._listener_enabled = True

        listener = Thread(target=self._listen_to_incoming_data)
        listener.start()

        def _purge_stale_requests():
            if (purged := TrackedValue.purge_all(1)) > 0:
                App.notify(f"Purged {purged} stale requests.")

        App.scheduler.execute_interval("purge_stale_requests", 3, _purge_stale_requests)

    def _listen_to_incoming_data(self):
        for midi_message in self._inbound_connection:
            if (message := self._decoder.feed_and_decode(midi_message)) is None:
                continue

            try:
                if isinstance(message, SendLevelMessage):
                    self._get_tracked_send_level(message.channel, message.to_channel).resolve(message.level)
                elif isinstance(message, LevelMessage):
                    self._get_tracked_level(message.channel).resolve(message.level)
                elif isinstance(message, MuteMessage):
                    self._get_tracked_mute(message.channel).resolve(message.mute)
                elif isinstance(message, SceneMessage):
                    self._scene.resolve(message.scene)
                elif isinstance(message, ColorMessage):
                    self._get_tracked_color(message.channel).resolve(message.color)
                elif isinstance(message, LabelMessage):
                    self._get_tracked_label(message.channel).resolve(message.label)
                else:
                    # print(message)
                    pass

            except IndexError:
                pass

    def sync(self) -> None:
        self.listen()
        self.wait_until_settled(False)

        # setup state
        self.change_scene(Scene(App.config.control_scenes["mixing_start"]))
        self.change_feedback_source()

        # request first set of properties
        # mutes needs to come before colors, see quirks_mode
        self._decoder.mute_color_quirks_mode = True

        for channel in self._mutes.keys():
            self._outbound_connection.send_bytes(self._encoder.request_mute(channel))

        for channel in self._labels.keys():
            self._outbound_connection.send_bytes(self._encoder.request_label(channel))

        self.wait_until_settled()
        self._decoder.mute_color_quirks_mode = False

        # request all other channel properties
        for channel in self._colors.keys():
            self._outbound_connection.send_bytes(self._encoder.request_color(channel))

        for channel in self._levels.keys():
            self._outbound_connection.send_bytes(self._encoder.request_level(channel))

        for channel, send_map in self._send_levels.items():
            for to_channel in send_map.keys():
                self._outbound_connection.send_bytes(self._encoder.request_send_level(channel, to_channel))

        self.wait_until_settled()

        def poll_color_updates():
            for ch in self._colors.keys():
                self._outbound_connection.send_bytes(self._encoder.request_color(ch))

        App.scheduler.execute_interval("poll_color_updates", 6, poll_color_updates)

    def get_scene(self, use_fallback: bool = True) -> Optional[Scene]:
        if (value := self._scene.value) is not None:
            return value

        return Scene(0)

    def get_color(self, channel: ChannelIdentifier, use_fallback: bool = True) -> Optional[Color]:
        if (value := self._get_tracked_color(channel).value) is not None or not use_fallback:
            return value

        return Color.OFF

    def get_label(self, channel: ChannelIdentifier, use_fallback: bool = True) -> Optional[Label]:
        if (value := self._get_tracked_label(channel).value) is not None or not use_fallback:
            return value

        return Label()

    def get_mute(self, channel: ChannelIdentifier, use_fallback: bool = True) -> Optional[bool]:
        if (value := self._get_tracked_mute(channel).value) is not None or not use_fallback:
            return value

        return False

    def get_level(self, channel: ChannelIdentifier, use_fallback: bool = True) -> Optional[Level]:
        if (value := self._get_tracked_level(channel).value) is not None or not use_fallback:
            return value

        return Level.VALUE_OFF

    def get_send_level(
        self, channel: ChannelIdentifier, to_channel: ChannelIdentifier, use_fallback: bool = True
    ) -> Optional[Level]:
        if (value := self._get_tracked_send_level(channel, to_channel).value) is not None or not use_fallback:
            return value

        return Level.VALUE_OFF

    def change_scene(self, scene: Scene) -> None:
        if self._scene.request(scene)[1]:
            self._outbound_connection.send_bytes(self._encoder.recall_scene(scene))

    def change_color(self, channel: ChannelIdentifier, color: Color) -> None:
        if self._get_tracked_color(channel).request(color)[1]:
            self._outbound_connection.send_bytes(self._encoder.color(channel, color))

    def change_label(self, channel: ChannelIdentifier, label: Label) -> None:
        if self._get_tracked_label(channel).request(label)[1]:
            self._outbound_connection.send_bytes(self._encoder.label(channel, label))

    def change_mute(self, channel: ChannelIdentifier, mute: bool) -> None:
        if self._get_tracked_mute(channel).request(mute)[1]:
            self._outbound_connection.send_bytes(self._encoder.mute(channel, mute))

    def change_level(self, channel: ChannelIdentifier, level: Level) -> None:
        if self._get_tracked_level(channel).request(level)[1]:
            self._outbound_connection.send_bytes(self._encoder.level(channel, level))

    def change_send_level(self, channel: ChannelIdentifier, to_channel: ChannelIdentifier, level: Level) -> None:
        if self._get_tracked_send_level(channel, to_channel).request(level)[1]:
            self._outbound_connection.send_bytes(self._encoder.send_level(channel, to_channel, level))

    def change_feedback_source(self, channel: Optional[ChannelIdentifier] = None) -> None:
        if channel is not None and channel not in self._send_channels:
            raise IndexError(f"The channel {channel} is not a valid send channel.")

        self._feedback_source = channel

        for send_channel in self._send_channels:
            level = (Level.VALUE_OFF, Level.VALUE_0DB)[self._feedback_source == send_channel]
            # we do not track these values, just send them
            self._outbound_connection.send_bytes(
                self._encoder.send_level(send_channel, self._virtual_feedback_channel, level)
            )

    def _get_tracked_color(self, channel: ChannelIdentifier) -> TrackedValue[Color]:
        if not (tracked_value := self._colors.get(channel, False)):
            raise IndexError(f"There is no tracked color information for channel {channel}.")

        return tracked_value

    def _get_tracked_label(self, channel: ChannelIdentifier) -> TrackedValue[Label]:
        if not (tracked_value := self._labels.get(channel, False)):
            raise IndexError(f"There is no tracked label information for channel {channel}.")

        return tracked_value

    def _get_tracked_mute(self, channel: ChannelIdentifier) -> TrackedValue[bool]:
        if not (tracked_value := self._mutes.get(channel, False)):
            raise IndexError(f"There is no tracked mute information for channel {channel}.")

        return tracked_value

    def _get_tracked_level(self, channel: ChannelIdentifier) -> TrackedValue[Level]:
        if not (tracked_value := self._levels.get(channel, False)):
            raise IndexError(f"There is no tracked level information for channel {channel}.")

        return tracked_value

    def _get_tracked_send_level(self, channel: ChannelIdentifier, to_channel: ChannelIdentifier) -> TrackedValue[Level]:
        if not (tracked_value := self._send_levels.get(channel, {}).get(to_channel, False)):
            raise IndexError(f"There is no tracked send level information for channel {channel} to {to_channel}.")

        return tracked_value

    def wait_until_settled(self, wait_initial: bool = True) -> None:
        if wait_initial:
            sleep(1)

        while not self._decoder.settled():
            sleep(0.1)

    def __str__(self) -> str:
        output = "DLive {\n"
        output += f"  scene:           {self._scene}\n"
        output += f"  feedback source: {self._feedback_source}\n"

        # channel table
        tabular_data = []

        for channel in self._channels:
            sends = []
            for to_channel, tracked_value in self._send_levels.get(channel, {}).items():
                if (level := tracked_value.value) not in [None, Level.VALUE_OFF]:
                    sends.append(f"{to_channel.short_label()}@{level}")

            tabular_data.append(
                [
                    channel.short_label(),
                    self._labels.get(channel, "-"),
                    self._colors.get(channel, "-"),
                    self._mutes.get(channel, "-"),
                    self._levels.get(channel, "-"),
                    ", ".join(sends),
                ]
            )

        table = tabulate(
            tabular_data,
            headers=["channel", "label", "color", "mute", "level", "sends"],
            tablefmt="pretty",
            colalign="left",
            stralign="left",
            numalign="left",
        )
        output += "\n  " + "  ".join(table.splitlines(True))

        output += "\n}\n"
        return output
