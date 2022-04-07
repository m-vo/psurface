import sys
from copy import copy
from typing import Optional, List

import yaml

from dlive.entity import Color


class Config:
    def __init__(self, config_file: str):
        with open(config_file, "r") as stream:
            self._data = yaml.safe_load(stream)

    @property
    def dlive_ip(self) -> str:
        return self._data["dlive"]["ip"]

    @property
    def auth(self) -> Optional[str]:
        # self._data["dlive"]["user_profile"] + self._data["_dlive"]["user_password"]
        return None

    @property
    def midi_bank_offset(self) -> int:
        # use zero based offset internally
        return int(self._data["dlive"]["midi_bank_offset"] - 1)

    @property
    def streamdeck_devices(self) -> dict:
        data = copy(self._data["ui"]["streamdeck_devices"])
        self._enforce_keys(data, ["system", "input", "output"], "streamdeck.devices")

        return data

    @property
    def input_colors(self) -> List[Color]:
        return self._parse_color_values(self._data["ui"]["color_listing"]["input"], "ui.color_listing.input")

    @property
    def output_colors(self) -> List[Color]:
        return self._parse_color_values(self._data["ui"]["color_listing"]["output"], "ui.color_listing.output")

    @property
    def control_tracking(self) -> dict:
        data = copy(self._data["control"]["tracking"])
        self._enforce_keys(
            data,
            [
                # inputs
                "number_of_inputs",
                "talk_to_monitor",
                "talk_to_stage",
                # aux
                "number_of_mono_aux",
                "mono_aux_start",
                "number_of_stereo_aux",
                # external fx
                "number_of_external_fx",
                "external_fx_start",
                # fx
                "number_of_mono_fx",
                "number_of_stereo_fx",
                # other
                "virtual_start",
                "feedback_matrix",
            ],
            "control.tracking",
        )

        # use zero based offset internally
        for key in [
            "talk_to_monitor",
            "talk_to_stage",
            "mono_aux_start",
            "external_fx_start",
            "virtual_start",
            "feedback_matrix",
        ]:
            data[key] -= 1

        return data

    @property
    def control_scenes(self) -> dict:
        data = copy(self._data["control"]["scenes"])
        self._enforce_keys(
            data,
            ["mixing_start", "virtual_left_start", "virtual_right", "sends", "custom_aux", "custom_fx", "custom_util"],
            "control.scenes",
        )

        # use zero based offset internally
        for key in data:
            data[key] -= 1

        # todo: directly validate and return a List[Scene] instead
        return data

    @staticmethod
    def _enforce_keys(data: dict, keys: list, group: str) -> None:
        for key in keys:
            if key not in data:
                raise ConfigError(f"Missing config key: '{key}' in '{group}'.")

    @staticmethod
    def _parse_color_values(input: str, group: str) -> List[Color]:
        try:
            return [Color[value.strip().upper()] for value in input.split(",")]
        except KeyError:
            raise ConfigError(f"Invalid color '{sys.exc_info()[1]}' in {group}.")


class ConfigError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(f"Config error: {message}")
