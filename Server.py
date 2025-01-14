import socket
import threading
import time
from common import format_offer_message, MAGIC_COOKIE, OFFER_MESSAGE_TYPE


class Server:
    def __init__(self, udp_port=13117, tcp_port=12345):
        self.udp_port = udp_port
        self.tcp_port = tcp_port
        self.running = False
        self.udp_socket = None
        self.tcp_socket = None

    def start(self):
        """Start the server."""
        try:
            print(f"Server started, listening on IP address {socket.gethostbyname(socket.gethostname())}")
            self.running = True

            # Start broadcasting offers over UDP
            self._start_udp_broadcast()

            # Start listening for TCP connections
            self._start_tcp_listener()
        except Exception as e:
            print(f"Error starting server: {e}")

    def _start_udp_broadcast(self):
        """Set up UDP broadcasting."""
        try:
            print("Setting up UDP broadcast...")
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            threading.Thread(target=self._send_offers, daemon=True).start()
        except Exception as e:
            print(f"Error setting up UDP broadcast: {e}")

    def _send_offers(self):
        """Send periodic UDP broadcast offers."""
        try:
            print("Broadcasting UDP offers...")
            offer_message = format_offer_message(self.udp_port, self.tcp_port)
            while self.running:
                try:
                    self.udp_socket.sendto(offer_message, ('<broadcast>', self.udp_port))
                    time.sleep(1)
                except Exception as e:
                    print(f"Error sending UDP offer: {e}")
        except Exception as e:
            print(f"Error in _send_offers: {e}")

    def _start_tcp_listener(self):
        """Set up TCP listener."""
        try:
            print("Setting up TCP listener...")
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.bind(("0.0.0.0", self.tcp_port))  # Bind to all interfaces
            self.tcp_socket.listen(5)
            threading.Thread(target=self._handle_tcp_connections, daemon=True).start()
        except Exception as e:
            print(f"Error setting up TCP listener: {e}")

    def _handle_tcp_connections(self):
        """Handle incoming TCP connections."""
        while self.running:
            try:
                print("Waiting for TCP connection...")
                client_socket, addr = self.tcp_socket.accept()
                print(f"Accepted TCP connection from {addr[0]}")
                threading.Thread(target=self._handle_tcp_request, args=(client_socket,), daemon=True).start()
            except Exception as e:
                print(f"Error accepting TCP connection: {e}")

    def _handle_tcp_request(self, client_socket):
        """Handle a single TCP request."""
        try:
            print("Handling TCP request...")
            file_size = int(client_socket.recv(1024).decode().strip())
            print(f"Received file size request: {file_size} bytes.")

            # Sending data in chunks to avoid memory issues
            chunk_size = 1024
            bytes_sent = 0
            while bytes_sent < file_size:
                to_send = min(chunk_size, file_size - bytes_sent)
                client_socket.sendall(b"X" * to_send)
                bytes_sent += to_send

            print(f"TCP transfer completed: {bytes_sent} bytes sent.")
        except Exception as e:
            print(f"Error handling TCP request: {e}")
        finally:
            client_socket.close()
            print("Closed TCP connection.")


# Server main entry point
if __name__ == "__main__":
    server = Server()
    server.start()
