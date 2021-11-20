from common.scheduler import Scheduler
from config import Config
from streamdeck.settings import GlobalSettings


class App:
    config = Config("config.yaml")
    scheduler = Scheduler()
    settings = GlobalSettings()
