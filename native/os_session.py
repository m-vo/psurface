"""
 This file is part of the pSurface project. For the full copyright and license
 information, see the LICENSE file that was distributed with this source code.
"""
import ctypes
import platform
import subprocess

from app import App
from common.event import AsyncEvent

os_is_windows = platform.system() == "Windows"


class OSSession:
    def __init__(self):
        self.on_lock: AsyncEvent = AsyncEvent("os.session.on_lock")
        self.on_unlock: AsyncEvent = AsyncEvent("os.session.on_unlock")

        self._lock_state = False

    def listen(self) -> None:
        if not os_is_windows:
            return

        def _check_os_session_lock() -> None:
            lock_state = "LogonUI.exe" in str(subprocess.check_output("TASKLIST"))

            if self._lock_state == lock_state:
                return

            self._lock_state = lock_state

            if lock_state:
                self.on_lock()
            else:
                self.on_unlock()

        App.scheduler.execute_interval("check_os_session_lock", 2.0, _check_os_session_lock)

    @staticmethod
    def lock() -> None:
        if os_is_windows:
            ctypes.windll.user32.LockWorkStation()

    @staticmethod
    def unlock() -> None:
        if os_is_windows:
            ctypes.windll.user32.UnlockWorkStation()
