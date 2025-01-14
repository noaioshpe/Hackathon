import argparse
from Server import Server
from Client import Client
import time


def main():
    parser = argparse.ArgumentParser(description="Network Speed Test Application")
    parser.add_argument("--mode", choices=["server", "client"], required=True, help="Run as server or client")
    args = parser.parse_args()

    if args.mode == "server":
        server = Server(udp_port=13117, tcp_port=12345)
        server.start_server()
    elif args.mode == "client":
        client = Client(udp_port=13117)
        client.start_client()
        time.sleep(2)  # Allow server discovery
        client.connect_to_server(file_size=1024 * 1024, tcp_connections=1, udp_connections=1)


if __name__ == "__main__":
    main()
