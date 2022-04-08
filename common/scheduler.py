"""
 This file is part of the pSurface project. For the full copyright and license
 information, see the LICENSE file that was distributed with this source code.
"""
from datetime import datetime, timedelta
from typing import Callable

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers import SchedulerNotRunningError
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger


class Scheduler:
    _TIMEZONE = "Europe/Berlin"

    def __init__(self):
        self._scheduler = BackgroundScheduler(timezone=self._TIMEZONE)
        self._scheduler.start()

    def __del__(self):
        try:
            self._scheduler.shutdown(wait=False)
        except SchedulerNotRunningError:
            pass

    def execute_interval(self, name: str, seconds_delay: float, handler: Callable, args=None) -> None:
        self._scheduler.add_job(
            handler,
            "interval",
            args,
            seconds=seconds_delay,
            id=name,
            replace_existing=True,
        )

    def execute_delayed(self, name: str, seconds_delay: float, handler: Callable, args=None) -> None:
        delta = datetime.now() + timedelta(seconds=seconds_delay)

        self._scheduler.add_job(
            handler,
            DateTrigger(delta, timezone=self._TIMEZONE),
            args,
            id=name,
            replace_existing=True,
        )

    def cancel(self, name: str) -> bool:
        try:
            self._scheduler.remove_job(name)
        except JobLookupError:
            return False

        return True
