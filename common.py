import struct

MAGIC_COOKIE = 0xabcddcba
OFFER_MESSAGE_TYPE = 0x2
REQUEST_MESSAGE_TYPE = 0x3
PAYLOAD_MESSAGE_TYPE = 0x4

DEFAULT_UDP_PORT = 13117
DEFAULT_TCP_PORT = 12345


def format_offer_message(udp_port, tcp_port):
    return struct.pack('!IBHH', MAGIC_COOKIE, OFFER_MESSAGE_TYPE, udp_port, tcp_port)


def format_request_message(file_size):
    return struct.pack('!IBQ', MAGIC_COOKIE, REQUEST_MESSAGE_TYPE, file_size)


def format_payload_message(total_segments, current_segment, payload):
    return struct.pack('!IBQQ', MAGIC_COOKIE, PAYLOAD_MESSAGE_TYPE, total_segments, current_segment) + payload