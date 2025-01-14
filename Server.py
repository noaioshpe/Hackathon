import socket
import threading
import time
from common import format_offer_message, MAGIC_COOKIE, OFFER_MESSAGE_TYPE


class Server:
    def __init__(self, udp_port, tcp_port):
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.running = False
        self.udp_socket = None
        self.tcp_socket = None

    def start_server(self):
        self.running = True
        self._start_udp_broadcast()
        self._start_tcp_listener()

    def _start_udp_broadcast(self):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        threading.Thread(target=self._send_offers, daemon=True).start()

    def _send_offers(self):
        offer_message = format_offer_message(self.udp_port, self.tcp_port)
        while self.running:
            self.udp_socket.sendto(offer_message, ('<broadcast>', self.udp_port))
            time.sleep(1)

    def _start_tcp_listener(self):
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.bind(("", self.tcp_port))
        self.tcp_socket.listen(5)
        threading.Thread(target=self._handle_tcp_connections, daemon=True).start()

    def _handle_tcp_connections(self):
        while self.running:
            client_socket, _ = self.tcp_socket.accept()
            threading.Thread(target=self._handle_tcp_request, args=(client_socket,), daemon=True).start()

    def _handle_tcp_request(self, client_socket):
        try:
            file_size = int(client_socket.recv(1024).decode().strip())
            client_socket.sendall(b"X" * file_size)
        except Exception as e:
            print(f"Error handling TCP request: {e}")
        finally:
            client_socket.close()
