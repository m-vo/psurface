from threading import Thread
from typing import Callable, Dict, List, Optional, Tuple

from dlive.entity import Channel, Color


class FragmentRenderer:
    def __init__(self):
        self._key_and_action_by_identifier_hash: Dict[int, Tuple[int, Callable]] = {}
        self._channels_by_key = {}

    def reset(self) -> None:
        self._key_and_action_by_identifier_hash = {}
        self._channels_by_key = {}

    def add_fragment(self, key: int, channel: Channel, render_action: Callable) -> None:
        self._key_and_action_by_identifier_hash[channel.identifier.__hash__()] = (
            key,
            render_action,
        )
        self._channels_by_key[key] = channel

    def update(self, channel: Channel) -> None:
        hash_index = channel.identifier.__hash__()

        if hash_index not in self._key_and_action_by_identifier_hash:
            return

        key, action = self._key_and_action_by_identifier_hash[hash_index]
        self._execute_action(action, key)

    def get_channel(self, key: int) -> Optional[Channel]:
        if key not in self._channels_by_key:
            return None

        return self._channels_by_key[key]

    def _execute_action(self, action: Callable, key: int) -> None:
        action(key, self._channels_by_key[key])

        # action_thread = Thread(target=action, args=(key, self._channels_by_key[key]))
        # action_thread.start()


class ChannelPacking:
    @staticmethod
    def get_color_packing(channels: List[Channel]) -> Dict[int, Channel]:
        channels_by_color = {
            Color.BLUE: [],
            Color.LIGHT_BLUE: [],
            Color.YELLOW: [],
            Color.RED: [],
            Color.GREEN: [],
            Color.PURPLE: [],
        }

        for channel in channels:
            if channel.color not in [Color.OFF, Color.WHITE] and channel.is_visible:
                channels_by_color[channel.color].append(channel)

        def pack(avoid_break: bool = True, leave_space: bool = True) -> Dict[int, Channel]:
            index = 0
            pack_map: Dict[int, Channel] = {}

            for channel_block in channels_by_color.values():
                space_8 = 8 - index % 8
                length = len(channel_block)

                if avoid_break and 8 >= length > space_8:
                    index += space_8

                for channel in channel_block:
                    pack_map[index] = channel
                    index += 1

                if leave_space and length > 0 and index % 8 != 0:
                    index += 1

            return pack_map

        # avoid bank breaks
        pack_map = pack()

        if len(pack_map) == 0:
            return pack_map

        # fall back to not leaving space
        if max(pack_map) > 32:
            pack_map = pack(leave_space=False)

        # fall back to dense packing
        if max(pack_map) > 32:
            pack_map = pack(avoid_break=False, leave_space=False)

        return pack_map

    @staticmethod
    def get_type_packing(channels: List[Channel]) -> Dict[int, Channel]:
        channels_by_type = {True: [], False: []}

        for channel in channels:
            if not channel.is_visible or (feed_type := channel.identifier.is_mono_feed) is None:
                continue

            channels_by_type[feed_type].append(channel)

        def pack(leave_space: bool = True) -> Dict[int, Channel]:
            index = 0
            pack_map: Dict[int, Channel] = {}

            for channel_block in channels_by_type.values():
                for channel in channel_block:
                    pack_map[index] = channel
                    index += 1

                if leave_space and index % 8 != 0:
                    index += 1

            return pack_map

        # avoid bank breaks
        pack_map = pack()

        if len(pack_map) == 0:
            return pack_map

        # fall back to not leaving space
        if max(pack_map) > 8:
            pack_map = pack(leave_space=False)

        return pack_map
