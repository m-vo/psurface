import subprocess
import time

from common.event import Event
from common.scheduler import Scheduler
from config import Config
from streamdeck.settings import GlobalSettings


class App:
    config = Config("config.yaml")
    scheduler = Scheduler()
    settings = GlobalSettings()

    try:
        version = subprocess.check_output(["git", "describe", "--tags", "--always"]).strip().decode()
    except Exception:
        version = "unknown"

    # time bound data
    _last_inbound_data: float = 0
    _inbound_data_state: bool = False
    inbound_data_changed_event = Event()

    @staticmethod
    def tick_inbound_data() -> None:
        App._last_inbound_data = time.time()

    @staticmethod
    def monitor_inbound_data() -> None:
        def monitor() -> None:
            has_data = (time.time() - App._last_inbound_data) < 0.5

            if has_data != App._inbound_data_state:
                App._inbound_data_state = has_data
                App.inbound_data_changed_event(has_data)

        App.scheduler.execute_interval("monitor_inbound_data", 0.2, monitor)
