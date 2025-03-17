########################################################################
#
# GET File Transfer
#
# When the client connects to the server, it immediately sends a
# 1-byte GET command followed by the requested filename. The server
# checks for the GET and then transmits the file. The file transfer
# from the server is prepended by an 8 byte file size field. These
# formats are shown below.
#
# The server needs to have REMOTE_FILE_NAME defined as a text file
# that the client can request. The client will store the downloaded
# file using the filename LOCAL_FILE_NAME. This is so that you can run
# a server and client from the same directory without overwriting
# files.

# Running the server side, simply paste: python3 file_transfer_protocol_v1.py -r server
# Running the client side, paste : python3 file_transfer_protocol_v1.py -r client
#
########################################################################

import socket
import argparse
import os 

########################################################################

# Define all of the packet protocol field lengths. See the
# corresponding packet formats below.
#CMD_FIELD_LEN = 1 # 1 byte commands sent from the client.
#FILE_SIZE_FIELD_LEN  = 8 # 8 byte file size field.

# Packet format when a GET command is sent from a client, asking for a
# file download:

# -------------------------------------------
# | 1 byte GET command  | ... file name ... |
# -------------------------------------------

# When a GET command is received by the server, it reads the file name
# then replies with the following response:

# -----------------------------------
# | 8 byte file size | ... file ... |
# -----------------------------------

# Define a dictionary of commands. The actual command field value must
# be a 1-byte integer. For now, we only define the "GET" command,
# which tells the server to send a file.

import threading
import struct
import argparse

# Command codes for protocol
CMD_LIST = 0
CMD_GET  = 1
CMD_PUT  = 2

# Default ports
DEFAULT_SDP = 30000  # Service Discovery Port (UDP)
DEFAULT_FSP = 30001  # File Sharing Port (TCP)

# Buffer size for file transfers
BUFFER_SIZE = 4096

def recvall(sock, n):
    """Helper function to receive exactly n bytes from a socket."""
    data = b""
    while len(data) < n:
        packet = sock.recv(n - len(data))
        if not packet:
            break
        data += packet
    return data

class FileSharingServer:
    def __init__(self, shared_dir, sdp=DEFAULT_SDP, fsp=DEFAULT_FSP, service_name="TeamFileShare Service"):
        self.shared_dir = os.path.abspath(shared_dir)
        os.makedirs(self.shared_dir, exist_ok=True)
        self.sdp = sdp
        self.fsp = fsp
        self.service_name = service_name
        self.tcp_socket = None
        self.udp_socket = None
        self.running = True

    def start(self):
        print(f"Starting File Sharing Server...")
        print(f"Shared directory: {self.shared_dir}")
        # Start UDP service discovery listener in a separate thread
        udp_thread = threading.Thread(target=self.udp_listener, daemon=True)
        udp_thread.start()
        # Start TCP server for file sharing
        self.tcp_server()

    def udp_listener(self):
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Allow reuse and broadcast
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket.bind(("", self.sdp))
        print(f"Listening for service discovery messages on UDP port {self.sdp}...")
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                if data.decode().strip() == "SERVICE DISCOVERY":
                    print(f"Received service discovery request from {addr}")
                    self.udp_socket.sendto(self.service_name.encode(), addr)
            except Exception as e:
                print("UDP listener error:", e)

    def tcp_server(self):
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_socket.bind(("", self.fsp))
        self.tcp_socket.listen(5)
        print(f"Listening for file sharing connections on TCP port {self.fsp}...")
        while self.running:
            try:
                client_sock, client_addr = self.tcp_socket.accept()
                print(f"Connection received from {client_addr[0]} on port {client_addr[1]}")
                client_thread = threading.Thread(target=self.handle_client, args=(client_sock, client_addr), daemon=True)
                client_thread.start()
            except Exception as e:
                print("TCP server error:", e)

    def handle_client(self, conn, addr):
        with conn:
            while True:
                try:
                    # Read command byte
                    cmd_byte = conn.recv(1)
                    if not cmd_byte:
                        break
                    cmd = cmd_byte[0]
                    if cmd == CMD_LIST:
                        # List command: no additional data expected.
                        files = os.listdir(self.shared_dir)
                        listing = "\n".join(files)
                        data = listing.encode()
                        # Send 4-byte length followed by listing data
                        conn.sendall(struct.pack("!I", len(data)))
                        conn.sendall(data)
                    elif cmd in (CMD_GET, CMD_PUT):
                        # First, read 4 bytes: filename length
                        len_bytes = recvall(conn, 4)
                        if len(len_bytes) < 4:
                            break
                        name_len = struct.unpack("!I", len_bytes)[0]
                        # Now read the filename
                        filename_bytes = recvall(conn, name_len)
                        if len(filename_bytes) < name_len:
                            break
                        filename = filename_bytes.decode().strip()
                        file_path = os.path.join(self.shared_dir, filename)
                        if cmd == CMD_GET:
                            # Handle get command: send file size then file data
                            if not os.path.exists(file_path):
                                # Send file size 0 if file doesn't exist
                                conn.sendall(struct.pack("!Q", 0))
                            else:
                                filesize = os.path.getsize(file_path)
                                conn.sendall(struct.pack("!Q", filesize))
                                with open(file_path, "rb") as f:
                                    while True:
                                        chunk = f.read(BUFFER_SIZE)
                                        if not chunk:
                                            break
                                        conn.sendall(chunk)
                        elif cmd == CMD_PUT:
                            # Handle put command: receive file size then file data.
                            # First, read 8 bytes: file size
                            size_bytes = recvall(conn, 8)
                            if len(size_bytes) < 8:
                                break
                            filesize = struct.unpack("!Q", size_bytes)[0]
                            # Write to a temporary file first
                            temp_path = file_path + ".part"
                            received = 0
                            with open(temp_path, "wb") as f:
                                while received < filesize:
                                    chunk = conn.recv(min(BUFFER_SIZE, filesize - received))
                                    if not chunk:
                                        break
                                    f.write(chunk)
                                    received += len(chunk)
                            # Only rename if fully received
                            if received == filesize:
                                os.rename(temp_path, file_path)
                                print(f"Received and stored file: {filename}")
                            else:
                                # Remove partial file if incomplete
                                if os.path.exists(temp_path):
                                    os.remove(temp_path)
                                print(f"Incomplete file transfer for {filename} from {addr}")
                    else:
                        print(f"Unknown command {cmd} from {addr}")
                except Exception as e:
                    print(f"Error handling client {addr}: {e}")
                    break
            print(f"Connection closed for {addr}")

class FileSharingClient:
    def __init__(self, local_dir, sdp=DEFAULT_SDP, fsp=DEFAULT_FSP):
        self.local_dir = os.path.abspath(local_dir)
        os.makedirs(self.local_dir, exist_ok=True)
        self.sdp = sdp
        self.fsp = fsp
        self.tcp_socket = None

    def scan(self):
        """Broadcast a service discovery message and print any server responses."""
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        udp_sock.settimeout(3)  # 3 second timeout
        message = "SERVICE DISCOVERY".encode()
        server_list = []
        try:
            udp_sock.sendto(message, ('255.255.255.255', self.sdp))
            while True:
                try:
                    data, addr = udp_sock.recvfrom(1024)
                    service = data.decode().strip()
                    print(f"{service} found at {addr[0]}:{addr[1]}")
                    server_list.append((service, addr))
                except socket.timeout:
                    break
        finally:
            udp_sock.close()
        if not server_list:
            print("No service found.")
        return server_list

    def connect(self, ip, port):
        """Establish a TCP connection to the server."""
        self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_socket.connect((ip, int(port)))
        print(f"Connected to server at {ip}:{port}")

    def llist(self):
        """List files in the local sharing directory."""
        files = os.listdir(self.local_dir)
        print("Local files:")
        for f in files:
            print(f)

    def rlist(self):
        """Send list command to the server and print the remote directory listing."""
        if not self.tcp_socket:
            print("Not connected to any server.")
            return
        try:
            # Send list command (CMD_LIST)
            self.tcp_socket.sendall(bytes([CMD_LIST]))
            # Receive 4 bytes length
            len_bytes = recvall(self.tcp_socket, 4)
            if len(len_bytes) < 4:
                print("Error receiving remote list length.")
                return
            data_len = struct.unpack("!I", len_bytes)[0]
            data = recvall(self.tcp_socket, data_len)
            listing = data.decode()
            print("Remote files:")
            print(listing)
        except Exception as e:
            print("Error during rlist:", e)

    def put(self, filename):
        """Upload a file to the server."""
        if not self.tcp_socket:
            print("Not connected to any server.")
            return
        file_path = os.path.join(self.local_dir, filename)
        if not os.path.exists(file_path):
            print(f"Local file {filename} does not exist.")
            return
        try:
            # Send put command (CMD_PUT)
            self.tcp_socket.sendall(bytes([CMD_PUT]))
            # Send filename length and filename
            filename_bytes = filename.encode()
            self.tcp_socket.sendall(struct.pack("!I", len(filename_bytes)))
            self.tcp_socket.sendall(filename_bytes)
            # Send file size and file data
            filesize = os.path.getsize(file_path)
            self.tcp_socket.sendall(struct.pack("!Q", filesize))
            with open(file_path, "rb") as f:
                while True:
                    chunk = f.read(BUFFER_SIZE)
                    if not chunk:
                        break
                    self.tcp_socket.sendall(chunk)
            print(f"Uploaded {filename} to server.")
        except Exception as e:
            print("Error during put:", e)

    def get(self, filename):
        """Download a file from the server."""
        if not self.tcp_socket:
            print("Not connected to any server.")
            return
        try:
            # Send get command (CMD_GET)
            self.tcp_socket.sendall(bytes([CMD_GET]))
            # Send filename length and filename
            filename_bytes = filename.encode()
            self.tcp_socket.sendall(struct.pack("!I", len(filename_bytes)))
            self.tcp_socket.sendall(filename_bytes)
            # Receive 8 bytes file size
            size_bytes = recvall(self.tcp_socket, 8)
            if len(size_bytes) < 8:
                print("Error receiving file size.")
                return
            filesize = struct.unpack("!Q", size_bytes)[0]
            if filesize == 0:
                print(f"File {filename} not found on server.")
                return
            # Receive file data
            file_path = os.path.join(self.local_dir, filename)
            with open(file_path, "wb") as f:
                received = 0
                while received < filesize:
                    chunk = self.tcp_socket.recv(min(BUFFER_SIZE, filesize - received))
                    if not chunk:
                        break
                    f.write(chunk)
                    received += len(chunk)
            if received == filesize:
                print(f"Downloaded {filename} from server.")
            else:
                print("Incomplete download.")
        except Exception as e:
            print("Error during get:", e)

    def bye(self):
        """Close the connection to the server."""
        if self.tcp_socket:
            self.tcp_socket.close()
            self.tcp_socket = None
            print("Disconnected from server.")

    def run(self):
        """Interactive command loop for the client."""
        print("Welcome to the File Sharing Client.")
        print("Available commands: scan, connect <IP> <port>, llist, rlist, put <filename>, get <filename>, bye, exit")
        while True:
            try:
                cmd = input(">> ").strip()
            except EOFError:
                break
            if not cmd:
                continue
            parts = cmd.split()
            command = parts[0].lower()
            if command == "scan":
                self.scan()
            elif command == "connect" and len(parts) >= 3:
                self.connect(parts[1], parts[2])
            elif command == "llist":
                self.llist()
            elif command == "rlist":
                self.rlist()
            elif command == "put" and len(parts) >= 2:
                self.put(" ".join(parts[1:]))
            elif command == "get" and len(parts) >= 2:
                self.get(" ".join(parts[1:]))
            elif command == "bye":
                self.bye()
            elif command == "exit":
                self.bye()
                break
            else:
                print("Unknown command.")

def main():
    parser = argparse.ArgumentParser(description="Online File Sharing Application")
    subparsers = parser.add_subparsers(dest="role", help="Role to run as: server or client")

    # Server parser
    server_parser = subparsers.add_parser("server", help="Run as server")
    server_parser.add_argument("--dir", required=True, help="Directory to share")
    server_parser.add_argument("--sdp", type=int, default=DEFAULT_SDP, help="Service Discovery Port (UDP)")
    server_parser.add_argument("--fsp", type=int, default=DEFAULT_FSP, help="File Sharing Port (TCP)")
    server_parser.add_argument("--name", default="TeamFileShare Service", help="Service name to advertise")

    # Client parser
    client_parser = subparsers.add_parser("client", help="Run as client")
    client_parser.add_argument("--dir", required=True, help="Local directory for file sharing")
    client_parser.add_argument("--sdp", type=int, default=DEFAULT_SDP, help="Service Discovery Port (UDP)")
    client_parser.add_argument("--fsp", type=int, default=DEFAULT_FSP, help="File Sharing Port (TCP)")

    args = parser.parse_args()
    if args.role == "server":
        server = FileSharingServer(shared_dir=args.dir, sdp=args.sdp, fsp=args.fsp, service_name=args.name)
        try:
            server.start()
        except KeyboardInterrupt:
            print("Server shutting down.")
    elif args.role == "client":
        client = FileSharingClient(local_dir=args.dir, sdp=args.sdp, fsp=args.fsp)
        try:
            client.run()
        except KeyboardInterrupt:
            print("Client exiting.")
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
