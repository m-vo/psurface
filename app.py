"""
 This file is part of the pSurface project. For the full copyright and license
 information, see the LICENSE file that was distributed with this source code.
"""
import subprocess

from common.event import AsyncEvent
from common.scheduler import Scheduler
from config import Config
from streamdeck.settings import GlobalSettings


class App:
    config = Config("config.yaml")
    scheduler = Scheduler()
    settings = GlobalSettings()
    on_notify = AsyncEvent()
    on_lock = AsyncEvent()
    on_unlock = AsyncEvent()

    try:
        version = subprocess.check_output(["git", "describe", "--tags", "--always"]).strip().decode()
    except Exception:
        version = "unknown"

    @classmethod
    def notify(cls, message: str) -> None:
        cls.on_notify(message)

    @classmethod
    def lock(cls) -> None:
        cls.on_lock()

    @classmethod
    def unlock(cls) -> None:
        cls.on_unlock()
