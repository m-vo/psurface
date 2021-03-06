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

    try:
        version = subprocess.check_output(["git", "describe", "--tags", "--always"]).strip().decode()
    except Exception:
        version = "unknown"

    @classmethod
    def notify(cls, message: str) -> None:
        cls.on_notify(message)
