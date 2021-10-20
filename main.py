import sys

from common.session import Session, VirtualChannel, LayerController
from config import Config
from dlive.connection import DLiveSocketPort
from dlive.encoding import Encoder, Decoder
from streamdeck.ui import DeckUI


class PSurface:
    def __init__(self, config: Config):
        # We're using separate connections so that we can monitor our own
        # commands. The mix rack would for instance not respond with a program
        # change message on the connection where a scene recall was issued
        self._dlive_out = DLiveSocketPort(config)
        self._dlive_in = DLiveSocketPort(config)

        self._encoder = Encoder(config.midi_bank_offset)
        self._decoder = Decoder(config.midi_bank_offset)
        self._session = Session(self._decoder, self._encoder)

        self._layer_controller = LayerController(self._session)
        self._ui = DeckUI(
            config.streamdeck_devices, self._session, self._layer_controller
        )

    def run(self):
        self._encoder.dispatch.append(self._dlive_in.send_bytes)
        self._session.track_changes()

        self._ui.init()

        # th = threading.Thread(target=self.threaded)
        # th.start()

        for message in self._dlive_out:
            self._decoder.feed_message(message)

    # def threaded(self):
    #     time.sleep(1)
    #     print("creating vch")
    #     vch = VirtualChannel(ChannelIdentifier(Bank.BANK_MONO_AUX, 8), self._decoder, self._encoder)
    #     vch.init()
    #
    #     time.sleep(10)
    #     print("binding vch")
    #     vch.bind_send(self._session.input_channels[0], self._session.aux_channels[0])


def main():
    PSurface(Config("config.yaml")).run()


if __name__ == "__main__":
    if len(sys.argv) > 0 and "--dev" in sys.argv:
        main()

    while True:
        try:
            main()
        except:
            # ignore + restart
            print("Unexpected error:", sys.exc_info()[0])

            pass
