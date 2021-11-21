import re
import typing
from copy import copy
from enum import Enum
from threading import Lock, Thread

from app import App
from common.event import Event


def _make_bank_lookups(bank_map: dict) -> tuple:
    bank_offset_by_bank = {}
    channel_offset_by_bank = {}

    for bank_offset, banks in bank_map.items():
        for channel_offset, bank in banks.items():
            bank_offset_by_bank[bank] = bank_offset
            channel_offset_by_bank[bank] = channel_offset

    return bank_offset_by_bank, channel_offset_by_bank


class Color(Enum):
    """
    Channel color
    """

    OFF = 0x00, (0x20, 0x20, 0x20)
    RED = 0x01, (0xFF, 0x00, 0x00)
    GREEN = 0x02, (0x00, 0xFF, 0x00)
    YELLOW = 0x03, (0xFF, 0xFF, 0x00)
    BLUE = 0x04, (0x00, 0x00, 0xFF)
    PURPLE = 0x05, (0xAA, 0x00, 0xAA)
    LIGHT_BLUE = 0x06, (0x00, 0xFF, 0xFF)
    WHITE = 0x07, (0xFF, 0xFF, 0xFF)

    def __new__(cls, *args, **kwds):
        obj = object.__new__(cls)
        obj._value_ = args[0]
        return obj

    def __init__(self, _: str, rgb: typing.Tuple[int, int, int]):
        self._rgb_ = rgb

    def __str__(self):
        return self.name

    @property
    def rgb(self):
        return self._rgb_


class Level(int):
    """
    Channel or send level. Values have a linear dependency to dBu values
    and a logarithmic dependency to physical fader positions.
    """

    VALUE_FULL = 0x7F
    VALUE_0DB = 0x6B
    VALUE_OFF = 0x00
    VALUE_FADER_MIDPOINT = 0x58

    def __new__(cls, value: int = 0):
        return int.__new__(cls, max(min(Level.VALUE_FULL, value), Level.VALUE_OFF))

    def __str__(self) -> str:
        value = int(self)

        if value <= 1:
            return "-inf"

        dbu = ((value - 17) * 55 / 110) - 45

        return "{0:+}".format(int(dbu))


class Bank(Enum):
    """
    Channel bank
    """

    INPUT = 0, "Ip"
    MONO_GROUP = 1, "Grp"
    STEREO_GROUP = 2, "StGrp"
    MONO_AUX = 3, "Aux"
    STEREO_AUX = 4, "StAux"
    MONO_MATRIX = 5, "Mtx"
    STEREO_MATRIX = 6, "StMtx"
    MONO_FX_SEND = 7, "FX"
    STEREO_FX_SEND = 8, "StFX"
    FX_RETURN = 9, "FXRet"
    MAIN = 10, "Main"
    DCA = 11, "DCA"
    MUTE_GROUP = 12, "MuteG"

    def __new__(cls, *args, **kwds):
        obj = object.__new__(cls)
        obj._value_ = args[0]
        return obj

    def __init__(self, _: str, short_name: str = None):
        self._short_name_ = short_name

    def __str__(self):
        return self.value

    @property
    def short_name(self):
        return self._short_name_


class ChannelIdentifier:
    """
    Bank and offset information uniquely describing a channel.
    """

    _BANK_MAP = {
        0: {
            0x00: Bank.INPUT,
        },
        1: {
            0x00: Bank.MONO_GROUP,
            0x40: Bank.STEREO_GROUP,
        },
        2: {
            0x00: Bank.MONO_AUX,
            0x40: Bank.STEREO_AUX,
        },
        3: {
            0x00: Bank.MONO_MATRIX,
            0x40: Bank.STEREO_MATRIX,
        },
        4: {
            0x00: Bank.MONO_FX_SEND,
            0x10: Bank.STEREO_FX_SEND,
            0x20: Bank.FX_RETURN,
            0x30: Bank.MAIN,
            0x36: Bank.DCA,
            0x4E: Bank.MUTE_GROUP,
        },
    }

    _BANK_OFFSET_BY_BANK, _CHANNEL_OFFSET_BY_BANK = _make_bank_lookups(_BANK_MAP)

    def __init__(self, bank: Bank, canonical_index: int):
        self._bank = bank
        self._canonical_index = canonical_index

    @property
    def bank(self) -> Bank:
        return self._bank

    @property
    def canonical_index(self) -> int:
        return self._canonical_index

    @property
    def midi_bank_offset(self) -> int:
        return self._BANK_OFFSET_BY_BANK[self._bank]

    @property
    def midi_channel_index(self) -> int:
        return self._CHANNEL_OFFSET_BY_BANK[self._bank] + self._canonical_index

    @property
    def is_mono_feed(self) -> typing.Optional[bool]:
        if self._bank in [Bank.MONO_GROUP, Bank.MONO_AUX, Bank.MONO_MATRIX, Bank.MONO_FX_SEND]:
            return True

        if self._bank in [Bank.STEREO_GROUP, Bank.STEREO_AUX, Bank.STEREO_MATRIX, Bank.STEREO_FX_SEND]:
            return False

        return None

    @classmethod
    def from_raw_data(cls, bank_offset: int, channel_offset: int) -> "ChannelIdentifier":
        if bank_offset not in ChannelIdentifier._BANK_MAP:
            raise IndexError("Invalid bank offset")

        banks = ChannelIdentifier._BANK_MAP[bank_offset]
        for channel_offset_start in reversed(banks):
            if channel_offset_start <= channel_offset:
                return ChannelIdentifier(banks[channel_offset_start], channel_offset - channel_offset_start)

        raise IndexError("Invalid channel offset")

    def short_label(self) -> str:
        return "{} {}".format(self.bank.short_name, self.canonical_index + 1)

    def __str__(self):
        return "{}#{} {{ N_base={}, CH={} }}".format(
            self.bank.name,
            self.canonical_index,
            self.midi_bank_offset,
            self.midi_channel_index,
        )

    def __eq__(self, other: "ChannelIdentifier"):
        return other is not None and self._bank == other._bank and self._canonical_index == other._canonical_index

    def __hash__(self):
        return hash((self._bank, self._canonical_index))


class Channel:
    """
    Basic channel entity, that implements a property observer pattern: setting values will trigger the respective
    change event if the value differs from the internal state.
    """

    def __init__(self, identifier: ChannelIdentifier):
        self._identifier: ChannelIdentifier = identifier

        self._label: str = ""
        self._color: Color = Color.OFF
        self._mute: bool = False
        self._level: Level = Level()

        self._selected: bool = False

        # Change events
        self.label_changed_event: Event = Event()
        self.color_changed_event: Event = Event()
        self.mute_changed_event: Event = Event()
        self.level_changed_event: Event = Event()
        self.select_changed_event: Event = Event()

        # Lock
        self._update_lock = Lock()

    @property
    def identifier(self):
        return self._identifier

    @property
    def label(self):
        return self._label

    @property
    def color(self):
        return self._color

    @property
    def mute(self):
        return self._mute

    @property
    def level(self):
        return self._level

    @property
    def is_visible(self) -> bool:
        return not re.match(r"^[0-9\s]*$", self._label)

    @property
    def selected(self) -> bool:
        return self._selected

    def set_label(self, label: str, trigger_change_event: bool = True) -> bool:
        label = label[:8].strip("0x\00 ")

        if self._label == label:
            return False

        if trigger_change_event:
            channel = copy(self)
            channel._label = label
            self.label_changed_event(channel)

        self._label = label
        return True

    def set_color(self, color: Color, trigger_change_event: bool = True) -> bool:
        if self._color == color:
            return False

        if trigger_change_event:
            channel = copy(self)
            channel._color = color
            self.color_changed_event(channel)

        self._color = color
        return True

    def set_mute(self, enabled: bool, trigger_change_event: bool = True) -> bool:
        if self._mute == enabled:
            return False

        if trigger_change_event:
            channel = copy(self)
            channel._mute = enabled
            self.mute_changed_event(channel)

            return False

        self._mute = enabled
        return True

    def set_level(self, level: Level, trigger_change_event: bool = True) -> bool:
        if self._level == level:
            return False

        if trigger_change_event:
            channel = copy(self)
            channel._level = level
            self.level_changed_event(channel)

        self._level = level
        return True

    def select(self, state: bool = True, trigger_change_event: bool = True) -> bool:
        if self._selected == state:
            return False

        self._selected = state

        if trigger_change_event:
            self.select_changed_event(self)

        return True

    def __str__(self):
        return 'Channel {} "{}"'.format(
            self._identifier,
            self._label,
        )

    def __eq__(self, other: "Channel"):
        return other is not None and self._identifier == other._identifier

    def __hash__(self):
        return hash(self._identifier)


class OutputChannel(Channel):
    pass


class InputChannel(Channel):
    def __init__(self, identifier: ChannelIdentifier, hydrate_sends_callback: typing.Optional[typing.Callable] = None):
        super(InputChannel, self).__init__(identifier)

        self._sends: typing.Dict[int, typing.Tuple[Level, OutputChannel]] = {}
        self._sends_snapshot: typing.Dict[int, typing.Tuple[Level, OutputChannel]] = {}
        self._affected_by_s_dca: typing.Set[int] = set()

        self.send_level_changed_event: Event = Event()
        self.s_dca_changed_event: Event = Event()

        self._hydrate_sends_lock = Lock()
        self._sends_hydrated: bool = False
        self._hydrate_sends_callback: typing.Callable = hydrate_sends_callback

    @property
    def send_channels(self) -> typing.List[OutputChannel]:
        return list(map(lambda t: t[1], self._sends.values()))

    def hydrate_sends(self) -> bool:
        if not self._hydrate_sends_lock.acquire(timeout=1.0):
            return False

        if not self._sends_hydrated and self._hydrate_sends_callback:
            self._hydrate_sends_callback(self)
            self._sends_hydrated = True
            print(f"Hydrated sends of {self.identifier.short_label()}")

        now_hydrated = self._sends_hydrated
        self._hydrate_sends_lock.release()

        return now_hydrated

    def get_send_level(self, to_channel: OutputChannel) -> typing.Optional[Level]:
        self.hydrate_sends()
        hash_index = to_channel.identifier.__hash__()

        if hash_index not in self._sends:
            return None

        return self._sends[hash_index][0]

    def set_send_level(
        self,
        to_channel: "OutputChannel",
        level: Level = Level(0),
        trigger_change_event: bool = True,
    ) -> bool:
        hash_index = to_channel.identifier.__hash__()

        if hash_index in self._sends and self._sends[hash_index][0] == level:
            return False

        self._sends[hash_index] = (level, to_channel)

        if trigger_change_event:
            self.send_level_changed_event(self, to_channel, level)

        return True

    def backup_sends(self) -> None:
        """Create snapshot of the current send levels."""
        with self._hydrate_sends_lock:
            if self._sends_hydrated:
                self._sends_snapshot = copy(self._sends)

    def restore_sends(self) -> None:
        """Restore send levels from the snapshot and clear 'affected by s_dca' state."""
        if len(self._sends_snapshot) == 0:
            App.settings.set_status(f"Restore fail | {self.identifier.short_label()}")
            return

        for hash_index, level_output in self._sends_snapshot.items():
            level, to_channel = level_output

            if (
                hash_index in self._sends
                and to_channel.identifier.__hash__() in self._affected_by_s_dca
                and self._sends[hash_index][0] != level
            ):
                self._sends[hash_index] = (level, to_channel)
                self.send_level_changed_event(self, to_channel, level)

        self._affected_by_s_dca.clear()
        self.s_dca_changed_event(self)

    def drop_sends_backup(self) -> None:
        """Accept current send levels and drop the snapshot."""
        self._sends_snapshot = {}
        self._affected_by_s_dca.clear()

        self.s_dca_changed_event(self)

    def mark_affected_by_s_dca(self, with_channel: OutputChannel) -> None:
        hash_identifier = with_channel.identifier.__hash__()
        promote_change = hash_identifier not in self._affected_by_s_dca
        self._affected_by_s_dca.add(hash_identifier)

        if promote_change:
            self.s_dca_changed_event(self)

    @property
    def affected_by_s_dca(self) -> bool:
        return len(self._affected_by_s_dca) > 0


class MultiChannel(InputChannel, OutputChannel):
    pass


class VirtualChannel(OutputChannel):
    """
    A virtual channel tracks the (send) levels of another channel.
    This mapping can be dynamically changed at runtime.
    """

    _MODE_NONE = -1
    _MODE_TIE_TO_ZERO = 0
    _MODE_TRACK_SEND_LEVEL = 1
    _MODE_TRACK_MASTER_LEVEL = 2
    _MODE_SEND_DCA = 3

    def __init__(self, identifier: ChannelIdentifier):
        super(VirtualChannel, self).__init__(identifier)

        self._channel_base: typing.Optional[InputChannel] = None
        self._channel_send: typing.Optional[OutputChannel] = None
        self._affected_s_dca_channels: typing.List[typing.Tuple[InputChannel, Level]] = []

        self._mode = self._MODE_NONE

    def bind_send(self, base_channel: InputChannel, to_channel: OutputChannel, inverse: bool = False) -> bool:
        """Track the send level to a given output of a given base channel."""
        level = base_channel.get_send_level(to_channel)

        # reject if send levels are not settled
        if level is None:
            App.settings.set_status("Not synced | Try again")
            print(f"Send levels of {base_channel.identifier.short_label()} are not fully settled, yet.")

            return False

        with self._update_lock:
            self._mode = self._MODE_TRACK_SEND_LEVEL
            self._channel_base = base_channel
            self._channel_send = to_channel
            self._affected_s_dca_channels = []

        # set label and color from target/base channel
        if not inverse:
            self.set_label(f">{to_channel.label}")
            self.set_color(to_channel.color)
        else:
            self.set_label(f"@{base_channel.label}")
            self.set_color(base_channel.color)

        # initialize fader level
        self.set_level(level)
        self.set_mute(False)

        return True

    def bind_s_dca(self, base_channels: typing.List[InputChannel], to_channel: OutputChannel) -> bool:
        """Simultaneously track a send level to a given output on multiple base channels."""
        affected_s_dca_channels = list(
            zip(
                base_channels,
                map(lambda c: c.get_send_level(to_channel), base_channels),
            )
        )

        # reject if any send levels are not settled
        if None in list(map(lambda x: x[1], self._affected_s_dca_channels)):
            App.settings.set_status("Not synced | Try again")
            print(f"Send levels to {to_channel.identifier.short_label()} are not fully settled, yet.")

            return False

        with self._update_lock:
            self._mode = self._MODE_SEND_DCA
            self._channel_base = None
            self._channel_send = to_channel
            self._affected_s_dca_channels = affected_s_dca_channels

            # backup sends
            for channel in base_channels:
                if not channel.affected_by_s_dca:
                    channel.backup_sends()

        # set label and color from send channel
        self.set_label(f"={to_channel.label}")
        self.set_color(to_channel.color)
        self.set_mute(False)

        # initialize fader level at midpoint
        self.set_level(Level(Level.VALUE_FADER_MIDPOINT))

        return True

    def bind_master(self, base_channel: OutputChannel) -> None:
        """Copy the base channel"""
        with self._update_lock:
            self._mode = self._MODE_TRACK_MASTER_LEVEL
            self._channel_base = base_channel
            self._channel_send = None
            self._affected_s_dca_channels = []

        # set label and color from base channel
        self.set_label(f"M {base_channel.label}")
        self.set_color(base_channel.color)

        # initialize fader + mute
        self.set_level(base_channel.level)
        self.set_mute(base_channel.mute)

    def tie_to_zero(self) -> None:
        """Make the fader stick to the -inf/bottom position."""
        with self._update_lock:
            self._mode = self._MODE_TIE_TO_ZERO
            self._channel_base = None
            self._channel_send = None
            self._affected_s_dca_channels = []

        self.set_label("")
        self.set_color(Color.OFF)
        self.set_mute(False)

        self.set_level(Level(0))

    def unbind(self) -> None:
        """Reset and unbind this virtual channel."""
        with self._update_lock:
            self._mode = self._MODE_NONE
            self._channel_base = None
            self._channel_send = None
            self._affected_s_dca_channels = []

        self.set_label("[V-Ch]")
        self.set_color(Color.OFF)
        self.set_mute(True)

        self.set_level(Level(0))

    def set_level(self, level: Level, trigger_change_event: bool = True) -> bool:
        track_level_change = super(VirtualChannel, self).set_level(level, trigger_change_event)

        # Handle modes
        if track_level_change:
            if self._mode == self._MODE_TIE_TO_ZERO:
                if level > 0:
                    self.set_level(Level(0))
            elif self._mode == self._MODE_SEND_DCA and self._channel_send:
                self._apply_s_dca_values(level)
            elif self._mode == self._MODE_TRACK_SEND_LEVEL and self._channel_base and self._channel_send:
                self._channel_base.set_send_level(self._channel_send, level)
            elif self._mode == self._MODE_TRACK_MASTER_LEVEL and self._channel_base:
                self._channel_base.set_level(level)

        return track_level_change

    def set_mute(self, enabled: bool, trigger_change_event: bool = True) -> bool:
        track_mute_change = super().set_mute(enabled, trigger_change_event)

        # Handle modes
        if track_mute_change:
            if self._mode in [self._MODE_TRACK_SEND_LEVEL, self._MODE_SEND_DCA, self._MODE_TIE_TO_ZERO]:
                if enabled:
                    self.set_mute(False)
            elif self._mode == self._MODE_NONE:
                if not enabled:
                    self.set_mute(True)
            elif self._mode == self._MODE_TRACK_MASTER_LEVEL and self._channel_base:
                self._channel_base.set_mute(enabled)

        return track_mute_change

    def _apply_s_dca_values(self, level: Level) -> None:
        if level == Level(Level.VALUE_FADER_MIDPOINT):
            return

        for channel, base_level in self._affected_s_dca_channels:
            try:
                # sanity check against race conditions
                # todo: Consider moving value logic to Level entity
                reference = (Level.VALUE_OFF, Level.VALUE_FULL)[level > Level.VALUE_FADER_MIDPOINT]
                diff = (
                    (reference - base_level)
                    * (level - Level.VALUE_FADER_MIDPOINT)
                    / (reference - Level.VALUE_FADER_MIDPOINT)
                )

                # set level changes from new thread, so there is no waiting induced
                level = Level(base_level + int(diff))
                Thread(target=channel.set_send_level, args=[self._channel_send, level]).start()

                channel.mark_affected_by_s_dca(self._channel_send)

            except AttributeError:
                # protect against race conditions
                pass
