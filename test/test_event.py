"""
 This file is part of the pSurface project. For the full copyright and license
 information, see the LICENSE file that was distributed with this source code.
"""
import unittest

from common.event import Event


class TestEvent(unittest.TestCase):
    def test_register_and_fire_events(self) -> None:
        executed = ""

        def on_execute(value: str) -> None:
            nonlocal executed
            executed += value

        test_event = Event()

        test_event.append(on_execute)
        test_event.append(on_execute)

        self.assertEqual(executed, "")
        test_event("foo")
        self.assertEqual(executed, "foofoo")
