import struct
from typing import Any, Tuple, Union, Dict

from colorama import Fore, Style
from colorama import init as colorama_init

UDP_TIMEOUT = 1  # Timeout used for finishing udp download
BITS_IN_BYTE = 8  # Conversion factor for bytes to bits

UDP_SERVER_PORT: int = 8080
TCP_SERVER_PORT: int = 8081

# Constants
BROADCAST_PORT: int = 12345  # Port used for broadcasting
TCP_MESSAGE_TERMINATOR = "\n".encode()  # Terminator for TCP request messages
BUFFER_SIZE = 1024  # Socket buffer size

# Header format
MAGIC_COOKIE: bytes = 0xabcddcba.to_bytes(4, byteorder="big")  # Magic cookie for protocol validation
HEADER_FORMAT: str = "4sB"  # Protocol (4 bytes) + Message Type (1 byte) - struct format
HEADER_SIZE: int = struct.calcsize(HEADER_FORMAT)  # Size of the header in bytes

# Message types
OFFER_MESSAGE_TYPE: int = 0x2
REQUEST_MESSAGE_TYPE: int = 0x3
PAYLOAD_MESSAGE_TYPE: int = 0x4

# Message formats
MESSAGES_FORMATS: Dict[int, str] = {
    OFFER_MESSAGE_TYPE: ">HH",
    REQUEST_MESSAGE_TYPE: ">Q",
    PAYLOAD_MESSAGE_TYPE: ">QQ",
}


def build_header(message_type: int) -> bytes:
    try:
        return struct.pack(HEADER_FORMAT, MAGIC_COOKIE, message_type)
    except struct.error as e:
        raise ValueError(f"Failed to pack header with type '{message_type}': {e}")


def build_message(message_type: int, *args: Any, payload: bytes = b"") -> bytes:
    if message_type not in MESSAGES_FORMATS:
        raise ValueError(f"Unsupported message type: {message_type}")

    try:
        body = struct.pack(MESSAGES_FORMATS[message_type], *args) + payload
    except struct.error as e:
        raise ValueError(f"Failed to pack values {args} with type '{message_type}': {e}")

    return build_header(message_type) + body


def parse_header(data: bytes) -> int:
    if len(data) < HEADER_SIZE:
        raise ValueError("Data too short to contain a valid header.")

    try:
        magic_cookie, message_type = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])
        if magic_cookie != MAGIC_COOKIE:
            raise ValueError("Invalid magic cookie.")
    except struct.error as e:
        raise ValueError(f"Failed to parse header: {e}")

    return message_type


def parse_message(data: bytes) -> Tuple[int, Union[Tuple[Any, ...], None]]:
    message_type = parse_header(data)

    if message_type in MESSAGES_FORMATS:
        body_format = MESSAGES_FORMATS[message_type]
        body_size = struct.calcsize(body_format)
        body_data = data[HEADER_SIZE:]

        if len(body_data) < body_size:
            raise ValueError("Data too short to contain a valid message body.")

        try:
            parsed_body = struct.unpack(body_format, body_data[:body_size])  # returns Tuple by the struct format
        except struct.error as e:
            raise ValueError(f"Failed to unpack message body for type {message_type}: {e}")

        # Handle variable-length payloads for the payload message type
        if message_type == PAYLOAD_MESSAGE_TYPE:
            payload = body_data[body_size:]
            return message_type, (*parsed_body, payload)

        return message_type, parsed_body

    raise ValueError(f"Unsupported message type: {message_type}")


def parse_request_message(message: bytes) -> int:
    message_type, body = parse_message(message)
    if message_type != REQUEST_MESSAGE_TYPE:
        raise ValueError(f"Got wrong message type, expected {REQUEST_MESSAGE_TYPE} and got {message_type}.")
    return body[0]


###########################################################
# Colors part
colorama_init(autoreset=True)
COLORS = Fore


def print_error(text: str):
    print_in_color(f"{Style.BRIGHT}{text}", COLORS.RED)


def print_in_color(text: str, color: Fore = COLORS.RESET):
    print(f"{color}{text}")
