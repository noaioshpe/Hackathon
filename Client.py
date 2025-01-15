import concurrent.futures
import socket
from datetime import datetime, timedelta
from general import *


def start_client() -> None:
    file_size = get_positive_integer("Enter the file size to download (positive integer): ", include_zero=False)
    udp_connections_count = get_positive_integer("Enter the number of UDP connections (zero or positive integer): ")
    tcp_connections_count = get_positive_integer("Enter the number of TCP connections (zero or positive integer): ")

    while True:
        server_ip, udp_port, tcp_port = listen_for_offer()
        print_in_color(f"Receive offer from {server_ip}", color=COLORS.GREEN)

        with concurrent.futures.ThreadPoolExecutor() as executor:
            udp_futures = [
                executor.submit(
                    perform_udp_download,
                    server_ip=server_ip, server_port=udp_port, download_size=file_size
                ) for _ in range(udp_connections_count)
            ]
            tcp_futures = [
                executor.submit(
                    perform_tcp_download,
                    server_ip=server_ip, server_port=tcp_port, download_size=file_size
                ) for _ in range(tcp_connections_count)
            ]

            process_tcp_results(tcp_futures)
            process_udp_results(udp_futures)

        print_in_color("All transfers complete, listening to offer requests", color=COLORS.GREEN)


def process_tcp_results(tcp_futures: list) -> None:
    all_speeds = []
    for index, future in enumerate(concurrent.futures.as_completed(tcp_futures)):
        try:
            duration, total_data_received = future.result()
            speed = total_data_received * BITS_IN_BYTE / duration
            print_in_color(
                f"TCP transfer #{index + 1} finished, total time: {duration} seconds, total speed: {humanize_speed(speed)}",
                color=COLORS.LIGHTBLACK_EX
            )
            all_speeds.append(speed)
        except Exception as e:
            print_error(f"An error occurred in a TCP task #{index}: {e}")

    if all_speeds:
        max_speed = max(all_speeds)
        min_speed = min(all_speeds)
        avg_speed = sum(all_speeds) / len(all_speeds)
        print_in_color(
            f"TCP transfers summary:\n\tMax speed: {humanize_speed(max_speed)}\n\tMin speed: {humanize_speed(min_speed)}\n\t"
            f"Average speed: {humanize_speed(avg_speed)}",
            color=COLORS.CYAN
        )


def process_udp_results(udp_futures: list) -> None:
    all_speeds = []
    total_percentage_received = []
    for index, future in enumerate(concurrent.futures.as_completed(udp_futures)):
        try:
            duration, total_data_received, segments_received_count, expected_segments_count = future.result()
            speed = total_data_received * BITS_IN_BYTE / duration
            percentage_received = (
                                              segments_received_count / expected_segments_count) * 100 if expected_segments_count > 0 else 0
            print_in_color(
                f"UDP transfer #{index + 1} finished, total time: {duration} seconds, total speed: {humanize_speed(speed)}, percentage of packets received: {percentage_received}%",
                color=COLORS.LIGHTBLACK_EX
            )

            all_speeds.append(speed)
            total_percentage_received.append(percentage_received)
        except Exception as e:
            print_error(f"An error occurred in a UDP task: {e}")

    if all_speeds:
        max_speed = max(all_speeds)
        min_speed = min(all_speeds)
        avg_speed = sum(all_speeds) / len(all_speeds)
        avg_loss = 100 - (
            sum(total_percentage_received) / len(total_percentage_received) if total_percentage_received else 0)
        print_in_color(
            f"UDP transfers summary:\n\tMax speed: {humanize_speed(max_speed)}\n\tMin speed: {humanize_speed(min_speed)}\n\t"
            f"Average speed: {humanize_speed(avg_speed)}\n\tAverage packet loss: {avg_loss}%",
            color=COLORS.CYAN
        )


def get_positive_integer(message: str, include_zero: bool = True) -> int:
    while True:
        try:
            value = int(input(message))
            if value < 0 or (value == 0 and not include_zero):
                print_error(f"Value must be {'zero or ' if include_zero else ''}a positive integer. Please try again.")
            else:
                return value
        except ValueError:
            print_error("Invalid input. Please enter a numeric value.")


def humanize_speed(bits_per_second: float) -> str:
    units = ["bits/s", "Kib/s", "Mib/s", "Gib/s", "Tib/s", "Pib/s"]  # 2^0 , 2^10..
    scale = 1024  # Using base 2 (Kibi)
    for unit in units:
        if bits_per_second < scale:
            return f"{bits_per_second:.2f} {unit}"
        bits_per_second /= scale
    return f"{bits_per_second:.2f} {units[-1]}"


def listen_for_offer() -> Tuple[str, int, int]:
    print_in_color("Client started, listening for offer requests...", color=COLORS.GREEN)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:  # Open UDP Socket (IP, UDP)
        sock.bind(("", BROADCAST_PORT))  # Listen to BROADCAST_PORT

        while True:
            offer_message, (server_ip, server_port) = sock.recvfrom(BUFFER_SIZE)
            if is_valid_offer(offer_message):
                message_type, (udp_port, tcp_port) = parse_message(offer_message)
                return server_ip, udp_port, tcp_port


def is_valid_offer(offer_message: bytes) -> bool:
    try:
        message_type, *_ = parse_message(offer_message)
        return message_type == OFFER_MESSAGE_TYPE
    except ValueError as e:
        print_in_color(f"DBG: Got invalid offer message - {e}. Keep trying...", color=COLORS.LIGHTYELLOW_EX)
        return False


def perform_udp_download(server_ip: str, server_port: int, download_size: int) -> Tuple[float, int, int, int]:
    request_message = build_message(REQUEST_MESSAGE_TYPE, download_size)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind(("", 0))
        sock.settimeout(UDP_TIMEOUT)

        sock.sendto(request_message, (server_ip, server_port))

        segments_received_count = 0
        expected_segments_count = 1
        total_data_received = 0

        start_time = datetime.now()

        while True:
            try:
                message = sock.recv(BUFFER_SIZE)
                message_type, (expected_segments_count, current_segment, payload) = parse_message(message)
                segments_received_count += 1
                total_data_received += len(payload)
            except socket.timeout:
                break
            except ValueError as e:
                print_error(f"Corrupted Message: {e}")

        end_time = datetime.now()

        duration_seconds = (end_time - start_time - timedelta(seconds=UDP_TIMEOUT)).total_seconds()
        return duration_seconds, total_data_received, segments_received_count, expected_segments_count


def perform_tcp_download(server_ip: str, server_port: int, download_size: int) -> Tuple[float, int]:
    request_message = build_message(REQUEST_MESSAGE_TYPE, download_size, payload=TCP_MESSAGE_TERMINATOR)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:  # Open TCP Socket (IP, TCP)
        sock.connect((server_ip, server_port))
        sock.sendall(request_message)

        start_time = datetime.now()

        response = sock.recv(download_size)  # could be problematic with larger files

        end_time = datetime.now()

        duration_seconds = (end_time - start_time).total_seconds()
        return duration_seconds, len(response)


if __name__ == '__main__':
    try:
        start_client()
    except KeyboardInterrupt:
        print_in_color("Client stopped by user", color=COLORS.RED)
