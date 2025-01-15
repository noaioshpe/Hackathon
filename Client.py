import socket
import struct
import threading
import time


class Client:
    def __init__(self):
        self.running = False
        self.tcp_stats = {
            'times': [],
            'speeds': [],
            'successful_connections': 0,
            'connection_failures': 0,
            'transfer_failures': 0
        }
        self.udp_stats = {
            'times': [],
            'speeds': [],
            'packet_loss_rates': []
        }

    def start_client(self):
        """Start the client and begin listening for offers"""
        self.running = True
        print("Starting Speed Test Client")
        print("Press Ctrl+C to exit")

        try:
            while self.running:
                # Reset statistics for new test
                self._reset_statistics()

                # Get initial file size
                file_size = self._get_file_size()
                if not file_size:
                    continue

                print("Looking for speed test server...")
                server_info = self._wait_for_server()
                if not server_info:
                    continue

                server_ip, tcp_port, udp_port = server_info

                # Get connection counts
                tcp_count = self._get_tcp_count()
                udp_count = self._get_udp_count()
                if not all([tcp_count, udp_count]):
                    continue

                # Run the speed tests
                self._run_speed_tests(server_ip, tcp_port, udp_port, file_size, tcp_count, udp_count)

                # Print statistics
                self._print_statistics()

                print("All transfers complete, listening for new offers")

        except KeyboardInterrupt:
            print("\nShutting down client...")
        finally:
            self.stop_client()

    def _reset_statistics(self):
        """Reset all statistics for new test"""
        self.tcp_stats = {
            'times': [],
            'speeds': [],
            'successful_connections': 0,
            'connection_failures': 0,
            'transfer_failures': 0
        }
        self.udp_stats = {
            'times': [],
            'speeds': [],
            'packet_loss_rates': []
        }

    def _get_file_size(self):
        """Get file size from user"""
        while self.running:
            try:
                size = input("Enter file size for speed test (in bytes): ")
                if size.strip() == "":
                    continue
                size = int(size)
                if size <= 0:
                    print("Please enter a positive number")
                    continue
                return size
            except ValueError:
                print("Please enter a valid number")
        return None

    def _get_tcp_count(self):
        """Get number of TCP connections from user"""
        while self.running:
            try:
                count = input("Enter number of TCP connections: ")
                if count.strip() == "":
                    continue
                count = int(count)
                if count <= 0:
                    print("Please enter a positive number")
                    continue
                return count
            except ValueError:
                print("Please enter a valid number")
        return None

    def _get_udp_count(self):
        """Get number of UDP connections from user"""
        while self.running:
            try:
                count = input("Enter number of UDP connections: ")
                if count.strip() == "":
                    continue
                count = int(count)
                if count <= 0:
                    print("Please enter a positive number")
                    continue
                return count
            except ValueError:
                print("Please enter a valid number")
        return None

    def _wait_for_server(self):
        """Wait for server offer"""
        udp_socket = None
        try:
            udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            udp_socket.settimeout(1.0)
            udp_socket.bind(('', 13117))

            while self.running:
                try:
                    data, addr = udp_socket.recvfrom(1024)

                    if len(data) < 9:
                        continue

                    magic_cookie, msg_type, udp_port, tcp_port = struct.unpack('!IbHH', data[:9])

                    if magic_cookie != 0xabcddcba or msg_type != 0x2:
                        continue

                    server_ip = addr[0]
                    print(f"Received offer from {server_ip}")
                    return server_ip, tcp_port, udp_port

                except socket.timeout:
                    continue

        except Exception as e:
            print(f"Error waiting for server: {e}")
        finally:
            if udp_socket:
                udp_socket.close()
        return None

    def _run_single_tcp_test(self, server_ip, tcp_port, file_size, test_num):
        """Run single TCP speed test"""
        tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tcp_socket.settimeout(5.0)

        try:
            # Connect to server
            tcp_socket.connect((server_ip, tcp_port))
            self.tcp_stats['successful_connections'] += 1

            # Send file size request
            tcp_socket.send(f"{file_size}\n".encode())

            # Receive data and measure time
            start_time = time.time()
            bytes_received = 0

            while bytes_received < file_size:
                data = tcp_socket.recv(4096)
                if not data:
                    # If no data received, consider it a transfer failure
                    if bytes_received == 0:
                        raise Exception("No data received from server")
                    break
                bytes_received += len(data)

            # Check if we received any data
            if bytes_received == 0:
                raise Exception("No data received from server")

            # Calculate duration and speed (ensure non-zero duration)
            end_time = time.time()
            duration = max(end_time - start_time, 0.001)  # Ensure duration is not zero
            speed = (bytes_received * 8) / duration  # Use actual bytes received

            # Update statistics
            self.tcp_stats['times'].append(duration)
            self.tcp_stats['speeds'].append(speed)

            print(f"TCP transfer #{test_num} finished: Time: {duration:.3f}s, Speed: {speed:.2f} bits/second")

        except ConnectionError:
            self.tcp_stats['connection_failures'] += 1
            print(f"TCP transfer #{test_num} failed: Connection error")
        except Exception as e:
            self.tcp_stats['transfer_failures'] += 1
            print(f"TCP transfer #{test_num} failed: {str(e)}")
        finally:
            tcp_socket.close()

    def _run_single_udp_test(self, server_ip, udp_port, file_size, test_num):
        """Run single UDP speed test"""
        udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_socket.settimeout(1.0)

        try:
            request = struct.pack('!IbQ', 0xabcddcba, 0x3, file_size)
            udp_socket.sendto(request, (server_ip, udp_port))

            start_time = time.time()
            received_segments = set()
            total_segments = None
            last_receive_time = time.time()

            while True:
                try:
                    data, _ = udp_socket.recvfrom(2048)

                    if len(data) < 21:
                        continue

                    magic_cookie, msg_type, total_segs, current_seg = struct.unpack('!IbQQ', data[:21])

                    if magic_cookie != 0xabcddcba or msg_type != 0x4:
                        continue

                    total_segments = total_segs
                    received_segments.add(current_seg)
                    last_receive_time = time.time()

                except socket.timeout:
                    if time.time() - last_receive_time >= 1.0:
                        break

            duration = time.time() - start_time
            speed = (file_size * 8) / duration

            if total_segments:
                loss_rate = 100 - (len(received_segments) / total_segments * 100)
            else:
                loss_rate = 100

            self.udp_stats['times'].append(duration)
            self.udp_stats['speeds'].append(speed)
            self.udp_stats['packet_loss_rates'].append(loss_rate)

            print(f"UDP transfer #{test_num} finished: Time: {duration:.3f}s, "
                  f"Speed: {speed:.2f} bits/second, Success rate: {100 - loss_rate:.2f}%")

        except Exception as e:
            print(f"UDP transfer #{test_num} failed: {str(e)}")
        finally:
            udp_socket.close()

    def _run_speed_tests(self, server_ip, tcp_port, udp_port, file_size, tcp_count, udp_count):
        """Run all speed tests"""
        threads = []

        for i in range(udp_count):
            thread = threading.Thread(
                target=self._run_single_udp_test,
                args=(server_ip, udp_port, file_size, i + 1)
            )
            thread.start()
            threads.append(thread)

        for i in range(tcp_count):
            thread = threading.Thread(
                target=self._run_single_tcp_test,
                args=(server_ip, tcp_port, file_size, i + 1)
            )
            thread.start()
            threads.append(thread)

        for thread in threads:
            thread.join()

    def _print_statistics(self):
        """Print test statistics"""
        print("\n=== Speed Test Statistics ===")

        print("TCP Statistics:")
        if self.tcp_stats['times']:
            avg_time = sum(self.tcp_stats['times']) / len(self.tcp_stats['times'])
            avg_speed = sum(self.tcp_stats['speeds']) / len(self.tcp_stats['speeds'])
            print(f"- Average Time: {avg_time:.3f}s")
            print(f"- Average Speed: {avg_speed:.2f} bits/second")
        print(f"- Successful Connections: {self.tcp_stats['successful_connections']}")
        print(f"- Connection Failures: {self.tcp_stats['connection_failures']}")
        print(f"- Transfer Failures: {self.tcp_stats['transfer_failures']}")

        print("\nUDP Statistics:")
        if self.udp_stats['times']:
            avg_time = sum(self.udp_stats['times']) / len(self.udp_stats['times'])
            avg_speed = sum(self.udp_stats['speeds']) / len(self.udp_stats['speeds'])
            avg_loss = sum(self.udp_stats['packet_loss_rates']) / len(self.udp_stats['packet_loss_rates'])
            print(f"- Average Time: {avg_time:.3f}s")
            print(f"- Average Speed: {avg_speed:.2f} bits/second")
            print(f"- Packet Loss Rate: {avg_loss:.2f}%")

    def stop_client(self):
        """Stop the client"""
        self.running = False


if __name__ == "__main__":
    client = Client()
    client.start_client()