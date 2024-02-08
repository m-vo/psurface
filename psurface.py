"""
 This file is part of the pSurface project. For the full copyright and license
 information, see the LICENSE file that was distributed with this source code.
"""
#!python

import logging
import sys

from app import App
from dlive.api import DLive
from dlive.connection import DLiveSocketPort
from dlive.entity import Scene
from dlive.value import TrackedValue
from dlive.virtual import LayerController
from streamdeck.ui import UI


class PSurface:
    def run(self):
        def print_help():
            print("Supported commands")
            print("------------------")
            print("  Global")
            print("    ?      Print this help")
            print("    d      Dump the internal state")
            print("    r      Perform a full resync")
            print("    s<n>   Recall scene n, e.g. 's100'")
            print("    l      Lock/unlock streamdecks'")
            print()
            print("  Mode of operation")
            print("    i<n>   Select input n, e.g. 'i42'")
            print("    o<n>   Select send/fx n, e.g. 'o3'")
            print("    m      Select mixing mode")
            print("    f      Toggle channel filter")
            print("    x      Toggle sends target (Aux/FX)")
            print()

        def print_notification(message: str):
            print(f"> ", end="")
            for m in message.split("\n"):
                print(f"{m}")

        print(f"pSurface version {App.version}\n")
        App.on_notify.append(print_notification)

        # Find streamdecks
        print("Finding devices…", end="")
        ui = UI()
        if ui.find_devices():
            print(" [OK]")

        # Establish mixrack connection
        print("Establishing connection…", end="")
        dlive = DLive(DLiveSocketPort(), DLiveSocketPort())
        print(" [OK]")

        # Init state and sync
        print("Syncing…", end="")
        dlive.sync()
        layer_controller = LayerController(dlive)
        print(" [OK]")

        # Start UI
        print("Initializing UI…", end="")
        ui.initialize_ui(dlive, layer_controller)
        print(" [OK]")

        print("\nReady for some music!\nType ? and press [Enter] for a list of commands.\n")

        # CLI control loop
        while True:
            user_input = input("")
            length = len(user_input)
            if length == 0:
                continue

            if user_input == "?":
                print_help()
                continue

            if user_input == "d":
                App.notify(dlive.__str__())
                continue

            if user_input == "r":
                App.notify("Resetting state and syncing …")
                TrackedValue.purge_all(0)
                dlive.sync()
                App.notify("Resync complete")
                continue

            if user_input == "m":
                App.notify("Select mixing mode")
                layer_controller.select_mixing_mode()
                continue

            if user_input == "f":
                App.notify("Toggle channel filter")
                layer_controller.toggle_channel_filter()
                continue

            if user_input == "x":
                App.notify("Toggle sends target")
                layer_controller.toggle_sends_target()
                continue

            if user_input == "l":
                ui.toggle_lock()
                state = ("unlocked", "locked")[ui.locked]
                App.notify(f"The streamdecks are now {state}.")

            if length < 2:
                continue

            try:
                number = int(user_input[1:])
            except ValueError:
                continue

            if user_input[0] == "s" and 0 < number <= 500:
                scene = Scene(number - 1)
                App.notify(f"Recall scene {scene}")
                dlive.change_scene(scene)
                continue

            if user_input[0] == "i" and 0 < number <= len(channels := dlive.input_channels):
                channel = channels[number - 1]
                App.notify(f"Select input channel {channel.short_label()}")
                layer_controller.select_input(channel)
                continue

            if user_input[0] == "o" and 0 < number <= len(channels := dlive.output_channels):
                channel = channels[number - 1]
                App.notify(f"Select output channel {channel.short_label()}")
                layer_controller.select_output(channel)
                continue


def main():
    class Unbuffered(object):
        def __init__(self, stream):
            self.stream = stream

        def write(self, data):
            self.stream.write(data)
            self.stream.flush()

        def writelines(self, datas):
            self.stream.writelines(datas)
            self.stream.flush()

        def __getattr__(self, attr):
            return getattr(self.stream, attr)

    # Make sure console output is not buffered under windows
    import sys

    sys.stdout = Unbuffered(sys.stdout)

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
