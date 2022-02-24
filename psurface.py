#!python

import logging
import os
import sys
import time

from app import App
from dlive.connection import DLiveSocketPort
from dlive.encoding import Decoder, Encoder
from state.layers import LayerController
from state.session import Session
from streamdeck.ui import DeckUI


class PSurface:
    def __init__(self):
        def print_status() -> None:
            print(App.settings.status)

        App.settings.status_changed_event.append(print_status)

        # Internal state
        self._encoder = Encoder()
        self._decoder = Decoder()
        self._session = Session(self._decoder, self._encoder)
        self._layer_controller = LayerController(self._session)

        # Connect to decks
        App.settings.set_status("Finding decks…")
        self._ui = DeckUI(self._session, self._layer_controller)

        # We're using separate connections so that we can monitor our own
        # commands. The mix rack would for instance not respond with a program
        # change message on the connection where a scene recall was issued
        App.settings.set_status("Connecting to mixrack…")
        self._dlive_out = DLiveSocketPort()
        self._dlive_in = DLiveSocketPort()

    def run(self):
        self._encoder.dispatch.append(self._dlive_in.send_bytes)
        self._session.track_changes()

        # wait some time until the internal state has settled before initializing event bound ui
        App.scheduler.execute_delayed("run_ui", App.config.timing["ui_startup_delay"], self._ui.init)

        for message in self._dlive_out:
            self._decoder.feed_message(message)


def main():
    PSurface().run()


if __name__ == "__main__":
    if len(sys.argv) > 0 and "--dev" in sys.argv:
        print(sys.executable)

        main()

    else:
        # run; log and restart in case of an error
        try:
            main()

        except:
            print("\n\n:-(\n")
            print(sys.exc_info()[1])

            logging.basicConfig(
                format="%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S", filename="error.log"
            )

            logging.exception("PSurface crashed")
