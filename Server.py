import socket
import struct
import threading
import time


class Server:
    def __init__(self):
        self.udp_broadcast_port = 13117  # Port for broadcasting offers
        self.tcp_port = None  # Will be assigned when server starts
        self.udp_port = None  # Will be assigned when server starts
        self.running = False
        self.tcp_socket = None
        self.udp_socket = None

    def start_server(self):
        """Start the server and begin broadcasting offers"""
        try:
            # Initialize TCP socket
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.bind(('', 0))  # Bind to random available port
            self.tcp_port = self.tcp_socket.getsockname()[1]
            self.tcp_socket.listen(5)

            # Initialize UDP socket
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.bind(('', 0))  # Bind to random available port
            self.udp_port = self.udp_socket.getsockname()[1]

            # Get server IP
            hostname = socket.gethostname()
            server_ip = socket.gethostbyname(hostname)
            print(f"Server started, listening on IP address {server_ip}")

            self.running = True

            # Start broadcast thread
            broadcast_thread = threading.Thread(target=self._broadcast_offers)
            broadcast_thread.daemon = True
            broadcast_thread.start()

            # Start TCP listener thread
            tcp_thread = threading.Thread(target=self._handle_tcp_connections)
            tcp_thread.daemon = True
            tcp_thread.start()

            # Start UDP listener thread
            udp_thread = threading.Thread(target=self._handle_udp_requests)
            udp_thread.daemon = True
            udp_thread.start()

            # Keep main thread alive
            while self.running:
                time.sleep(1)

        except Exception as e:
            print(f"Error starting server: {e}")
            self.stop_server()

    def stop_server(self):
        """Stop the server and clean up resources"""
        self.running = False
        if self.tcp_socket:
            self.tcp_socket.close()
        if self.udp_socket:
            self.udp_socket.close()

    def _broadcast_offers(self):
        """Broadcast offer messages every second"""
        broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        while self.running:
            try:
                # Create offer message
                offer_message = struct.pack('!IbHH',
                                            0xabcddcba,  # Magic cookie
                                            0x2,  # Message type (offer)
                                            self.udp_port,
                                            self.tcp_port
                                            )

                # Broadcast offer
                broadcast_socket.sendto(offer_message, ('<broadcast>', self.udp_broadcast_port))
                time.sleep(1)

            except Exception as e:
                print(f"Error broadcasting offer: {e}")

        broadcast_socket.close()

    def _handle_tcp_connections(self):
        """Handle incoming TCP connections"""
        while self.running:
            try:
                client_socket, addr = self.tcp_socket.accept()
                client_thread = threading.Thread(
                    target=self._handle_tcp_client,
                    args=(client_socket, addr)
                )
                client_thread.daemon = True
                client_thread.start()

            except Exception as e:
                if self.running:
                    print(f"Error accepting TCP connection: {e}")

    def _handle_tcp_client(self, client_socket, addr):
        """Handle individual TCP client connection"""
        try:
            # Receive file size request
            data = client_socket.recv(1024).decode()
            file_size = int(data.strip())

            # Send requested amount of data
            bytes_sent = 0
            chunk_size = 4096

            while bytes_sent < file_size:
                remaining = file_size - bytes_sent
                chunk = min(chunk_size, remaining)
                data = b'0' * chunk  # Generate dummy data
                client_socket.send(data)
                bytes_sent += chunk

        except Exception as e:
            print(f"Error handling TCP client {addr}: {e}")
        finally:
            client_socket.close()

    def _handle_udp_requests(self):
        """Handle incoming UDP requests"""
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)

                # Verify request format
                if len(data) < 13:  # 4 (cookie) + 1 (type) + 8 (file size)
                    continue

                magic_cookie, msg_type, file_size = struct.unpack('!IbQ', data[:13])

                if magic_cookie != 0xabcddcba or msg_type != 0x3:
                    continue

                # Handle request in new thread
                client_thread = threading.Thread(
                    target=self._handle_udp_client,
                    args=(addr, file_size)
                )
                client_thread.daemon = True
                client_thread.start()

            except Exception as e:
                if self.running:
                    print(f"Error handling UDP request: {e}")

    def _handle_udp_client(self, addr, file_size):
        """Handle individual UDP client request"""
        try:
            segment_size = 1024
            total_segments = (file_size + segment_size - 1) // segment_size

            for segment_num in range(total_segments):
                # Calculate size of current segment
                current_size = min(segment_size, file_size - segment_num * segment_size)

                # Create payload message
                header = struct.pack('!IbQQ',
                                     0xabcddcba,  # Magic cookie
                                     0x4,  # Message type (payload)
                                     total_segments,
                                     segment_num
                                     )

                payload = b'0' * current_size
                message = header + payload

                # Send segment
                self.udp_socket.sendto(message, addr)
                time.sleep(0.001)  # Small delay to prevent network congestion

        except Exception as e:
            print(f"Error sending UDP data to {addr}: {e}")


if __name__ == "__main__":
    server = Server()
    try:
        server.start_server()
    except KeyboardInterrupt:
        server.stop_server()
