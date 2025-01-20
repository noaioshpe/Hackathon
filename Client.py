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
        Initialize the client class.
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
        """Initialize and run the client"""

        print(f"{self.MAGENTA}Client started, listening for offer requests...{self.RESET}")
        print(f"{self.MAGENTA}Press Ctrl+C to exit{self.RESET}")

        while self.is_running:
            try:
                self.file_size = self.get_file_size()
                self.state = ClientState.SERVER_DISCOVERY
                self.initialize_udp_socket()
                self.find_available_server()
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"{self.RED}Error in main loop: {e}{self.RESET}")
                time.sleep(1)

        self.cleanup()

    def initialize_udp_socket(self):
        try:
            self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

            # More robust socket configuration
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)  # Enable broadcast
            self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8388608)  # 8MB receive buffer

            # Bind to all interfaces and specific port
            self.udp_socket.bind(('0.0.0.0', self.discovery_port))
            self.udp_socket.setblocking(False)
        except Exception as e:
            print(f"{self.RED}Error setting up UDP socket: {e}{self.RESET}")
            raise

    def find_available_server(self):
        print(f"{self.YELLOW}Looking for speed test server...{self.RESET}")

        TOTAL_DISCOVERY_TIME = 30  # Increased discovery window
        TIMEOUT_INTERVAL = 1.0
        EXPECTED_MSG_SIZE = 9
        SERVER_MSG_TYPE = 0x2

        discovered_servers = []
        start_time = time.time()

        while (self.is_running and
               self.state == ClientState.SERVER_DISCOVERY and
               time.time() - start_time < TOTAL_DISCOVERY_TIME):

            try:
                socket_ready, _, _ = select.select([self.udp_socket], [], [], TIMEOUT_INTERVAL)

                if socket_ready:
                    try:
                        server_message, server_address = self.udp_socket.recvfrom(1024)

                        if len(server_message) == EXPECTED_MSG_SIZE:
                            received_cookie, message_type, server_udp_port, server_tcp_port = \
                                struct.unpack('!IbHH', server_message)

                            if (received_cookie == self.protocol_cookie and
                                    message_type == SERVER_MSG_TYPE):

                                # Avoid duplicate server offers
                                if server_address[0] not in [s[0] for s in discovered_servers]:
                                    print(f"{self.GREEN}Received offer from {server_address[0]}{self.RESET}")
                                    discovered_servers.append((server_address[0], server_udp_port, server_tcp_port))

                    except Exception as parse_error:
                        print(f"{self.RED}Error parsing server message: {parse_error}{self.RESET}")

            except Exception as e:
                print(f"{self.RED}Error discovering server: {e}{self.RESET}")
                time.sleep(0.5)

        # Choose the first discovered server or handle multiple servers
        if discovered_servers:
            server_host, udp_port, tcp_port = discovered_servers[0]
            self.state = ClientState.PERFORMANCE_TEST
            self.execute_performance_tests(
                server_host=server_host,
                udp_port=udp_port,
                tcp_port=tcp_port
            )
        else:
            print(f"{self.RED}No servers discovered within {TOTAL_DISCOVERY_TIME} seconds{self.RESET}")

    def get_file_size(self):
        """Interactively prompt the user to specify a file size for speed testing with robust input validation"""

        while True:
            try:
                size = input(f"{self.CYAN}Enter the file size for the speed test (in bytes): {self.RESET}")
                size_int = int(size)
                if size_int <= 0:
                    print(f"{self.RED}File size must be positive{self.RESET}")
                    continue
                return size_int
            except ValueError:
                print(f"{self.RED}Please enter a valid number{self.RESET}")

    def execute_performance_tests(self, server_host, udp_port, tcp_port):
        """
        Coordinate comprehensive network performance tests across multiple TCP and UDP connections
        """
        THREAD_DELAY = 0.05  # 50ms delay between thread starts
        TEST_TIMEOUT = 60  # 60 second total test timeout
        tcp_test_threads = []
        udp_test_threads = []

        def get_test_counts():
            try:
                tcp_count = int(input(f"{self.CYAN}Enter number of TCP connections: {self.RESET}"))
                udp_count = int(input(f"{self.CYAN}Enter number of UDP connections: {self.RESET}"))
                if tcp_count < 0 or udp_count < 0:
                    raise ValueError("Connection counts must be positive")
                return tcp_count, udp_count
            except (ValueError, TypeError):
                print(f"{self.RED}Invalid input, using default values{self.RESET}")
                return 1, 1

        # Initialize statistics for new test session
        def initialize_performance_data():
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

        def launch_test_threads(test_type, count, port):
            threads = []
            target_func = self.perform_tcp_test if test_type == 'tcp' else self.perform_udp_test

            for test_num in range(count):
                if not self.is_running:
                    break

                thread = threading.Thread(
                    target=target_func,
                    args=(server_host, port, test_num + 1),
                    name=f"{test_type}_test_{test_num}"
                )
                thread.daemon = True  # Ensure threads don't block program exit
                threads.append(thread)
                thread.start()
                time.sleep(THREAD_DELAY)

            return threads

        try:
            # Get test configuration and initialize
            num_tcp_tests, num_udp_tests = get_test_counts()
            initialize_performance_data()

            # Launch test threads
            test_threads = []
            test_threads.extend(launch_test_threads('tcp', num_tcp_tests, tcp_port))
            test_threads.extend(launch_test_threads('udp', num_udp_tests, udp_port))

            # Wait for tests with timeout
            start_time = time.time()
            for thread in test_threads:
                remaining_time = max(0, TEST_TIMEOUT - (time.time() - start_time))
                thread.join(timeout=remaining_time)

                # Check if thread is still alive after timeout
                if thread.is_alive():
                    print(f"{self.YELLOW}Warning: {thread.name} did not complete within timeout{self.RESET}")

            # Display results
            self.display_test_results()
            print(f"{self.YELLOW}All transfers complete, listening to offer requests{self.RESET}")

        except Exception as e:
            print(f"{self.RED}Error during performance tests: {str(e)}{self.RESET}")

        finally:
            # Ensure state is reset even if an error occurs
            self.state = ClientState.SERVER_DISCOVERY

    def perform_tcp_test(self, server_host, server_port, test_number):
        """
        Execute a robust TCP speed test with advanced error handling and configurable retry mechanism.
        """
        # Constants
        SOCKET_TIMEOUT = 10.0
        RECEIVE_BUFFER = 8388608  # 8MB buffer
        MAX_CHUNK_SIZE = 65536  # 64KB chunks
        RETRY_DELAY = 1.0  # 1 second between retries
        READ_TIMEOUT = 5.0  # 5 seconds read timeout

        def setup_socket():
            """Create and configure TCP socket with appropriate parameters"""
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(SOCKET_TIMEOUT)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, RECEIVE_BUFFER)
            return sock

        def handle_data_transfer(sock):
            """Handle the actual data transfer and timing"""
            bytes_received = 0
            transfer_start = time.time()

            while bytes_received < self.file_size and self.is_running:
                ready_sockets, _, _ = select.select([sock], [], [], READ_TIMEOUT)

                if not ready_sockets:
                    raise TimeoutError("TCP data transfer timed out")

                remaining_bytes = self.file_size - bytes_received
                data_chunk = sock.recv(min(MAX_CHUNK_SIZE, remaining_bytes))

                if not data_chunk:
                    break

                bytes_received += len(data_chunk)

            return time.time() - transfer_start, bytes_received

        def record_success(duration):
            """Record successful transfer metrics"""
            transfer_speed = (self.file_size * 8) / duration

            with self.sync_lock:
                self.performance_data['tcp']['timings'].append(duration)
                self.performance_data['tcp']['successes'] += 1

            print(f"{self.GREEN}TCP transfer #{test_number} finished"
                  f" total time: {duration:.3f} seconds,"
                  f" total speed: {transfer_speed:.2f} bits/second{self.RESET}")

        def record_failure(error_type, error):
            """Record transfer failure with appropriate categorization"""
            with self.sync_lock:
                self.performance_data['tcp']['failures'][error_type] += 1

            color = self.YELLOW if error_type == 'connections' else self.RED
            print(f"{color}TCP transfer #{test_number} failed: {error}{self.RESET}")

        tcp_socket = None
        attempt_count = 0

        try:
            while attempt_count < self.max_attempts and self.is_running:
                try:
                    # Setup and connection phase
                    tcp_socket = setup_socket()

                    with self.sync_lock:
                        self.active_tests += 1

                    # Connect and send test parameters
                    tcp_socket.connect((server_host, server_port))
                    tcp_socket.send(f"{self.file_size}\n".encode())

                    # Execute transfer
                    duration, bytes_received = handle_data_transfer(tcp_socket)

                    # Verify complete transfer
                    if duration > 0:
                        record_success(duration)
                        break
                    else:
                        raise ConnectionError("Invalid transfer duration - zero or negative time")

                except (ConnectionRefusedError, TimeoutError) as e:
                    attempt_count += 1
                    record_failure('connections', f"{str(e)} (attempt {attempt_count}/{self.max_attempts})")
                    time.sleep(RETRY_DELAY)

                except Exception as e:
                    record_failure('transfers', str(e))
                    break

        finally:
            if tcp_socket:
                tcp_socket.close()
            with self.sync_lock:
                self.active_tests -= 1

    def perform_udp_test(self, server_host, server_port, test_number):
        """
        Execute a comprehensive UDP speed test with advanced packet tracking and reliability analysis
        """
        SOCKET_TIMEOUT = 5.0
        RECEIVE_BUFFER = 8388608  # 8MB buffer
        PACKET_SIZE = 4096  # 4KB packet size
        HEADER_SIZE = 21  # Magic(4) + Type(1) + Total(8) + Current(8)
        PACKET_TIMEOUT = 1.0  # Timeout for packet reception
        udp_socket = None

        def process_packet(packet_data):
            """Process a received packet and return segment info if valid"""
            if len(packet_data) < HEADER_SIZE:
                return None

            header = packet_data[:HEADER_SIZE]
            received_cookie, msg_type, total_segs, current_seg = struct.unpack('!IbQQ', header)

            if received_cookie != self.protocol_cookie or msg_type != 0x4:
                return None

            return total_segs, current_seg

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
                    packet_info = process_packet(packet_data)

                    if not packet_info:
                        continue

                    total_segs, current_seg = packet_info

                    if total_segments is None:
                        total_segments = total_segs

                    received_segments.add(current_seg)

                    with self.sync_lock:
                        self.performance_data['udp']['packets']['received'] += 1
                    last_packet = time.time()

                    if len(received_segments) == total_segments:
                        break

                except socket.timeout:
                    break

            test_duration = time.time() - test_start

            if total_segments:
                lost_packets = total_segments - len(received_segments)
                loss_percentage = (lost_packets / total_segments) * 100
                transfer_speed = (self.file_size * 8) / test_duration

                with self.sync_lock:
                    self.performance_data['udp']['timings'].append(test_duration)
                    self.performance_data['udp']['packets']['lost'] += lost_packets

                print(f"{self.GREEN}UDP transfer #{test_number} finished"
                      f" total time: {test_duration:.3f} seconds,"
                      f" total speed: {transfer_speed:.2f} bits/second,"
                      f" success rate: {100 - loss_percentage:.2f}% {self.RESET}")
            else:
                print(f"{self.RED} UDP transfer #{test_number} failed, no segments received{self.RESET}")

        except Exception as error:
            print(f"{self.RED}UDP transfer #{test_number} error: {error}{self.RESET}")

        finally:
            if udp_socket:
                udp_socket.close()

    def display_test_results(self):
        """Aggregate and display comprehensive network performance statistics for TCP and UDP tests"""

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

    def handle_shutdown(self, signum, frame):
        """Handle system signals to initiate a controlled client shutdown"""

        print("\nShutting down client...")
        self.is_running = False

    def cleanup(self):
        """Perform comprehensive resource management and graceful shutdown of network components"""

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
    client.initialize_client()