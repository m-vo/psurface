"""
 This file is part of the pSurface project. For the full copyright and license
 information, see the LICENSE file that was distributed with this source code.
"""
import re
import typing
from enum import Enum


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

    OFF = 0x00
    RED = 0x01
    GREEN = 0x02
    YELLOW = 0x03
    BLUE = 0x04
    PURPLE = 0x05
    LIGHT_BLUE = 0x06
    WHITE = 0x07

    _rgb = {
        0x00: (0x20, 0x20, 0x20),
        0x01: (0xFF, 0x00, 0x00),
        0x02: (0x00, 0xFF, 0x00),
        0x03: (0xFF, 0xFF, 0x00),
        0x04: (0x00, 0x00, 0xFF),
        0x05: (0xAA, 0x00, 0xAA),
        0x06: (0x00, 0xFF, 0xFF),
        0x07: (0xFF, 0xFF, 0xFF),
    }

    def __str__(self):
        return self.name

    @property
    def rgb(self):
        return self._rgb.value[self.value]


class Level(int):
    """
    Channel or send level. Values have a linear dependency to dBu values
    and a logarithmic dependency to physical fader positions.
    """

    VALUE_FULL = 0x7F
    VALUE_0DB = 0x6B
    VALUE_OFF = 0x00
    VALUE_FADER_MIDPOINT = 0x58

    # trim base value for effect sends
    VALUE_AUDIBLE_MINIMUM = 0x43

    def __new__(cls, value: int = 0):
        return int.__new__(cls, max(min(Level.VALUE_FULL, value), Level.VALUE_OFF))

    def __str__(self) -> str:
        value = int(self)

        if value <= 1:
            return "-inf"

        dbu = ((value - 17) * 55 / 110) - 45

        return "{0:+}".format(int(dbu))


class Scene(int):
    def with_offset(self, offset: int) -> "Scene":
        return Scene(self + offset)

    def __str__(self) -> str:
        return "s{}".format(int(self) + 1)


class Label(str):
    def with_bind_send_prefix(self) -> "Label":
        return Label("@" + self)

    def with_bind_master_prefix(self) -> "Label":
        return Label("M" + self)

    @property
    def has_name(self) -> bool:
        return not re.match(r"^[0-9]*$", self)

    @property
    def is_suppressed_in_overview(self) -> bool:
        return len(self) > 0 and self[0] == "!"

    def __new__(cls, value: str = ""):
        return str.__new__(cls, value[:8].strip())


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
            self.canonical_index + 1,
            self.midi_bank_offset,
            self.midi_channel_index,
        )

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        return other is not None and (self._bank, self._canonical_index) == (other._bank, other._canonical_index)

    def __hash__(self):
        return hash((self._bank, self._canonical_index))
