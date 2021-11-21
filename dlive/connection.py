import socket
from threading import Lock

from mido.sockets import SocketPort

from app import App


class DLiveSocketPort(SocketPort):
    def __init__(self):
        self._io_lock = Lock()

        auth = App.config.auth
        host = App.config.dlive_ip
        port = (51325, 51327)[auth is not None]

        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.setblocking(True)
        connection.connect((host, port))

        SocketPort.__init__(self, host, port, connection)

        # todo: auth
        if auth:
            print("Authenticating….", end=" ")

            success = self._authenticate(auth)
            print(("OK", "FAIL")[success])

            if not success:
                raise ConnectionRefusedError("Invalid credentials")

    def send_bytes(self, byte_list: list) -> None:
        try:
            with self._io_lock:
                self._wfile.write(bytearray(byte_list))
                self._wfile.flush()
        except socket.error as err:
            if err.errno == 32:
                # Broken pipe. The other end has disconnected.
                self.close()

            raise IOError(err.args[1])

    def _authenticate(self, auth_string: str) -> bool:
        try:
            with self._io_lock:
                self._send(auth_string.encode())
                ack = self._rfile.read(6)
                return ack.decode() == "AuthOK"

        except IOError:
            return False
