from typing import Optional

import yaml


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
        data = self._data["streamdeck"]["devices"]
        self._enforce_keys(data, ["system", "input", "output"], "streamdeck.devices")

        return data

    @property
    def control_tracking(self) -> dict:
        data = self._data["control"]["tracking"]
        self._enforce_keys(
            data,
            [
                "number_of_inputs",
                "number_of_mono_aux",
                "number_of_stereo_aux",
                "number_of_mono_fx",
                "number_of_stereo_fx",
                "virtual_start",
                "feedback_matrix",
            ],
            "control.tracking",
        )

        # use zero based offset internally
        for key in ["virtual_start", "feedback_matrix"]:
            data[key] -= 1

        return data

    @property
    def control_scenes(self) -> dict:
        data = self._data["control"]["scenes"]
        self._enforce_keys(
            data,
            ["mixing_start", "virtual_left_start", "virtual_right", "sends", "custom_aux", "custom_fx"],
            "control.scenes",
        )

        # use zero based offset internally
        for key in data:
            data[key] -= 1

        return data

    @staticmethod
    def _enforce_keys(data: dict, keys: list, group: str) -> None:
        for key in keys:
            if key not in data:
                raise RuntimeError(f"Invalid config - missing config key: '{key}' in '{group}'")

        pass
