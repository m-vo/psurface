from typing import Callable, Dict, Tuple, Optional

from dlive.entity import Channel


class FragmentRenderer:
    def __init__(self):
        self._key_and_action_by_identifier_hash: Dict[int, Tuple[int, Callable]] = {}
        self._channels_by_key = {}

    def add_fragment(self, key: int, channel: Channel, render_action: Callable) -> None:
        self._key_and_action_by_identifier_hash[channel.identifier.__hash__()] = (
            key,
            render_action,
        )
        self._channels_by_key[key] = channel

        pass

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
