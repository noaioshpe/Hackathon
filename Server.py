import struct
import select
import signal
from typing import Tuple, Optional
import socket
import random
import time
import threading


# ANSI color codes
class Colors:
    RED = '\033[91m'  # Errors and failures
    GREEN = '\033[92m'  # Success messages
    YELLOW = '\033[93m'  # Warnings and status
    BLUE = '\033[94m'  # Information messages
    MAGENTA = '\033[95m'  # Headers and titles
    CYAN = '\033[96m'  # User input prompts
    RESET = '\033[0m'  # Reset colors


class NetworkConstants:
    """Network protocol constants for the speed test server."""
    massage_offer: int = 0x2
    massage_response: int = 0x3
    massage_payload: int = 0x4
    validator: int = 0xabcddcba


class Server:
    """
    A server class that handles network speed testing using TCP and UDP protocols.
    """

    def __init__(self, host: str = '', offer_port: int = 13117) -> None:
        """
        Initialize the server.
        """
        # Server configuration
        self.server_host = host
        self.broadcast_port = offer_port
        self.connection_tcp_port = random.randint(20000, 65000)
        self.data_udp_port = random.randint(20000, 65000)

        # Network configuration
        self.network_config = NetworkConstants()

        # Server state
        self.is_active = False
        self.server_address_ip: Optional[str] = None

        # Socket initialization
        self.connection_tcp_socket: Optional[socket.socket] = None
        self.data_udp_socket: Optional[socket.socket] = None

        # Set up signal handlers
        self.setup_signal_handlers()

    def start(self) -> None:
        """
        Start the server and initialize sockets and threads.
        """
        # Set the running flag to True
        self.is_active = True

        try:
            self.initialize_sockets()
            self.start_broadcast_thread()
            self.print_server_info()
            self.handle_requests()

        except Exception as e:
            print(f"{Colors.RED}Error starting server: {e}{Colors.RESET}")
            # Stop the server on error
            self.stop_server()

    def initialize_sockets(self) -> None:
        """
        Initialize and bind the UDP and TCP sockets.
        """
        self.udp_socket = self.create_udp_socket()
        self.tcp_socket = self.create_tcp_socket()

    def create_udp_socket(self) -> socket.socket:
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.bind((self.server_host, self.data_udp_port))
        return udp_socket

    def create_tcp_socket(self) -> socket.socket:
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.bind((self.server_host, self.connection_tcp_port))
        tcp_socket.listen(5)
        return tcp_socket

    def start_broadcast_thread(self) -> None:
        """
        Start a thread to broadcast server offers.
        """
        self.broadcast_thread = threading.Thread(target=self.broadcast_offer)
        # Ensure thread exits with the program
        self.broadcast_thread.daemon = True
        self.broadcast_thread.start()

    def print_server_info(self) -> None:
        """
        Print the server's IP address and port information.
        """
        server_ip = socket.gethostbyname(socket.gethostname())
        print(f"{Colors.GREEN}Server started, listening on IP address {server_ip}{Colors.RESET}")
        print(f"{Colors.GREEN}Port: {self.data_udp_port}, TCP Port: {self.connection_tcp_port}{Colors.RESET}")

    def broadcast_offer(self):
        """
        Continuously broadcast server offer messages using non-blocking sockets.
        """
        try:
            # Create a UDP socket for broadcasting server offers
            offer_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Enable broadcasting capability for the socket
            offer_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            # Prepare the offer message with server details
            offer_message = struct.pack('!IbHH',
                                        NetworkConstants.validator,
                                        NetworkConstants.massage_offer,
                                        self.data_udp_port,
                                        self.connection_tcp_port)

            while self.is_active:
                try:
                    # Send broadcast message to all potential clients on the discovery port
                    offer_socket.sendto(offer_message, ('<broadcast>', self.broadcast_port))
                    time.sleep(1)  # Wait before sending the next offer
                except Exception as e:
                    # Log any errors during broadcast transmission
                    print(f"{Colors.RED}Error broadcasting offer: {e}{Colors.RESET}")

        except Exception as e:
            print(f"{Colors.RED}Error in broadcast thread: {e}{Colors.RESET}")
        finally:
            offer_socket.close()  # Ensure the socket is closed

    def handle_requests(self):
        """
        Main loop for handling incoming client requests.
        """
        # Configure sockets for concurrent request handling
        self.udp_socket.setblocking(False)
        self.tcp_socket.setblocking(False)

        # Sockets to be monitored for incoming connections
        monitored_sockets = [self.udp_socket, self.tcp_socket]

        while self.is_active:
            try:
                # Use select to efficiently wait for socket activity
                readable_sockets, _, exceptional_sockets = select.select(
                    monitored_sockets, [], monitored_sockets, 1.0
                )

                for active_socket in readable_sockets:
                    try:
                        if active_socket is self.udp_socket:
                            # Process UDP speed test requests in a separate thread
                            self.process_udp_request(active_socket)

                        elif active_socket is self.tcp_socket:
                            # Handle new TCP client connections in a separate thread
                            self.process_tcp_connection(active_socket)

                    except Exception as socket_error:
                        # Log any errors during socket request processing
                        print(f"{Colors.RED}Error processing socket request: {socket_error}{Colors.RESET}")

                for problem_socket in exceptional_sockets:
                    self.handle_socket_exception(problem_socket, monitored_sockets)

            except Exception as main_loop_error:
                print(f"{Colors.RED}Critical error in request handling loop: {main_loop_error}{Colors.RESET}")

    def process_udp_request(self, udp_socket):
        """
        Process an incoming UDP speed test request.
        """
        try:
            # Receive UDP data
            data, client_address = udp_socket.recvfrom(1024)

            # Handle the UDP speed test in a separate thread
            threading.Thread(
                target=self.handle_udp_speed_test,
                args=(data, client_address)
            ).start()

        except Exception as udp_error:
            print(f"{Colors.RED}Error handling UDP request: {udp_error}{Colors.RESET}")

    def process_tcp_connection(self, tcp_socket):
        """
        Accept and process a new TCP client connection.
        """
        try:
            # Accept the incoming TCP connection
            client_socket, client_address = tcp_socket.accept()

            # Handle the TCP client in a separate thread
            threading.Thread(
                target=self.handle_tcp_client,
                args=(client_socket, client_address)
            ).start()

        except Exception as tcp_error:
            print(f"{Colors.RED}Error handling TCP connection: {tcp_error}{Colors.RESET}")

    def handle_socket_exception(self, problem_socket, monitored_sockets):
        """
        Handle exceptional conditions for a problematic socket.
        """
        try:
            print(f"{Colors.RED}Exception condition on {problem_socket.getsockname()}{Colors.RESET}")

            # Remove the problematic socket from monitoring
            if problem_socket in monitored_sockets:
                monitored_sockets.remove(problem_socket)

            # Close the socket to prevent further issues
            problem_socket.close()

        except Exception as cleanup_error:
            print(f"{Colors.RED}Error during socket exception handling: {cleanup_error}{Colors.RESET}")

    def handle_udp_speed_test(self, data, client_address):
        """
        Handle a UDP speed test request from a client.
        """
        try:
            # Unpack the received UDP request message
            magic_cookie, msg_type, file_size = struct.unpack('!IbQ', data)

            # Validate the incoming request
            if (magic_cookie != NetworkConstants.validator or
                    msg_type != NetworkConstants.massage_response):
                print(f"{Colors.RED}Invalid UDP request from {client_address}{Colors.RESET}")
                return

            # Log the received UDP test request
            print(f"{Colors.BLUE}UDP test request from {client_address}, size: {file_size} bytes{Colors.RESET}")

            # Determine optimal segment size for data transmission
            segment_size = 1024
            total_segments = self.calculate_total_segments(file_size, segment_size)

            # Send segmented data to the client
            self.send_segmented_data(
                file_size=file_size,
                segment_size=segment_size,
                total_segments=total_segments,
                client_address=client_address
            )

        except Exception as processing_error:
            print(f"{Colors.RED}Error handling UDP request: {processing_error}{Colors.RESET}")

    def calculate_total_segments(self, file_size: int, segment_size: int) -> int:
        return (file_size + segment_size - 1) // segment_size

    def send_segmented_data(self, file_size: int, segment_size: int, total_segments: int,
                             client_address: Tuple[str, int]):

        for segment_index in range(total_segments):
            # Calculate remaining bytes for this segment
            remaining_bytes = min(segment_size, file_size - segment_index * segment_size)

            # Create payload of 'X' characters
            payload = b'X' * remaining_bytes

            # Create segment header using NetworkConstants
            segment_header = struct.pack('!IbQQ',
                                         NetworkConstants.validator,
                                         NetworkConstants.massage_payload,
                                         total_segments,
                                         segment_index
                                         )

            # Send the segment to the client
            self.udp_socket.sendto(segment_header + payload, client_address)

    def handle_tcp_client(self, client_socket, client_address):
        """
        Handle a TCP speed test request from a client.
        """
        try:
            # Configure socket timeout to prevent indefinite blocking
            client_socket.settimeout(5.0)

            # Receive file size request from the client
            requested_file_size = self.receive_file_size_request(client_socket)

            # Log the TCP test request details
            print(f"{Colors.BLUE}TCP test request from {client_address}, size: {requested_file_size} bytes{Colors.RESET}")

            # Send the requested amount of data
            self.transmit_test_data(client_socket, requested_file_size)

        except socket.timeout:
            print(f"{Colors.RED}TCP client connection timed out: {client_address}{Colors.RESET}")
        except Exception as connection_error:
            print(f"{Colors.RED}Error handling TCP client: {connection_error}{Colors.RESET}")
        finally:
            # Ensure the socket is always closed, preventing resource leaks
            self.close_client_socket(client_socket)

    def receive_file_size_request(self, client_socket: socket.socket) -> int:
        try:
            # Receive raw data and decode
            raw_data = client_socket.recv(1024).decode().strip()
            # Convert to integer
            file_size = int(raw_data)
            return file_size

        except ValueError:
            print(f"{Colors.RED}Invalid file size request: {raw_data}{Colors.RESET}")
            raise

    def transmit_test_data(self, client_socket: socket.socket, file_size: int) -> None:
        # Generate payload of 'X' characters
        test_data = b'X' * file_size
        try:
            # Send all data to the client
            client_socket.sendall(test_data)
        except Exception as transmission_error:
            print(f"{Colors.RED}Data transmission error: {transmission_error}{Colors.RESET}")
            raise

    def close_client_socket(self, client_socket: socket.socket) -> None:
        try:
            client_socket.close()
        except Exception as close_error:
            print(f"{Colors.RED}Error closing client socket: {close_error}{Colors.RESET}")

    def setup_signal_handlers(self) -> None:
        """Configure system signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum: int, frame) -> None:
        """
        Handle system signals for shutdown.
        """
        print(f"{Colors.YELLOW}Shutting down server...{Colors.RESET}")
        self.stop_server()  # Stop the server

    def stop_server(self):
        # Indicate that the server should stop running
        self.is_active = False
        # Perform resource cleanup
        try:
            # Close UDP socket safely
            self.close_socket(self.udp_socket, 'UDP')
            # Close TCP socket safely
            self.close_socket(self.tcp_socket, 'TCP')
            # Additional optional cleanup can be added here
            self.perform_additional_cleanup()
        except Exception as cleanup_error:
            print(f"{Colors.RED}Critical error during server shutdown: {cleanup_error}{Colors.RESET}")

    def close_socket(self, socket_to_close: Optional[socket.socket], socket_type: str) -> None:
        if socket_to_close is not None:
            try:
                socket_to_close.close()
                print(f"{Colors.GREEN}{socket_type} socket closed successfully{Colors.RESET}")
            except Exception as socket_close_error:
                print(f"{Colors.RED}Error closing {socket_type} socket: {socket_close_error}{Colors.RESET}")

    def perform_additional_cleanup(self) -> None:
        try:
            # Log successful server shutdown
            print(f"{Colors.YELLOW}Server shutdown process completed{Colors.RESET}")
            pass
        except Exception as cleanup_error:
            print(f"{Colors.RED}Error during additional cleanup: {cleanup_error}{Colors.RESET}")


if __name__ == "__main__":
    # Create an instance of the server
    server = Server()
    try:
        # Start the server
        server.start()
    except KeyboardInterrupt:
        # Stop the server on interruption
        server.stop_server()
