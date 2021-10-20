import socket

from config import Config
from mido.sockets import SocketPort


class DLiveSocketPort(SocketPort):
    def __init__(self, config: Config):
        host = config.dlive_ip
        port = (51325, 51327)[config.use_auth]

        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.setblocking(True)
        connection.connect((host, port))

        SocketPort.__init__(self, host, port, connection)

        if config.use_auth:
            print("Authenticating….", end=" ")

            success = self._authenticate(config.auth_string)
            print(("OK", "FAIL")[success])

            if not success:
                raise ConnectionRefusedError("Invalid credentials")

    def send_bytes(self, byte_list: list) -> None:
        try:
            self._wfile.write(bytearray(byte_list))
            self._wfile.flush()
        except socket.error as err:
            if err.errno == 32:
                # Broken pipe. The other end has disconnected.
                self.close()

            raise IOError(err.args[1])

    def _authenticate(self, auth_string: str) -> bool:
        try:
            self._send(auth_string.encode())
            ack = self._rfile.read(6)
            return ack.decode() == "AuthOK"

        except IOError:
            return False
