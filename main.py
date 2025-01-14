import argparse
from Server import Server
from Client import Client
import time


def main():
    import time  # Ensure this is imported
    parser = argparse.ArgumentParser(description="Network Speed Test Application")
    parser.add_argument("--mode", choices=["server", "client"], required=True, help="Run as server or client")
    args = parser.parse_args()

    if args.mode == "server":
        print("Initializing the server...")  # Debug print
        server = Server(udp_port=13117, tcp_port=12345)
        print("Starting the server...")  # Debug print
        server.start_server()
        print("Server is running.")  # Debug print
    elif args.mode == "client":
        print("Initializing the client...")  # Debug print
        client = Client(udp_port=13117)
        print("Starting the client...")  # Debug print
        client.start_client()
        time.sleep(2)  # Allow server discovery
        print("Connecting to server for the speed test...")  # Debug print
        client.connect_to_server(file_size=1024 * 1024, tcp_connections=1, udp_connections=1)


if __name__ == "__main__":
    main()
