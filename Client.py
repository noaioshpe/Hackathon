from enum import Enum
import queue
import select
import signal
import socket
import statistics
import struct
import threading
import time


class ClientState(Enum):
    """Enumeration of possible client states."""
    INITIALIZATION = 1
    SERVER_DISCOVERY = 2
    PERFORMANCE_TEST = 3


class Client:

    # ANSI color codes
    RED = '\033[91m'  # Errors and failures
    GREEN = '\033[92m'  # Success messages
    YELLOW = '\033[93m'  # Warnings and status
    BLUE = '\033[94m'  # Information messages
    MAGENTA = '\033[95m'  # Headers and titles
    CYAN = '\033[96m'  # User input prompts
    RESET = '\033[0m'  # Reset color

    def __init__(self, discovery_port=13117):
        """
        Initialize the speed test client with improved configuration.
        Args:
            listen_port (int): Port to listen for server broadcasts (default: 13117)
        """
        # Core settings
        self.discovery_port = discovery_port
        self.state = ClientState.INITIALIZATION
        self.protocol_cookie = 0xabcddcba
        self.is_running = True

        # Thread management
        self.command_queue = queue.Queue()
        self.sync_lock = threading.Lock()
        self.active_tests = 0
        self.max_attempts = 3

        self.performance_data = {
            'tcp': {
                'timings': [],
                'failures': {
                    'connections': 0,
                    'transfers': 0
                },
                'successes': 0
            },
            'udp': {
                'timings': [],
                'packets': {
                    'received': 0,
                    'lost': 0
                }
            }
        }

        # Set up graceful shutdown handlers
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

    def initialize_client(self):
        """Start the speed test client with improved error handling."""
        print(f"{self.MAGENTA}Starting Speed Test Client{self.RESET}")
        print(f"{self.MAGENTA}Press Ctrl+C to exit{self.RESET}")

        while self.is_running:
            try:
                self.file_size = self._get_file_size()
                self.state = ClientState.SERVER_DISCOVERY
                self.initialize_udp_socket()
                self.find_available_server()
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"{self.RED}Error in main loop: {e}{self.RESET}")
                time.sleep(1)

        self._cleanup()

    def handle_shutdown(self, signum, frame):
        """Handle system signals for graceful shutdown."""
        print("\nShutting down client...")
        self.is_running = False

    def initialize_udp_socket(self):
        try:
            """Setup UDP socket with improved configuration."""
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8388608)  # 8MB receive buffer
            self.udp_socket.bind(('', self.discovery_port))
            self.udp_socket.setblocking(False)
        except Exception as e:
            print(f"{self.RED}Error setting up UDP socket: {e}{self.RESET}")
            raise

    def find_available_server(self):
        """Discover speed test servers with improved timeout handling."""
        print(f"{self.YELLOW}Looking for speed test server...{self.RESET}")

        TIMEOUT_INTERVAL = 1.0
        EXPECTED_MSG_SIZE = 9  # Magic(4) + Type(1) + UDP(2) + TCP(2)
        SERVER_MSG_TYPE = 0x2

        while self.is_running and self.state == ClientState.SERVER_DISCOVERY:
            try:
                socket_ready, _, _ = select.select([self.udp_socket], [], [], TIMEOUT_INTERVAL)

                if socket_ready:
                    server_message, server_address = self.udp_socket.recvfrom(1024)

                    if len(server_message) == EXPECTED_MSG_SIZE:
                        # Unpack server broadcast message
                        received_cookie, message_type, server_udp_port, server_tcp_port = \
                            struct.unpack('!IbHH', server_message)

                        if received_cookie == self.protocol_cookie and message_type == SERVER_MSG_TYPE:
                            print(f"{self.GREEN}Received offer from {server_address[0]}{self.RESET}")

                            self.state = ClientState.PERFORMANCE_TEST

                            self.execute_performance_tests(
                                server_host=server_address[0],
                                udp_port=server_udp_port,
                                tcp_port=server_tcp_port
                            )
                            break

            except Exception as e:
                print(f"{self.RED}Error discovering server: {e}{self.RESET}")
                time.sleep(1)

    def _get_file_size(self):
        """Get desired file size from user input with validation."""
        while True:
            try:
                size = input(f"{self.CYAN}Enter file size for speed test (in bytes): {self.RESET}")
                size_int = int(size)
                if size_int <= 0:
                    print(f"{self.RED}File size must be positive{self.RESET}")
                    continue
                return size_int
            except ValueError:
                print(f"{self.RED}Please enter a valid number{self.RESET}")

    def execute_performance_tests(self, server_host, udp_port, tcp_port):
        """
        Coordinate speed tests with improved thread management and connection throttling.
        """
        THREAD_DELAY = 0.05  # 50ms delay between thread starts
        TEST_TIMEOUT = 60  # 60 second total test timeout

        tcp_test_threads = []
        udp_test_threads = []

        try:
            # Get test configuration from user
            num_tcp_tests = int(input(f"{self.CYAN}Enter number of TCP connections: {self.RESET}"))
            num_udp_tests = int(input(f"{self.CYAN}Enter number of UDP connections: {self.RESET}"))

        except ValueError:
            print(f"{self.RED}Invalid input, using default values (1 each){self.RESET}")
            num_tcp_tests = num_udp_tests = 1

            # Initialize statistics for new test session
            with self.sync_lock:
                self.performance_data = {
                    'tcp': {
                        'timings': [],
                        'failures': {
                            'connections': 0,
                            'transfers': 0
                        },
                        'successes': 0
                    },
                    'udp': {
                        'timings': [],
                        'packets': {
                            'received': 0,
                            'lost': 0
                        }
                    }
                }

        # Launch TCP test threads
        for test_number in range(num_tcp_tests):
            if not self.is_running:
                break

            tcp_thread = threading.Thread(
                target=self.perform_tcp_test,
                args=(server_host, tcp_port, test_number + 1)
            )
            tcp_test_threads.append(tcp_thread)
            tcp_thread.start()
            time.sleep(THREAD_DELAY)

        # Launch UDP test threads
        for test_number in range(num_udp_tests):
            if not self.is_running:
                break

            udp_thread = threading.Thread(
                target=self.perform_udp_test,
                args=(server_host, udp_port, test_number + 1)
            )

            udp_test_threads.append(udp_thread)
            udp_thread.start()
            time.sleep(THREAD_DELAY)

        # Wait for tests to complete
        test_end_time = time.time() + TEST_TIMEOUT

        for thread in tcp_test_threads + udp_test_threads:
            remaining_time = max(0, test_end_time - time.time())
            thread.join(timeout=remaining_time)

        # Display results and reset state
        self.display_test_results()
        print(f"{self.YELLOW}All transfers complete, listening for new offers{self.RESET}")
        self.state = ClientState.SERVER_DISCOVERY

    def perform_tcp_test(self, server_host, server_port, test_number):
        """
        Perform TCP speed test with improved error handling and retry mechanism.
        """

        SOCKET_TIMEOUT = 10.0
        RECEIVE_BUFFER = 8388608  # 8MB buffer
        MAX_CHUNK_SIZE = 65536  # 64KB chunks
        RETRY_DELAY = 1.0  # 1 second between retries
        READ_TIMEOUT = 5.0  # 5 seconds read timeout

        tcp_socket = None
        attempt_count = 0

        while attempt_count < self.max_attempts and self.is_running:
            try:
                tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tcp_socket.settimeout(SOCKET_TIMEOUT)
                tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RECEIVE_BUFFER)

                with self.sync_lock:
                    self.active_tests += 1

                # Establish connection and send test parameters
                tcp_socket.connect((server_host, server_port))
                test_request = f"{self.file_size}\n".encode()
                tcp_socket.send(test_request)

                # Start data transfer and timing
                transfer_start = time.time()
                bytes_received = 0

                while bytes_received < self.file_size and self.is_running:
                    ready_sockets, _, _ = select.select([tcp_socket], [], [], READ_TIMEOUT)

                    if not ready_sockets:
                        raise TimeoutError("TCP data transfer timed out")

                    remaining_bytes = self.file_size - bytes_received
                    data_chunk = tcp_socket.recv(min(MAX_CHUNK_SIZE, remaining_bytes))

                    if not data_chunk:
                        break

                    bytes_received += len(data_chunk)

                transfer_duration = time.time() - transfer_start

                if transfer_duration > 0:
                    transfer_speed = (self.file_size * 8) / transfer_duration

                    with self.sync_lock:
                        self.performance_data['tcp']['timings'].append(transfer_duration)
                        self.performance_data['tcp']['successes'] += 1

                    print(f"{self.GREEN}TCP transfer #{test_number} finished:"
                          f" Time: {transfer_duration:.3f}s,"
                          f" Speed: {transfer_speed:.2f} bits/second{self.RESET}")
#FIXME (maybe it should be in the line of the print)
                break  # Success, exit retry loop

            except (ConnectionRefusedError, TimeoutError) as conn_error:
                attempt_count += 1
                with self.sync_lock:
                    self.performance_data['tcp']['failures']['connections'] += 1
                print(f"{self.YELLOW}TCP transfer #{test_number} failed "
                      f"(attempt {attempt_count}/{self.max_attempts}): {conn_error}{self.RESET}")
                time.sleep(RETRY_DELAY)  # Wait before retry

            except Exception as error:
                with self.sync_lock:
                    self.performance_data['tcp']['failures']['transfers'] += 1
                print(f"{self.RED}TCP transfer #{test_number} error: {error}{self.RESET}")
                break

            finally:
                if tcp_socket:
                    tcp_socket.close()
                with self.sync_lock:
                    self.active_tests -= 1

    def perform_udp_test(self, server_host, server_port, test_number):
        """
        Perform UDP speed test with improved packet tracking and error handling.
        """
        SOCKET_TIMEOUT = 5.0
        RECEIVE_BUFFER = 8388608  # 8MB buffer
        PACKET_SIZE = 4096  # 4KB packet size
        HEADER_SIZE = 21  # Magic(4) + Type(1) + Total(8) + Current(8)
        PACKET_TIMEOUT = 1.0  # Timeout for packet reception

        udp_socket = None

        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.settimeout(SOCKET_TIMEOUT)
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RECEIVE_BUFFER)

            test_request = struct.pack('!IbQ', self.protocol_cookie, 0x3, self.file_size)
            udp_socket.sendto(test_request, (server_host, server_port))

            total_segments = None
            received_segments = set()
            test_start = time.time()
            last_packet = test_start

            while (time.time() - last_packet) < SOCKET_TIMEOUT and self.is_running:
                try:
                    ready_sockets, _, _ = select.select([udp_socket], [], [], PACKET_TIMEOUT)
                    if not ready_sockets:
                        continue

                    packet_data, _ = udp_socket.recvfrom(PACKET_SIZE)
                    if len(packet_data) < HEADER_SIZE:
                        continue

                    # Extract packet header
                    header = packet_data[:HEADER_SIZE]
                    received_cookie, msg_type, total_segs, current_seg = struct.unpack('!IbQQ', header)

                    # Validate packet
                    if received_cookie != self.protocol_cookie or msg_type != 0x4:
                        continue

                    # Track segments
                    if total_segments is None:
                        total_segments = total_segs

                    received_segments.add(current_seg)

                    with self.sync_lock:
                        self.performance_data['udp']['packets']['received'] += 1
                    last_packet = time.time()

                    # Check if all segments received
                    if len(received_segments) == total_segments:
                        break

                except socket.timeout:
                    break

            # Calculate performance metrics
            test_duration = time.time() - test_start

            if total_segments:
                lost_packets = total_segments - len(received_segments)
                loss_percentage = (lost_packets / total_segments) * 100
                transfer_speed = (self.file_size * 8) / test_duration

                with self.sync_lock:
                    self.performance_data['udp']['timings'].append(test_duration)
                    self.performance_data['udp']['packets']['lost'] += lost_packets

                print(f"{self.GREEN}UDP transfer #{test_number} finished:"
                      f" Time: {test_duration:.3f}s,"
                      f" Speed: {transfer_speed:.2f} bits/second,"
                      f" Success rate: {100 - loss_percentage:.2f}%{self.RESET}")
            else:
                print(f"{self.RED}UDP transfer #{test_number} failed: No segments received{self.RESET}")

        except Exception as error:
            print(f"{self.RED}UDP transfer #{test_number} error: {error}{self.RESET}")
        finally:
            if udp_socket:
                udp_socket.close()

    def display_test_results(self):
        """Display comprehensive performance statistics for TCP and UDP tests."""
        print(f"\n{self.MAGENTA}=== Speed Test Statistics ==={self.RESET}")

        with self.sync_lock:
            self.display_tcp_metrics()
            self.display_udp_metrics()

    def display_tcp_metrics(self):
        """Display TCP-specific performance metrics."""
        tcp_data = self.performance_data['tcp']

        if tcp_data['timings']:
            avg_duration = statistics.mean(tcp_data['timings'])
            avg_speed = (self.file_size * 8) / avg_duration

            print(f"{self.CYAN}TCP Statistics:")
            print(f"- Average Time: {avg_duration:.3f}s")
            print(f"- Average Speed: {avg_speed:.2f} bits/second")
            print(f"- Successful Transfers: {tcp_data['successes']}")
            print(f"- Connection Failures: {tcp_data['failures']['connections']}")
            print(f"- Transfer Failures: {tcp_data['failures']['transfers']}{self.RESET}")

    def display_udp_metrics(self):
        """Display UDP-specific performance metrics."""
        udp_data = self.performance_data['udp']

        if udp_data['timings']:
            avg_duration = statistics.mean(udp_data['timings'])
            avg_speed = (self.file_size * 8) / avg_duration

            total_packets = udp_data['packets']['received'] + udp_data['packets']['lost']
            if total_packets > 0:
                packet_loss = (udp_data['packets']['lost'] / total_packets * 100)
            else:
                packet_loss = 0

            print(f"{self.CYAN}UDP Statistics:")
            print(f"- Average Time: {avg_duration:.3f}s")
            print(f"- Average Speed: {avg_speed:.2f} bits/second")
            print(f"- Packet Loss Rate: {packet_loss:.2f}%{self.RESET}")

    def _cleanup(self):
        """Safely release all network resources and socket connections."""
        try:
            # Close UDP socket if it exists
            if hasattr(self, 'udp_socket'):
                try:
                    self.udp_socket.close()
                    print(f"{self.BLUE}UDP socket closed successfully{self.RESET}")
                except Exception as socket_error:
                    print(f"{self.RED}Failed to close UDP socket: {socket_error}{self.RESET}")

            # Additional cleanup could be added here
            print(f"{self.GREEN}Cleanup completed{self.RESET}")

        except Exception as error:
            print(f"{self.RED}Error during cleanup: {error}{self.RESET}")
        finally:
            # Ensure running flag is set to False
            self.is_running = False


if __name__ == "__main__":
    client = Client()
    client.start()