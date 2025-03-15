#!/usr/bin/env python3

########################################################################
#
# File Sharing Application
#
# This program implements a simple file-sharing server and client.
# The server listens for connections and handles LIST, GET, and PUT
# commands. The client can request a file list, download a file, and
# upload a file.
#
# Running the server: python3 file_transfer_protocol_v1.py -r server
# Running the client: python3 file_transfer_protocol_v1.py -r client
#
########################################################################

import socket
import argparse
import os 

########################################################################

# Define all of the packet protocol field lengths
CMD_FIELD_LEN = 1 # 1 byte commands sent from the client
FILE_SIZE_FIELD_LEN  = 8 # 8 byte file size field

CMD = { 
    "LIST": 1,
    "GET" : 2,
    "PUT" : 3,
    "BYE" : 4
}

MSG_ENCODING = "utf-8"
SHARED_DIR = "shared_files"
    
########################################################################
# SERVER
########################################################################

class Server:
    HOSTNAME = "127.0.0.1"
    PORT = 30001
    RECV_SIZE = 1024
    BACKLOG = 5
    FILE_NOT_FOUND_MSG = "Error: Requested file is not available!"
    
    def __init__(self):
        if not os.path.exists(SHARED_DIR):
            os.makedirs(SHARED_DIR)

        self.create_listen_socket()
        self.process_connections_forever()

    def create_listen_socket(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((Server.HOSTNAME, Server.PORT))
            self.socket.listen(Server.BACKLOG)
            print(f"Listening on {Server.HOSTNAME}:{Server.PORT}...")
        except Exception as msg:
            print(f"Socket error: {msg}")
            exit()

    def process_connections_forever(self):
        print("Waiting for client connections...")
        try:
            while True:
                client_socket, client_address = self.socket.accept()
                print(f"New connection from {client_address}")
                self.connection_handler((client_socket, client_address))
        except KeyboardInterrupt:
            print("Server shutting down...")
        finally:
            self.socket.close()

    def connection_handler(self, client):
        connection, address = client
        print(f"Handling connection from {address}.")

        while True:
            try:
                cmd = connection.recv(CMD_FIELD_LEN)
                if not cmd:
                    break  # Client disconnected
                cmd_int = int.from_bytes(cmd, byteorder='big')

                if cmd_int == CMD["LIST"]:
                    file_list = os.listdir(SHARED_DIR)
                    response = "\n".join(file_list) if file_list else "No files available"
                    connection.sendall(len(response).to_bytes(8, 'big') + response.encode(MSG_ENCODING))

                elif cmd_int == CMD["GET"]:
                    filename = connection.recv(Server.RECV_SIZE).decode(MSG_ENCODING)
                    filepath = os.path.join(SHARED_DIR, filename)
                    if os.path.exists(filepath):
                        with open(filepath, 'rb') as f:
                            file_data = f.read()
                        connection.sendall(len(file_data).to_bytes(8, 'big') + file_data)
                    else:
                        connection.sendall(b"FILE_NOT_FOUND")

                elif cmd_int == CMD["PUT"]:
                    filename = connection.recv(Server.RECV_SIZE).decode(MSG_ENCODING)
                    file_size = int.from_bytes(connection.recv(8), 'big')
                    received_data = connection.recv(file_size)
                    with open(os.path.join(SHARED_DIR, filename), 'wb') as f:
                        f.write(received_data)
                    connection.sendall(b"UPLOAD_SUCCESS")

                elif cmd_int == CMD["BYE"]:
                    print(f"Client {address} disconnected.")
                    break
            except Exception as e:
                print(f"Error with client {address}: {e}")
                break
        connection.close()

########################################################################
# CLIENT
########################################################################

class Client:
    RECV_SIZE = 1024
    
    def __init__(self):
        self.get_socket()
        self.connect_to_server()
        self.run()

    def run(self):
        while True:
            command = input("Enter command (list, get <file>, put <file>, bye): ").strip().split()
            if command[0] == "list":
                self.list_files()
            elif command[0] == "get" and len(command) > 1:
                self.get_file(command[1])
            elif command[0] == "put" and len(command) > 1:
                self.put_file(command[1])
            elif command[0] == "bye":
                self.disconnect()
                break
            else:
                print("Invalid command!")

    def list_files(self):
        self.socket.sendall(CMD["LIST"].to_bytes(1, 'big'))
        file_list_size = int.from_bytes(self.socket.recv(8), 'big')
        file_list = self.socket.recv(file_list_size).decode(MSG_ENCODING)
        print("Shared Files:\n" + file_list)

    def get_socket(self):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except Exception as msg:
            print(msg)
            exit()

    def connect_to_server(self):
        try:
            self.socket.connect((Server.HOSTNAME, Server.PORT))
        except Exception as msg:
            print(msg)
            exit()

    def disconnect(self):
        self.socket.sendall(CMD["BYE"].to_bytes(1, 'big'))
        self.socket.close()
        print("Disconnected from server.")

########################################################################

if __name__ == '__main__':
    roles = {'client': Client, 'server': Server}
    parser = argparse.ArgumentParser()
    parser.add_argument('-r', '--role', choices=roles, help='server or client role', required=True, type=str)
    args = parser.parse_args()
    roles[args.role]()
########################################################################
