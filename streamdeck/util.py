from collections import OrderedDict
from queue import Queue
from threading import Lock, Thread
from typing import List, Callable, Dict, Optional

from dlive.api import DLive
from dlive.entity import ChannelIdentifier, Color
from dlive.virtual import LayerController


class RenderQueue(Queue):
    def start_worker(self):
        renderer = Thread(target=self._dispatch)
        renderer.start()

    def put_handler(self, handler: Callable, key: int) -> None:
        with self.mutex:
            drop_existing = None
            for index, (h, k) in enumerate(self.queue):
                if k == key:
                    drop_existing = index
                    break
            if drop_existing is not None:
                del self.queue[index]

        self.put((handler, key))

    def _dispatch(self):
        while True:
            handler, key = self.get()
            handler(key)
            self.task_done()


class ChannelRenderer:
    def __init__(self, dlive: DLive, layer_controller: LayerController, length: int = 32) -> None:
        self._dlive = dlive
        self._length = length

        self._layout_lock = Lock()
        self._handlers: Dict[ChannelIdentifier, Callable] = {}
        self._display_map: List[Optional[ChannelIdentifier]] = [None] * length
        self._render_queue: RenderQueue = RenderQueue()

        self._render_queue.start_worker()

        self._selected_channel: [Optional[ChannelIdentifier]] = None
        layer_controller.on_selection_changed.append(self._on_update_channel_selection)

    def _on_update_color(self, channel: ChannelIdentifier, _) -> None:
        if channel in self._display_map:
            self._render_queue.put_handler(self._handlers[channel], self._display_map.index(channel))

    def _on_update_label(self, channel: ChannelIdentifier, _) -> None:
        if channel in self._display_map:
            self._render_queue.put_handler(self._handlers[channel], self._display_map.index(channel))

    def _on_update_mute(self, channel: ChannelIdentifier, _) -> None:
        if channel in self._display_map:
            self._render_queue.put_handler(self._handlers[channel], self._display_map.index(channel))

    def _on_update_level(self, channel: ChannelIdentifier, _) -> None:
        if channel in self._display_map:
            self._render_queue.put_handler(self._handlers[channel], self._display_map.index(channel))

    def _on_update_channel_selection(self, channel: Optional[ChannelIdentifier]) -> None:
        def update_if_affected(ch: Optional[ChannelIdentifier]):
            if ch is not None and ch in self._display_map:
                self._render_queue.put_handler(self._handlers[ch], self._display_map.index(ch))

        with self._layout_lock:
            if channel not in self._display_map:
                if self._selected_channel is not None:
                    update_if_affected(self._selected_channel)
                    self._selected_channel = None
                    return

            update_if_affected(channel)
            if channel != self._selected_channel:
                update_if_affected(self._selected_channel)
                self._selected_channel = channel

    def add_channel(self, channel: ChannelIdentifier, render_handler: Callable) -> None:
        self._handlers[channel] = render_handler

    def get_channel(self, key) -> Optional[ChannelIdentifier]:
        return self._display_map[key]

    def enable_static_strategy(self) -> None:
        self._display_map = list(self._handlers.keys())

        for key, channel in enumerate(self._display_map):
            self._render_queue.put_handler(self._handlers[channel], key)

        # Track mute changes to channels
        self._dlive.on_update_mute.append(self._on_update_mute)

    def enable_color_group_strategy(self, colors: List[Color], default_handler: Callable) -> None:
        def execute():
            self._apply_color_group_strategy(colors, default_handler)

        def on_change(channel=None, value=None):
            if channel in self._handlers.keys():
                execute()

        # Execute once and for all changes that affect display/ordering
        execute()
        self._dlive.on_update_color.append(on_change)
        self._dlive.on_update_label.append(on_change)

        # Track changes to channels
        self._dlive.on_update_color.append(self._on_update_color)
        self._dlive.on_update_label.append(self._on_update_label)
        self._dlive.on_update_mute.append(self._on_update_mute)
        self._dlive.on_update_level.append(self._on_update_level)

    def _apply_color_group_strategy(self, colors: List[Color], default_handler: Callable) -> None:
        color_groups: OrderedDict[Color, List[ChannelIdentifier]] = OrderedDict(map(lambda c: (c, []), colors))

        for channel in self._handlers.keys():
            if not color_groups.get(color := self._dlive.get_color(channel), None) is not None:
                continue

            label = self._dlive.get_label(channel)
            if label.has_name and not label.is_suppressed_in_overview:
                color_groups[color].append(channel)

        # build a display map
        def pack_channels(avoid_break: bool = True, leave_space: bool = True):
            _map: List[Optional[ChannelIdentifier]] = []

            for group in color_groups.values():
                space_8 = 8 - len(_map) % 8
                length = len(group)

                if avoid_break and 8 >= length > space_8:
                    _map += [None] * space_8

                for ch in group:
                    _map.append(ch)

                if leave_space and length > 0 and len(_map) % 8 != 0:
                    _map += [None]

            if len(_map) > self._length:
                if not avoid_break and not leave_space:
                    return _map[: self._length]

                return False

            return _map

        display_map = (
            pack_channels() or pack_channels(leave_space=False) or pack_channels(avoid_break=False, leave_space=False)
        )
        display_map += [None] * (self._length - len(display_map))

        # update affected channels
        with self._layout_lock:
            for key in range(self._length):
                if self._display_map[key] != display_map[key]:
                    if (channel := display_map[key]) is not None:
                        self._render_queue.put_handler(self._handlers[channel], key)
                    else:
                        self._render_queue.put_handler(default_handler, key)

            self._display_map = display_map
