import socket
import threading
import time
import struct
from common import format_request_message, MAGIC_COOKIE, OFFER_MESSAGE_TYPE, PAYLOAD_MESSAGE_TYPE


class Client:
    def __init__(self, udp_port):
        self.udp_port = udp_port
        self.server_ip = None
        self.server_tcp_port = None
        self.file_size = 0
        self.tcp_connections = 0
        self.udp_connections = 0
        self.running = True

    def start_client(self):
        threading.Thread(target=self._listen_for_offers, daemon=True).start()

    def _listen_for_offers(self):
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        udp_socket.bind(("", self.udp_port))

        while self.running:
            data, addr = udp_socket.recvfrom(1024)
            magic_cookie, message_type, udp_port, tcp_port = struct.unpack('!IBHH', data)
            if magic_cookie == MAGIC_COOKIE and message_type == OFFER_MESSAGE_TYPE:
                print(f"Received offer from {addr[0]} on TCP port {tcp_port}")
                self.server_ip = addr[0]
                self.server_tcp_port = tcp_port

    def connect_to_server(self, file_size, tcp_connections, udp_connections):
        self.file_size = file_size
        self.tcp_connections = tcp_connections
        self.udp_connections = udp_connections
        self._perform_speed_test()

    def _perform_speed_test(self):
        threads = []
        for _ in range(self.tcp_connections):
            threads.append(threading.Thread(target=self._tcp_transfer, daemon=True))
        for _ in range(self.udp_connections):
            threads.append(threading.Thread(target=self._udp_transfer, daemon=True))

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

    def _tcp_transfer(self):
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self.server_ip, self.server_tcp_port))
            sock.sendall(str(self.file_size).encode() + b"\n")

            received_data = 0
            while received_data < self.file_size:
                data = sock.recv(1024)
                received_data += len(data)

            total_time = time.time() - start_time
            speed = self.file_size / total_time
            print(f"TCP transfer finished, total time: {total_time:.2f} seconds, speed: {speed:.2f} bytes/second")
        except Exception as e:
            print(f"Error during TCP transfer: {e}")
        finally:
            sock.close()

    def _udp_transfer(self):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(format_request_message(self.file_size), (self.server_ip, self.udp_port))

            received_packets = 0
            expected_packets = None
            start_time = time.time()
            sock.settimeout(1)

            while True:
                try:
                    data, _ = sock.recvfrom(1024)
                    magic_cookie, message_type, total_segments, current_segment = struct.unpack('!IBQQ', data[:21])
                    if magic_cookie == MAGIC_COOKIE and message_type == PAYLOAD_MESSAGE_TYPE:
                        received_packets += 1
                        if expected_packets is None:
                            expected_packets = total_segments
                except socket.timeout:
                    break

            total_time = time.time() - start_time
            loss_rate = (1 - received_packets / expected_packets) * 100 if expected_packets else 100
            speed = self.file_size / total_time
            print(f"UDP transfer finished, total time: {total_time:.2f} seconds, speed: {speed:.2f} bytes/second, packet loss: {loss_rate:.2f}%")
        except Exception as e:
            print(f"Error during UDP transfer: {e}")
        finally:
            sock.close()
