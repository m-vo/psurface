import yaml


class Config:
    def __init__(self, config_file: str):
        with open(config_file, "r") as stream:
            self._data = yaml.safe_load(stream)

    @property
    def dlive_ip(self):
        return self._data["dlive"]["ip"]

    @property
    def use_auth(self):
        return bool(self._data["dlive"]["use_auth"])

    @property
    def auth_string(self):
        return self._data["dlive"]["user_profile"] + self._data["_dlive"]["user_password"]

    @property
    def midi_out_port_name(self):
        return self._data["midi"]["out"]["port_name"]

    @property
    def midi_in_port_name(self):
        return self._data["midi"]["in"]["port_name"]

    @property
    def midi_bank_offset(self):
        # use zero based offset internally
        return self._data["dlive"]["midi_bank_offset"] - 1

    @property
    def outbound_midi_channel(self):
        # use zero based offset internally
        return self._data["midi"]["out"]["channel"] - 1

    @property
    def control_aux_scene_start(self):
        # use zero based offset internally
        return self._data["control"]["aux"]["scene_start"] - 1

    @property
    def control_aux_amount(self):
        # use zero based offset internally
        return self._data["control"]["aux"]["amount"]

    @property
    def streamdeck_devices(self):
        return self._data["streamdeck"]["devices"]
