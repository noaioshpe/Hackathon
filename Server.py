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
        try:
            print("Starting the server...")
            self.running = True
            self._start_udp_broadcast()
            self._start_tcp_listener()
            print(f"Server started successfully. Listening for TCP connections on port {self.tcp_port} "
                  f"and broadcasting UDP offers on port {self.udp_port}.")
        except Exception as e:
            print(f"Error in start_server: {e}")

    def _start_udp_broadcast(self):
        try:
            print("Setting up UDP broadcast...")
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            self.udp_socket.bind(("0.0.0.0", self.udp_port))  # Bind to all interfaces
            threading.Thread(target=self._send_offers, daemon=True).start()
        except Exception as e:
            print(f"Error in _start_udp_broadcast: {e}")

    def _send_offers(self):
        try:
            print("Broadcasting UDP offers...")
            offer_message = format_offer_message(self.udp_port, self.tcp_port)
            while self.running:
                try:
                    self.udp_socket.sendto(offer_message, ('<broadcast>', self.udp_port))
                    print("Sent UDP offer.")
                except Exception as e:
                    print(f"Error sending UDP offer: {e}")
                time.sleep(1)
        except Exception as e:
            print(f"Error in _send_offers: {e}")

    def _start_tcp_listener(self):
        try:
            print("Setting up TCP listener...")
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.bind(("0.0.0.0", self.tcp_port))  # Bind to all interfaces
            self.tcp_socket.listen(5)
            threading.Thread(target=self._handle_tcp_connections, daemon=True).start()
            print(f"TCP listener running on port {self.tcp_port}.")
        except Exception as e:
            print(f"Error in _start_tcp_listener: {e}")

    def _handle_tcp_connections(self):
        try:
            while self.running:
                print("Waiting for TCP connection...")
                client_socket, addr = self.tcp_socket.accept()
                print(f"Accepted TCP connection from {addr}.")
                threading.Thread(target=self._handle_tcp_request, args=(client_socket,), daemon=True).start()
        except Exception as e:
            print(f"Error in _handle_tcp_connections: {e}")

    def _handle_tcp_request(self, client_socket):
        try:
            print("Handling TCP request...")
            file_size = int(client_socket.recv(1024).decode().strip())
            print(f"Received file size request: {file_size} bytes.")
            chunk_size = 1024 * 1024  # Send in 1 MB chunks to avoid memory issues
            bytes_sent = 0
            while bytes_sent < file_size:
                remaining = file_size - bytes_sent
                client_socket.sendall(b"X" * min(chunk_size, remaining))
                bytes_sent += min(chunk_size, remaining)
            print(f"File sent to client over TCP ({bytes_sent} bytes).")
        except Exception as e:
            print(f"Error handling TCP request: {e}")
        finally:
            client_socket.close()
            print("Closed TCP connection.")

    def stop_server(self):
        """Gracefully stop the server and release resources."""
        self.running = False
        if self.udp_socket:
            self.udp_socket.close()
        if self.tcp_socket:
            self.tcp_socket.close()
        print("Server stopped.")
