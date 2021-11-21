from collections import deque
from threading import Lock
from typing import Callable, Deque, List, Tuple

from mido.messages.messages import Message, SysexData

from app import App
from common.event import Event
from dlive.entity import Channel, ChannelIdentifier, Color, InputChannel, Level, OutputChannel


class Protocol:
    SYSEX_HEADER = [0x00, 0x00, 0x1A, 0x50, 0x10, 0x01, 0x00]

    def __init__(self):
        self._bank_offset = App.config.midi_bank_offset


class Decoder(Protocol):
    def __init__(self):
        Protocol.__init__(self)

        self._messages: Deque[Message] = deque()
        self._max_window = 3

        # Events
        self.label_changed_event: Event = Event()
        self.color_changed_event: Event = Event()
        self.mute_changed_event: Event = Event()
        self.level_changed_event: Event = Event()
        self.send_level_changed_event: Event = Event()
        self.scene_changed_event: Event = Event()

        self._decode_lock = Lock()
        self._handlers_to_execute: Deque[Tuple[Callable, List]] = deque()

    def feed_message(self, message: Message):
        with self._decode_lock:
            self._messages.appendleft(message)

            if len(self._messages) > self._max_window:
                self._messages.pop()

            self._decode()

        try:
            while handler_and_args := self._handlers_to_execute.popleft():
                handler, args = handler_and_args
                handler(*args)
        except IndexError:
            pass

    def _decode(self):
        m = self._messages

        # decode sysex
        if m[0].type == "sysex":
            self._decode_sysex_data(m[0].data)

            m.clear()
            return

        # decode length = 3
        if len(m) >= 3:
            if m[2].is_cc(0x63) and m[1].is_cc(0x62) and m[0].is_cc(0x06):
                n = m[2].channel
                ch = m[2].value
                parameter_id = m[1].value
                value = m[0].value

                if parameter_id == 0x17:
                    # (!) level
                    self._handlers_to_execute.append(
                        (self.level_changed_event, [self._decode_channel_identifier(n, ch), Level(value)])
                    )
                else:
                    # ignore unknown parameter
                    pass

                m.clear()
                return

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

                # (!) mute on/off
                self._handlers_to_execute.append(
                    (self.mute_changed_event, [self._decode_channel_identifier(n, ch), 0x7F == m[1].velocity])
                )

                m.clear()
                return

            if m[1].is_cc(0x00) and m[0].type == "program_change":
                n = m[1].value
                scene_offset = m[0].program

                # (!) scene recall
                self._handlers_to_execute.append((self.scene_changed_event, [(n << 7) + scene_offset]))

                m.clear()
                return

        pass

    def _decode_sysex_data(self, data: SysexData):
        minimum_data_length = 4

        if len(data) < len(self.SYSEX_HEADER) + minimum_data_length or list(data[:7]) != self.SYSEX_HEADER:
            # ignore invalid header
            return

        d = data[7:]
        identifier = self._decode_channel_identifier(d[0], d[2])
        parameter = d[1]

        if parameter == 0x02:
            label = bytearray(d[3:]).decode("ASCII").strip("0x\00")

            # (!) channel label
            self._handlers_to_execute.append((self.label_changed_event, [identifier, label]))

        elif parameter == 0x05 and d[3] <= 0x07:
            # (!) channel color
            self._handlers_to_execute.append((self.color_changed_event, [identifier, Color(d[3])]))

        elif parameter == 0x0D and 5 <= len(d) <= 6:
            # todo: this is a bug in the mixrack software where `SendN` isn't transmitted
            #       it happens when altering the send level of an FX bus in channel 0 (Ip 1)
            #       as a quick fix, we're hard coding the channel in this case
            if len(d) == 5:
                d.insert(3, self._bank_offset)

            to_channel_identifier = self._decode_channel_identifier(d[3], d[4])

            # (!) send level
            self._handlers_to_execute.append(
                (self.send_level_changed_event, [identifier, to_channel_identifier, Level(d[5])])
            )

    def _decode_channel_identifier(self, n: int, ch: int) -> ChannelIdentifier:
        return ChannelIdentifier.from_raw_data(n - self._bank_offset, ch)


class Encoder(Protocol):
    def __init__(self):
        Protocol.__init__(self)

        self.dispatch: Event = Event()  # data: list
        self._write_lock = Lock()
        self._debug_active = False

    def recall_scene(self, scene: int) -> list:
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

        self.dispatch(data)
        return data

    def label(self, channel: Channel) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + channel.identifier.midi_bank_offset,
            0x03,
            channel.identifier.midi_channel_index,
            *list(channel.label.encode("ASCII")),
            0xF7,
        ]

        self.dispatch(data)
        return data

    def request_label(self, channel: Channel) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + channel.identifier.midi_bank_offset,
            0x01,
            channel.identifier.midi_channel_index,
            0xF7,
        ]

        self.dispatch(data)
        return data

    def color(self, channel: Channel) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + channel.identifier.midi_bank_offset,
            0x06,
            channel.identifier.midi_channel_index,
            channel.color.value,
            0xF7,
        ]

        self.dispatch(data)
        return data

    def request_color(self, channel: Channel) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + channel.identifier.midi_bank_offset,
            0x04,
            channel.identifier.midi_channel_index,
            0xF7,
        ]

        self.dispatch(data)
        return data

    def mute(self, channel: Channel) -> list:
        data = [
            0x90 + self._bank_offset + channel.identifier.midi_bank_offset,
            channel.identifier.midi_channel_index,
            (0x3F, 0x7F)[channel.mute],
            channel.identifier.midi_channel_index,
            0x00,
        ]

        self.dispatch(data)
        return data

    def request_mute(self, channel: Channel) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + channel.identifier.midi_bank_offset,
            0x05,
            0x09,
            channel.identifier.midi_channel_index,
            0xF7,
        ]

        self.dispatch(data)
        return data

    def level(self, channel: Channel) -> list:
        data = [
            0xB0 + self._bank_offset + channel.identifier.midi_bank_offset,
            0x63,
            channel.identifier.midi_channel_index,
            0x62,
            0x17,
            0x06,
            channel.level,
        ]

        self.dispatch(data)
        return data

    def request_level(self, channel: Channel) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + channel.identifier.midi_bank_offset,
            0x05,
            0x0B,
            0x17,
            channel.identifier.midi_channel_index,
            0xF7,
        ]

        self.dispatch(data)
        return data

    def send_level(self, from_channel: InputChannel, to_channel: OutputChannel, level: Level) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + from_channel.identifier.midi_bank_offset,
            0x0D,
            from_channel.identifier.midi_channel_index,
            self._bank_offset + to_channel.identifier.midi_bank_offset,
            to_channel.identifier.midi_channel_index,
            level,
            0xF7,
        ]

        self.dispatch(data)
        return data

    def request_send_level(self, from_channel: InputChannel, to_channel: OutputChannel) -> list:
        data = [
            0xF0,
            *self.SYSEX_HEADER,
            self._bank_offset + from_channel.identifier.midi_bank_offset,
            0x05,
            0x0F,
            0x0D,
            from_channel.identifier.midi_channel_index,
            self._bank_offset + to_channel.identifier.midi_bank_offset,
            to_channel.identifier.midi_channel_index,
            0xF7,
        ]

        self.dispatch(data)
        return data
