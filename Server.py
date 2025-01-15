import socket
import struct
import threading
import time
import random


class Server:
    def __init__(self, host='', offer_port=13117):
        """
        Initialize the server with specified host and port.
        Args:
            host (str): The server's host address (default: all interfaces)
            offer_port (int): Port for broadcasting server offers (default: 13117)
        """
        self.host = host  # Store the server's host address
        self.offer_port = offer_port  # Port for broadcasting offers
        self.udp_port = random.randint(20000, 65000)  # Random UDP port for speed tests
        self.tcp_port = random.randint(20000, 65000)  # Random TCP port for speed tests
        self.running = False  # Flag to indicate whether the server is running
        self.magic_cookie = 0xabcddcba  # Unique identifier for valid packets
        self.msg_type_offer = 0x2  # Message type for server offer packets
        self.msg_type_response = 0x3  # Message type for client response
        self.msg_type_payload = 0x4  # Message type for data payload
        self.server_ip = None
        self.tcp_socket = None
        self.udp_socket = None

    def _get_ip_address(self):
        """Get the server's IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return '127.0.0.1'

    def start_server(self):
        """Start the server and begin broadcasting offers"""
        try:
            # Get server IP
            self.server_ip = self._get_ip_address()

            # Initialize TCP socket
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.tcp_socket.bind((self.server_ip, self.tcp_port))
            self.tcp_socket.listen(5)

            # Initialize UDP socket
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.bind((self.server_ip, self.udp_port))

            print(f"\nServer started, listening on IP address {self.server_ip}")
            print(f"TCP port: {self.tcp_port}, UDP port: {self.udp_port}\n")

            self.running = True

            # Start threads
            threads = [
                threading.Thread(target=self._broadcast_offer),
                threading.Thread(target=self._handle_tcp_connections),
                threading.Thread(target=self._handle_udp_requests)
            ]

            for thread in threads:
                thread.daemon = True
                thread.start()

            # Keep main thread alive
            while self.running:
                time.sleep(1)

        except Exception as e:
            print(f"\033[91mError starting server: {e}\033[0m")
            self.stop_server()

    def _broadcast_offer(self):
        """
        Continuously broadcast server offer messages using non-blocking sockets.
        """
        try:
            # Create a UDP socket for broadcasting
            offer_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            offer_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            # Prepare the offer message with server details
            offer_message = struct.pack('!IbHH',
                                        self.magic_cookie,
                                        self.msg_type_offer,
                                        self.udp_port,
                                        self.tcp_port)

            while self.running:
                try:
                    # Send the offer message as a broadcast
                    offer_socket.sendto(offer_message, ('<broadcast>', self.offer_port))
                    time.sleep(1)  # Wait before sending the next offer
                except Exception as e:
                    print(f"\033[91mError broadcasting offer: {e}\033[0m")

        except Exception as e:
            print(f"\033[91mError in broadcast thread: {e}\033[0m")
        finally:
            offer_socket.close()  # Ensure the socket is closed

    def _handle_tcp_connections(self):
        """Handle incoming TCP connections"""
        while self.running:
            try:
                client_socket, addr = self.tcp_socket.accept()
                client_socket.settimeout(5.0)  # 5 second timeout for operations
                print(f"\033[94mAccepted TCP connection from {addr}\033[0m")

                client_thread = threading.Thread(
                    target=self._handle_tcp_client,
                    args=(client_socket, addr)
                )
                client_thread.daemon = True
                client_thread.start()

            except Exception as e:
                if self.running:
                    print(f"\033[91mError accepting TCP connection: {e}\033[0m")

    def _handle_tcp_client(self, client_socket, addr):
        """Handle individual TCP client connection"""
        try:
            # Receive file size request
            data = client_socket.recv(1024).decode().strip()
            if not data:
                raise Exception("No data received")

            file_size = int(data)
            print(f"\033[94mTCP client {addr} requested {file_size} bytes\033[0m")

            # Send requested amount of data
            bytes_sent = 0
            chunk_size = 4096

            while bytes_sent < file_size and self.running:
                remaining = file_size - bytes_sent
                chunk = min(chunk_size, remaining)
                data = b'0' * chunk
                client_socket.send(data)
                bytes_sent += chunk

            print(f"\033[92mTCP transfer completed for {addr}: {bytes_sent} bytes sent\033[0m")

        except Exception as e:
            print(f"\033[91mError handling TCP client {addr}: {e}\033[0m")
        finally:
            client_socket.close()

    def _handle_udp_requests(self):
        """Handle incoming UDP requests"""
        self.udp_socket.settimeout(1.0)  # 1 second timeout for UDP operations

        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                print(f"\033[94mReceived UDP request from {addr}\033[0m")

                if len(data) < 13:  # Magic cookie (4) + type (1) + file size (8)
                    continue

                magic_cookie, msg_type, file_size = struct.unpack('!IbQ', data[:13])

                if magic_cookie != self.magic_cookie or msg_type != self.msg_type_response:
                    continue

                print(f"\033[94mValid UDP request from {addr} for {file_size} bytes\033[0m")

                client_thread = threading.Thread(
                    target=self._handle_udp_client,
                    args=(addr, file_size)
                )
                client_thread.daemon = True
                client_thread.start()

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"\033[91mError handling UDP request: {e}\033[0m")

    def _handle_udp_client(self, addr, file_size):
        """Handle individual UDP client request"""
        try:
            segment_size = 1024
            total_segments = (file_size + segment_size - 1) // segment_size
            print(f"\033[94mStarting UDP transfer to {addr}: {total_segments} segments\033[0m")

            for segment_num in range(total_segments):
                if not self.running:
                    break

                current_size = min(segment_size, file_size - segment_num * segment_size)
                header = struct.pack('!IbQQ',
                                     self.magic_cookie,
                                     self.msg_type_payload,
                                     total_segments,
                                     segment_num
                                     )

                payload = b'0' * current_size
                message = header + payload
                self.udp_socket.sendto(message, addr)
                time.sleep(0.001)  # Small delay to prevent network congestion

            print(f"\033[92mUDP transfer completed for {addr}: {total_segments} segments sent\033[0m")

        except Exception as e:
            print(f"\033[91mError sending UDP data to {addr}: {e}\033[0m")

    def stop_server(self):
        """Stop the server and clean up resources"""
        print("\n\033[93mShutting down server...\033[0m")
        self.running = False

        # Close sockets
        if hasattr(self, 'tcp_socket') and self.tcp_socket:
            self.tcp_socket.close()
        if hasattr(self, 'udp_socket') and self.udp_socket:
            self.udp_socket.close()


if __name__ == "__main__":
    server = Server()
    try:
        server.start_server()
    except KeyboardInterrupt:
        server.stop_server()