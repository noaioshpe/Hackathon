import time
import threading
import socket
import math
from general import *

# Configuration
BROADCAST_INTERVAL_SECONDS: int = 1
BROADCAST_TARGET_ADDRESS: Tuple[str, int] = ("255.255.255.255", BROADCAST_PORT)
UDP_CHUNK_SIZE: int = 512


def start_server():
    server_ip = resolve_server_ip()
    announce_server_start(server_ip)

    # Launch server threads
    threads = [
        threading.Thread(target=broadcast_offers, args=(UDP_SERVER_PORT, TCP_SERVER_PORT)),
        threading.Thread(target=setup_tcp_service, args=(server_ip, TCP_SERVER_PORT)),
        threading.Thread(target=setup_udp_service, args=(server_ip, UDP_SERVER_PORT))
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()


def resolve_server_ip() -> str:
    """Retrieve the server's local IP address."""
    return socket.gethostbyname(socket.gethostname())


def announce_server_start(ip_address: str):
    """Print a message indicating the server has started."""
    print_in_color(f"Server started, listening on IP address {ip_address}", color=COLORS.BLUE)


def broadcast_offers(udp_port: int, tcp_port: int):
    """Broadcast periodic offer messages."""
    message = prepare_offer_message(udp_port, tcp_port)
    while True:
        transmit_broadcast_message(message)
        time.sleep(BROADCAST_INTERVAL_SECONDS)


def prepare_offer_message(udp_port: int, tcp_port: int) -> bytes:
    """Create the offer message to broadcast."""
    return build_message(OFFER_MESSAGE_TYPE, udp_port, tcp_port)


###readme
def transmit_broadcast_message(message: bytes):
    """Send a broadcast message over UDP."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            udp_socket.sendto(message, BROADCAST_TARGET_ADDRESS)
            print_in_color("DBG: Broadcast offer sent.", color=COLORS.LIGHTYELLOW_EX)
        except Exception as e:
            print_error(f"Broadcast transmission error: {e}")


######################################################################
def initialize_tcp_service(ip: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp_socket:
            tcp_socket.bind((ip, port))
            tcp_socket.listen(5)
            print_in_color(f"DBG: TCP server listening on {ip}:{port}", color=COLORS.LIGHTYELLOW_EX)

        while True:
            try:
                client_socket, client_address = tcp_socket.accept()
                print_in_color(f"DBG: Connection from {client_address}", color=COLORS.LIGHTYELLOW_EX)
                threading.Thread(target=process_tcp_request, args=(client_socket,)).start()
            except Exception as e:
                print_error(f"Error in TCP server: {e}")


##FIXME#####################
def process_tcp_request(client_socket: socket.socket):
    with client_socket:
        try:
            message: bytes = client_socket.recv(BUFFER_SIZE)
            if message[-1] != ord(TCP_MESSAGE_TERMINATOR):
                raise ValueError("Message is too large or improperly terminated with '\\n'.")

            file_size = parse_request_message(message)
            print_in_color(f"DBG: Received filesize of {file_size} bytes", color=COLORS.LIGHTYELLOW_EX)

            response: bytes = b"a" * file_size
            client_socket.sendall(response)
            print_in_color(f"DBG: Sent response of length: {len(response)}", color=COLORS.LIGHTYELLOW_EX)
        except Exception as e:
            print_error(f"Error processing TCP client request: {e}")


def initialize_udp_service(server_ip: str, server_port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        udp_socket.bind((server_ip, server_port))
        print_in_color(f"DBG: UDP server listening on {server_ip}:{server_port}", color=COLORS.LIGHTYELLOW_EX)

        while True:
            try:
                message, client_address = udp_socket.recvfrom(BUFFER_SIZE)
                print_in_color(f"DBG: Received message from {client_address}: {message}", color=COLORS.LIGHTYELLOW_EX)

                threading.Thread(
                    target=handle_udp_client_request,
                    args=(client_address, message)
                ).start()
            except Exception as e:
                print_error(f"Error in UDP server: {e}")


def handle_udp_client_request(client_address: Tuple[str, int], message: bytes) -> None:
    try:
        file_size: int = parse_request_message(message)
        print_in_color(f"DBG: Handling UDP client {client_address}, received message: {message}", color=COLORS.LIGHTYELLOW_EX)
        send_udp_file_segments(target_address=client_address, file_size=file_size, payload_size=DEFAULT_UDP_PAYLOAD_SIZE)
    except Exception as e:
        print_error(f"Error processing UDP client {client_address}: {e}")


def send_udp_file_segments(target_address: Tuple[str, int], file_size: int, payload_size: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp_socket:
        total_segments: int = math.ceil(file_size / payload_size)

        for segment_number in range(total_segments):
            bytes_sent = segment_number * payload_size
            remaining_bytes = file_size - bytes_sent
            current_payload_size = min(payload_size, remaining_bytes)
            payload_data: bytes = b'a' * current_payload_size

            payload_message: bytes = build_message(
                PAYLOAD_MESSAGE_TYPE,
                total_segments,
                segment_number,
                payload=payload_data
            )

            udp_socket.sendto(payload_message, target_address)
            print_in_color(f"DBG: Sent segment {segment_number + 1}/{total_segments}, size: {current_payload_size} bytes", color=COLORS.LIGHTYELLOW_EX)


if __name__ == '__main__':
    start_server()