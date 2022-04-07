from collections import deque
from dataclasses import dataclass
from threading import Lock
from time import time
from typing import Deque, Optional

from mido.messages.messages import Message, SysexData

from app import App
from dlive.entity import ChannelIdentifier, Color, Level, Scene, Label


class DLiveMessage:
    pass


@dataclass
class SceneMessage(DLiveMessage):
    scene: Scene


@dataclass
class ChannelMessage(DLiveMessage):
    channel: ChannelIdentifier


@dataclass
class LabelMessage(ChannelMessage):
    label: Label


@dataclass
class ColorMessage(ChannelMessage):
    color: Color


@dataclass
class MuteMessage(ChannelMessage):
    mute: bool


@dataclass
class LevelMessage(ChannelMessage):
    level: Level


@dataclass
class SendLevelMessage(LevelMessage):
    to_channel: ChannelIdentifier


@dataclass
class UnknownSysexMessage(DLiveMessage):
    bytes: list
    info: str = ""


class Protocol:
    SYSEX_HEADER = [0x00, 0x00, 0x1A, 0x50, 0x10, 0x01, 0x00]

    def __init__(self):
        self._bank_offset = App.config.midi_bank_offset


class Decoder(Protocol):
    def __init__(self):
        Protocol.__init__(self)

        self._messages: Deque[Message] = deque()
        self._max_window = 3
        self._decode_lock = Lock()
        self._last_inbound_data: float = 0.0

        # if set to True, no colors will be decoded
        self.mute_color_quirks_mode = False

    def settled(self) -> bool:
        return (time() - self._last_inbound_data) > 0.8

    def feed_and_decode(self, midi_message: Message) -> Optional[DLiveMessage]:
        with self._decode_lock:
            self._last_inbound_data = time()
            self._messages.appendleft(midi_message)

            if len(self._messages) > self._max_window:
                self._messages.pop()

            message = self._decode()

        return message

    def _decode(self) -> Optional[DLiveMessage]:
        m = self._messages
        decoded = None

        # decode sysex
        if m[0].type == "sysex":
            decoded = self._decode_sysex_data(m[0].data)

            m.clear()
            return decoded

        # decode length = 3
        if len(m) >= 3:
            if m[2].is_cc(0x63) and m[1].is_cc(0x62) and m[0].is_cc(0x06):
                n = m[2].channel
                ch = m[2].value
                parameter_id = m[1].value
                value = m[0].value

                if parameter_id == 0x17:
                    # … level changed
                    decoded = LevelMessage(channel=self._decode_channel_identifier(n, ch), level=Level(value))
                else:
                    # ignore unknown parameter
                    pass

                m.clear()
                return decoded

        # decode length = 2
        if len(m) >= 2:
            if (
                m[1].type == "note_on"
                and m[1].velocity in [0x7F, 0x3F]
                and m[0].type == "note_on"
                and m[0].velocity == 0x00
            ):
                n = m[1].channel
                ch = m[1].note

                # … mute on/off
                decoded = MuteMessage(channel=self._decode_channel_identifier(n, ch), mute=0x7F == m[1].velocity)

                m.clear()
                return decoded

            if m[1].is_cc(0x00) and m[0].type == "program_change":
                n = m[1].value
                scene_offset = m[0].program

                # … scene recall
                decoded = SceneMessage(scene=Scene((n << 7) + scene_offset))

                m.clear()
                return decoded

        return None

    def _decode_sysex_data(self, data: SysexData) -> Optional[DLiveMessage]:
        minimum_data_length = 4

        if len(data) < len(self.SYSEX_HEADER) + minimum_data_length or list(data[:7]) != self.SYSEX_HEADER:
            # ignore invalid header
            return

        d = data[7:]
        identifier = self._decode_channel_identifier(d[0], d[2])
        parameter = d[1]

        if parameter == 0x02:
            label = bytearray(d[3:]).decode("ASCII").strip("\00")

            # … channel label
            return LabelMessage(channel=identifier, label=Label(label))

        if parameter == 0x05 and d[3] <= 0x07:
            # todo: The current implementation in the mixrack software will mirror all
            #       request_* messages… but they are ambiguous. Requesting a mute status
            #       [SysEx Header, 0N, 05, 09, CH, F7] is identical to receiving a color
            #       [SysEx Header, 0N, 05, CH, Col, F7] on channel 9. Until this is is
            #       fixed, we've got a quirks mode in place that prevents decoding color
            #       messages.
            if self.mute_color_quirks_mode:
                return UnknownSysexMessage(
                    bytes=d,
                    info="Skipping message that could either be color information or a mirrored 'request for mute'.",
                )

            # … channel color
            return ColorMessage(channel=identifier, color=Color(d[3]))

        if parameter == 0x0D and 5 <= len(d) <= 6:
            # todo: This is a bug in the mixrack software where `SendN` isn't transmitted
            #       it happens when altering the send level of an FX bus in channel 0 (Ip 1)
            #       as a quick fix, we're hard coding the channel in this case
            if len(d) == 5:
                d.insert(3, self._bank_offset)

            to_channel_identifier = self._decode_channel_identifier(d[3], d[4])

            # … send level
            return SendLevelMessage(channel=identifier, to_channel=to_channel_identifier, level=Level(d[5]))

        return UnknownSysexMessage(bytes=d)

    def _decode_channel_identifier(self, n: int, ch: int) -> ChannelIdentifier:
        return ChannelIdentifier.from_raw_data(n - self._bank_offset, ch)


class Encoder(Protocol):
    def __init__(self):
        Protocol.__init__(self)

    def recall_scene(self, scene: Scene) -> list:
        if scene < 0 or scene > 499:
            raise IndexError("Scene must be in the range [0..499]")

        bank = scene >> 7
        scene_offset = scene - (bank << 7)

        data = [
            0xB0 + self._bank_offset,
            0x00,
            bank,
            0xC0 + self._bank_offset,
            scene_offset,
        ]

        return data

    def label(self, channel: ChannelIdentifier, label: Label) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + channel.midi_bank_offset,
            0x03,
            channel.midi_channel_index,
            *list(label.encode("ASCII")),
            0xF7,
        ]

        return data

    def request_label(self, channel: ChannelIdentifier) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + channel.midi_bank_offset,
            0x01,
            channel.midi_channel_index,
            0xF7,
        ]

        return data

    def color(self, channel: ChannelIdentifier, color: Color) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + channel.midi_bank_offset,
            0x06,
            channel.midi_channel_index,
            color.value,
            0xF7,
        ]

        return data

    def request_color(self, channel: ChannelIdentifier) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + channel.midi_bank_offset,
            0x04,
            channel.midi_channel_index,
            0xF7,
        ]

        return data

    def mute(self, channel: ChannelIdentifier, mute: bool) -> list:
        data = [
            0x90 + self._bank_offset + channel.midi_bank_offset,
            channel.midi_channel_index,
            (0x3F, 0x7F)[mute],
            channel.midi_channel_index,
            0x00,
        ]

        return data

    def request_mute(self, channel: ChannelIdentifier) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + channel.midi_bank_offset,
            0x05,
            0x09,
            channel.midi_channel_index,
            0xF7,
        ]

        return data

    def level(self, channel: ChannelIdentifier, level: Level) -> list:
        data = [
            0xB0 + self._bank_offset + channel.midi_bank_offset,
            0x63,
            channel.midi_channel_index,
            0x62,
            0x17,
            0x06,
            level,
        ]

        return data

    def request_level(self, channel: ChannelIdentifier) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + channel.midi_bank_offset,
            0x05,
            0x0B,
            0x17,
            channel.midi_channel_index,
            0xF7,
        ]

        return data

    def send_level(self, from_channel: ChannelIdentifier, to_channel: ChannelIdentifier, level: Level) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + from_channel.midi_bank_offset,
            0x0D,
            from_channel.midi_channel_index,
            self._bank_offset + to_channel.midi_bank_offset,
            to_channel.midi_channel_index,
            level,
            0xF7,
        ]

        return data

    def request_send_level(self, from_channel: ChannelIdentifier, to_channel: ChannelIdentifier) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + from_channel.midi_bank_offset,
            0x05,
            0x0F,
            0x0D,
            from_channel.midi_channel_index,
            self._bank_offset + to_channel.midi_bank_offset,
            to_channel.midi_channel_index,
            0xF7,
        ]

        return data
