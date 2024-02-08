# pSurface

Custom remote solution for a Allen&Heath *dLive* mixrack/director session using *IP8* and *Elgato Stream Deck*
controllers.

#### Use at your own risk! ⚠

If you want to use this software, keep in mind that functions are strongly opinionated and neither support nor a BC
promise for upcoming versions is given.

![](docs/psurface.jpg)

## Getting started

### Intended hardware setup

* 2x *Allen&Heath IP8* controller
* 2x *Elgato Stream Deck XL* (32 buttons)
* 1x *Elgato Stream Deck* (15 buttons)
* Computer running *dLive Director*
* Computer running *pSurface* (can be the same)

One of the large stream decks is used to display input channels (we call it "left" or "inputs" deck), the other is used
to display AUX/FX buses (we call it "right" or "outputs" deck). The small stream deck (the "system" deck)
is used to select modes, filters and custom scenes.

You can start the software without some/any stream deck connected - a simulator is then started showing the missing
devices on the screen. Alternatively, use the command line interface for testing and debugging.

### Get the software going
#### Prerequisites
Make sure you have the following installed:
* `Python 3.8` + `pipenv`
* `git`
* `LibUSB HIDAPI`, see guide by [abcminiuser's excellent python-elgato-stream library][1]
* If on Windows, you'll also need to install the [Visual C++ Redistributable libraries][2]

#### Download + install
1) Clone the repository
2) Run `pipenv sync` to install the requirements
3) Create a `config.yaml` file; use the provided dist file as a starting point: `cp config.yaml.dist config.yaml`
4) Run `pipenv run python psurface.py` to start the application. If on Windows, execute  `run_loop.bat` instead.

Make sure to at least adjust the mixrack IP and stream deck serial numbers in the `config.yaml`.

### Load the default showfile

You can use [this basic showfile](docs/pSurface.tar.gz) that already includes all needed scenes and IP-8 mappings as
well as some other defaults. Be prepared for quite some magic due to the heavy use of virtualization…

The basic idea is: there is a "conventional" scene for each bank of inputs (the mixing layers) as well as a few special
scenes that assign the 16 "virtual channels" (input channels read and controlled by the software) to the IP controllers.
When then physically moving faders on one of these virtual channels, the software will read the data and - according to
the currently selected mode - set levels/send-levels for the 'real' channels. Same goes for the mute button. This way
we're saving a huge amount of scenes that would need to be created and can support things like dynamic filtering
("spill").

In case you are wondering why we are using 6 "virtual channel scenes" for the left IP8 and only one for the right IP8:
This is, because you can use the left IP8's soft buttons to switch banks, and we want the LEDs to be lit accordingly.
All 6 scenes basically contain the same data, including scene recall assignments for these 6 scenes on the soft buttons.
So loading the 4th scene will make the 4th button lit and so on. The software will call the scene for the right IP8 and
one for the left directly after each other when entering a virtual channel mode.

### Basic usage

#### Overview

- Press the <img src="assets/home.png" width="20px" style="vertical-align:top"> button to enter mixing mode; use the
  left IP8 soft buttons to select banks of inputs.
- Press any button on the left deck, to select *"sends on fader"* for this channel, use the `AUX/FX` button on the
  system deck to toggle between showing sends for AUX or FX buses.
- Press any button on the right deck to select *"inverse sends on fader"* for this bus. Use the left IP8 soft buttons to
  select the banks of inputs. The 16th channel tracks the selected bus master level/mute state. We use a dynamically
  controlled matrix channel to route signal in this virtual channel so that the IP8's meter is showing signal of the
  selected bus.
- Press the <img src="assets/filter.png" width="20px" style="vertical-align:top"> button to toggle channel filtering
  on/off. When in any 'sends on fader' mode, this will only show those channels, that have a send-level > 0 set and
  group them on one layer.
- Hold the <img src="assets/direct.png" width="20px" style="vertical-align:top"> button and press any input/output to
  mute/unmute the channel.
- Use the <img src="assets/brightness.png" width="20px" style="vertical-align:top"> button to adjust the deck's
  brightness.
- Use the two <img src="assets/mic.png" width="20px" style="vertical-align:top">buttons to mute/unmute the configured
  talkback channels.
- There are more buttons on the system deck, that simply call custom scenes (`DCA`, `AUX`, `GRP`, …) - mostly for quick
  access to the 'select button' of the respective channels.

#### Which channels are displayed on the decks and how?

Channels that have a name set, that does not start with a `!` are displayed on the decks. With "have a name set", we
mean a label that is not empty or only contains a number. Here are some examples:

* ` ` &rarr; not shown
* `12` &rarr; not shown
* `Snare` &rarr; shown
* `!Snare` &rarr; not shown

Channels are grouped by color. You can configure the order for the left/right deck in the `config.yaml`. Channels with
colors not mentioned in the config, won't be displayed.

[1]: https://python-elgato-streamdeck.readthedocs.io/en/stable/pages/backend_libusb_hidapi.html
[2]: https://docs.microsoft.com/en-GB/cpp/windows/latest-supported-vc-redist?view=msvc-170