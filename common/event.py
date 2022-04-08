"""
 This file is part of the pSurface project. For the full copyright and license
 information, see the LICENSE file that was distributed with this source code.
"""
from queue import Queue
from threading import Thread
from typing import Optional


class Event(list):
    def __init__(self, name: Optional[str] = None) -> None:
        self._name = name
        super().__init__()

    def __call__(self, *args, **kwargs):
        for f in self:
            f(*args, **kwargs)

    def __repr__(self):
        return f"Event {self._name} ({list.__repr__(self)})"


class AsyncEvent(Event):
    def __init__(self, name: Optional[str] = None) -> None:
        self._queue = Queue()

        worker = Thread(target=self._worker)
        worker.start()

        super().__init__(name)

    def __call__(self, *args, **kwargs):
        self._queue.put((args, kwargs))

    def _worker(self) -> None:
        while True:
            args, kwargs = self._queue.get()
            for f in self:
                f(*args, **kwargs)

            self._queue.task_done()

    def __repr__(self):
        return f"Async{super.__repr__(self)}"
