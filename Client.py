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

    """
    An improved client class that performs network speed tests using both TCP and UDP protocols.
    Includes enhanced connection handling and retry mechanisms.
    """

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
                'timings': [],  # Same as tcp_times
                'failures': {
                    'connections': 0,  # Same as tcp_connect_fails
                    'transfers': 0  # Same as tcp_transfer_fails
                },
                'successes': 0  # Same as successful_tests
            },
            'udp': {
                'timings': [],  # Same as udp_times
                'packets': {
                    'received': 0,  # Same as udp_received
                    'lost': 0  # Same as udp_lost
                }
            }
        }

        # Set up graceful shutdown handlers
        signal.signal(signal.SIGINT, self._cleanup_handler)
        signal.signal(signal.SIGTERM, self._cleanup_handler)

    def _cleanup_handler(self, signum, frame):
        """Handle system signals for graceful shutdown."""
        print("\nShutting down client...")
        self.is_running = False

    def start(self):
        """Start the speed test client with improved error handling."""
        print(f"{self.MAGENTA}Starting Speed Test Client{self.RESET}")
        print(f"{self.MAGENTA}Press Ctrl+C to exit{self.RESET}")

        while self.running:
            try:
                self.file_size = self._get_file_size()
                self.state = ClientState.SERVER_DISCOVERY
                self._setup_udp_socket()
                self._discover_server()
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"{self.RED}Error in main loop: {e}{self.RESET}")
                time.sleep(1)

        self._cleanup()

    def _setup_udp_socket(self):
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

    def _discover_server(self):
        """Discover speed test servers with improved timeout handling."""
        print(f"{self.YELLOW}Looking for speed test server...{self.RESET}")

        TIMEOUT_INTERVAL = 1.0
        EXPECTED_MSG_SIZE = 9  # Magic(4) + Type(1) + UDP(2) + TCP(2)
        SERVER_MSG_TYPE = 0x2

        while self.running and self.state == ClientState.SERVER_DISCOVERY:
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

                            self._run_speed_test(
                                server_host=server_address[0],
                                udp_port=server_udp_port,
                                tcp_port=server_tcp_port
                            )
                            break

            except Exception as e:
                print(f"{self.RED}Error discovering server: {e}{self.RESET}")
                time.sleep(1)

    def _run_tcp_test(self, server_host, server_port, test_number):
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

        while attempt_count < self.max_attempts and self.running:
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

                while bytes_received < self.file_size and self.running:
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

###############################################################

    def _run_udp_test(self, server_host, server_port, transfer_num):
        """
        Perform UDP speed test with improved packet tracking and error handling.
        """
        udp_socket = None
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.settimeout(5.0)
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 8388608)

            request = struct.pack('!IbQ', self.magic_cookie, 0x3, self.file_size)
            udp_socket.sendto(request, (server_host, server_port))

            received_segments = set()
            total_segments = None
            start_time = time.time()
            last_packet_time = start_time

            while (time.time() - last_packet_time) < 5.0 and self.running:
                try:
                    readable, _, _ = select.select([udp_socket], [], [], 1.0)
                    if not readable:
                        continue

                    data, _ = udp_socket.recvfrom(4096)
                    if len(data) < 21:
                        continue

                    header = data[:21]
                    magic_cookie, msg_type, total_segs, current_seg = struct.unpack('!IbQQ', header)

                    if magic_cookie != self.magic_cookie or msg_type != 0x4:
                        continue

                    if total_segments is None:
                        total_segments = total_segs

                    received_segments.add(current_seg)
                    with self.connection_lock:
                        self.statistics['udp_packets_received'] += 1
                    last_packet_time = time.time()

                    if len(received_segments) == total_segments:
                        break

                except socket.timeout:
                    break

            end_time = time.time()
            transfer_time = end_time - start_time

            if total_segments:
                packets_lost = total_segments - len(received_segments)
                loss_rate = (packets_lost / total_segments) * 100
                speed = (self.file_size * 8) / transfer_time

                with self.connection_lock:
                    self.statistics['udp_times'].append(transfer_time)
                    self.statistics['udp_packets_lost'] += packets_lost

                print(f"\033[92mUDP transfer #{transfer_num} finished:"
                      f" Time: {transfer_time:.3f}s,"
                      f" Speed: {speed:.2f} bits/second,"
                      f" Success rate: {100 - loss_rate:.2f}%\033[0m")
            else:
                print(f"\033[91mUDP transfer #{transfer_num} failed: No segments received\033[0m")

        except Exception as e:
            print(f"\033[91mUDP transfer #{transfer_num} error: {e}\033[0m")
        finally:
            if udp_socket:
                udp_socket.close()

    def _run_speed_test(self, server_host, udp_port, tcp_port):
        """
        Coordinate speed tests with improved thread management and connection throttling.
        """
        tcp_threads = []
        udp_threads = []

        try:
            num_tcp = int(input("\033[96mEnter number of TCP connections: \033[0m"))
            num_udp = int(input("\033[96mEnter number of UDP connections: \033[0m"))
        except ValueError:
            print("\033[91mInvalid input, using default values (1 each)\033[0m")
            num_tcp = num_udp = 1

        # Reset statistics for new test
        with self.connection_lock:
            self.statistics = {
                'tcp_times': [],
                'udp_times': [],
                'udp_packets_received': 0,
                'udp_packets_lost': 0,
                'tcp_connection_failures': 0,
                'tcp_transfer_failures': 0,
                'successful_connections': 0
            }

        # Add delay between connection attempts to prevent overwhelming the server
        delay_between_connections = 0.05  # 50ms delay

        # Start TCP test threads with delay
        for i in range(num_tcp):
            if not self.running:
                break
            tcp_thread = threading.Thread(
                target=self._run_tcp_test,
                args=(server_host, tcp_port, i + 1)
            )
            tcp_threads.append(tcp_thread)
            tcp_thread.start()
            time.sleep(delay_between_connections)

        # Start UDP test threads with delay
        for i in range(num_udp):
            if not self.running:
                break
            udp_thread = threading.Thread(
                target=self._run_udp_test,
                args=(server_host, udp_port, i + 1)
            )
            udp_threads.append(udp_thread)
            udp_thread.start()
            time.sleep(delay_between_connections)

        # Wait for all threads to complete with timeout
        end_time = time.time() + 60  # 60 second timeout
        for thread in tcp_threads + udp_threads:
            remaining_time = max(0, end_time - time.time())
            thread.join(timeout=remaining_time)

        self._print_statistics()
        print("\033[93mAll transfers complete, listening for new offers\033[0m")
        self.state = ClientState.LOOKING_FOR_SERVER

    def _print_statistics(self):
        """Display comprehensive test results and statistics."""
        print("\n\033[95m=== Speed Test Statistics ===\033[0m")

        with self.connection_lock:
            if self.statistics['tcp_times']:
                avg_tcp = statistics.mean(self.statistics['tcp_times'])
                print(f"\033[96mTCP Statistics:")
                print(f"- Average Time: {avg_tcp:.3f}s")
                print(f"- Average Speed: {(self.file_size * 8 / avg_tcp):.2f} bits/second")
                print(f"- Successful Connections: {self.statistics['successful_connections']}")
                print(f"- Connection Failures: {self.statistics['tcp_connection_failures']}")
                print(f"- Transfer Failures: {self.statistics['tcp_transfer_failures']}\033[0m")

            if self.statistics['udp_times']:
                avg_udp = statistics.mean(self.statistics['udp_times'])
                total_packets = self.statistics['udp_packets_received'] + self.statistics['udp_packets_lost']
                loss_rate = (self.statistics['udp_packets_lost'] / total_packets * 100) if total_packets > 0 else 0
                print(f"\033[96mUDP Statistics:")
                print(f"- Average Time: {avg_udp:.3f}s")
                print(f"- Average Speed: {(self.file_size * 8 / avg_udp):.2f} bits/second")
                print(f"- Packet Loss Rate: {loss_rate:.2f}%\033[0m")

    def _cleanup(self):
        """Clean up resources before exiting."""
        try:
            if hasattr(self, 'udp_socket'):
                self.udp_socket.close()
        except Exception as e:
            print(f"\033[91mError during cleanup: {e}\033[0m")


if __name__ == "__main__":
    client = Client()
    client.start()