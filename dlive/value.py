"""
 This file is part of the pSurface project. For the full copyright and license
 information, see the LICENSE file that was distributed with this source code.
"""
from collections import deque
from threading import Lock
from time import time
from typing import Callable, Deque, Generic, List, Optional, Set, Tuple, TypeVar

from common.event import Event

T = TypeVar("T")


class TrackedValue(Generic[T]):
    all_instances: List["TrackedValue"] = []

    def __init__(self, on_update_idle: Optional[Callable] = None) -> None:
        TrackedValue.all_instances.append(self)

        self._update_lock = Lock()

        self._value: Optional[T] = None
        self._last_resolve: Optional[time] = None
        self._requests: Deque[Tuple[T, time]] = deque()

        self.on_update_idle: Event = Event("tracked_value.on_update_idle")
        self.on_resolve: Event = Event("tracked_value.on_resolve")

        if on_update_idle is not None:
            self.on_update_idle.append(on_update_idle)

    def resolve(self, value: T) -> int:
        """
        Resolve a value and notifies on change. Returns the number of requests
        that are queued after resolving the current value.
        """
        first_matched_value = None
        first_matched_time = None

        with self._update_lock:
            if update := (self._value != value):
                self._value = value

            self._last_resolve = time()
            first_matched_index = None

            for index, (rvalue, rtime) in enumerate(self._requests):
                if rvalue == value:
                    (first_matched_index, first_matched_value, first_matched_time) = (index, rvalue, rtime)
                    break

            if first_matched_index is not None:
                del self._requests[first_matched_index]

            remaining_requests = len(self._requests)

        # notify about changes after releasing lock
        if update:
            if first_matched_value:
                self.on_resolve(first_matched_value, first_matched_time)

            if remaining_requests == 0:
                self.on_update_idle(value)

        return remaining_requests

    def request(self, value: T) -> (int, bool):
        """
        Queues a new request if requested value is not already settled or the
        last unfulfilled request needs the same value. Returns the number of
        requests that waiting (including the current if applicable) as well and
        whether the request was queued or not.
        """
        with self._update_lock:
            num_requests = len(self._requests)
            if num_requests == 0:
                # if no requests are queued and the current value is already
                # the requested one, do nothing
                if self._value == value:
                    return 0, False
            elif self._requests[-1][0] == value:
                # if last unresolved request matches value, just update the
                # request time
                self._requests[-1] = (value, time())
                return num_requests, False

            self._requests.append((value, time()))
            return num_requests + 1, True

    def purge(self, max_age: int) -> int:
        """
        Drop all requests that are older than the given max age. Returns the
        number of purged items.
        """
        with self._update_lock:
            if (before := len(self._requests)) == 0:
                return 0

            now = time()
            self._requests = deque([r for r in self._requests if r[1] - now <= max_age])

            return before - len(self._requests)

    @property
    def value(self) -> Optional[T]:
        return self._value

    @property
    def last_updated(self) -> Optional[time]:
        return self._last_resolve

    @property
    def synced(self) -> bool:
        return self._last_resolve is not None

    def __str__(self) -> str:
        return f"{(self.value, '?')[self.value is None]}{('', ' […]')[len(self._requests) > 0]}"

    @classmethod
    def purge_all(cls, max_age: int) -> int:
        return sum(map(lambda i: i.purge(max_age), cls.all_instances))


class ImmediateValue(TrackedValue):
    def resolve(self, value: T) -> int:
        self._update_and_notify(value)
        return 0

    def request(self, value: T) -> (int, bool):
        self._update_and_notify(value)
        return 0, True

    def _update_and_notify(self, value: T) -> None:
        with self._update_lock:
            if update := (self._value != value):
                self._value = value
            self._last_resolve = last_resolve = time()

        if update:
            self.on_resolve(value, last_resolve)
            self.on_update_idle(value)
