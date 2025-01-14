import socket
import struct
import threading
import time
from common import format_request_message, MAGIC_COOKIE, OFFER_MESSAGE_TYPE

class Client:
    def __init__(self, udp_port=13117):
        self.udp_port = udp_port
        self.server_ip = None
        self.server_tcp_port = None
        self.running = True

    def start(self):
        """Start the client and look for server offers."""
        print("Client started, listening for offer requests...")
        threading.Thread(target=self._listen_for_offers, daemon=True).start()

        while not self.server_ip:
            time.sleep(1)  # Wait for server offer
        self._connect_to_server()

    def _listen_for_offers(self):
        """Listen for UDP offers from servers."""
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        udp_socket.bind(("", self.udp_port))

        while self.running:
            try:
                data, addr = udp_socket.recvfrom(1024)
                magic_cookie, message_type, udp_port, tcp_port = struct.unpack('!IBHH', data)
                if magic_cookie == MAGIC_COOKIE and message_type == OFFER_MESSAGE_TYPE:
                    print(f"Received offer from {addr[0]} on TCP port {tcp_port}")
                    self.server_ip = addr[0]
                    self.server_tcp_port = tcp_port
            except Exception as e:
                print(f"Error receiving UDP offer: {e}")

    def _connect_to_server(self):
        """Connect to the server and perform the speed test."""
        file_size = int(input("Enter file size (in bytes): "))
        tcp_connections = int(input("Enter number of TCP connections: "))
        udp_connections = int(input("Enter number of UDP connections: "))

        threads = []
        for _ in range(tcp_connections):
            threads.append(threading.Thread(target=self._tcp_transfer, args=(file_size,), daemon=True))
        # UDP threads can be added similarly
        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

    def _tcp_transfer(self, file_size):
        """Perform a TCP transfer."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.server_ip, self.server_tcp_port))
            sock.sendall(f"{file_size}\n".encode())

            received_data = 0
            while received_data < file_size:
                data = sock.recv(1024)
                received_data += len(data)

            print(f"TCP transfer finished: {received_data} bytes received.")
        except Exception as e:
            print(f"Error during TCP transfer: {e}")
        finally:
            sock.close()

# Client main entry point
if __name__ == "__main__":
    client = Client()
    client.start()
