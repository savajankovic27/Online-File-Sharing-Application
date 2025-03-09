#!/usr/bin/env python3

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
CMD_FIELD_LEN = 1 # 1 byte commands sent from the client.
FILE_SIZE_FIELD_LEN  = 8 # 8 byte file size field.

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

CMD = { 
        "LIST": 1,
        "GET" : 2 ,
        "PUT" : 3,
        "BYE" : 4
       }

MSG_ENCODING = "utf-8"
    
########################################################################
# SERVER
########################################################################

SHARED_DIR = ""

class Server:

    HOSTNAME = "127.0.0.1"

    PORT = 30001
    RECV_SIZE = 1024
    BACKLOG = 5

    FILE_NOT_FOUND_MSG = "Error: Requested file is not available!"

    # This is the file that the client will request using a GET.
    REMOTE_FILE_NAME = "remotefile.txt"
    
    if not os.path.exists(SHARED_DIR):
        os.makedirs(SHARED_DIR)

    def __init__(self):
        self.create_listen_socket()
        self.process_connections_forever()

    def create_listen_socket(self):
        try:
            # Create the TCP server listen socket in the usual way.
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((Server.HOSTNAME, Server.PORT))
            self.socket.listen(Server.BACKLOG)
            print(f"Listening on {Server.HOSTNAME}:{Server.PORT}...")
        except Exception as msg:
            print(f"Socket error:{msg}")
            exit()

    def process_connections_forever(self):
        print("Connecting to the client right now...")
        try:
            while True:
                client_socket, client_address = self.socket.accept();
                print(f"New connection from {client_address}")
                self.connection_handler((client_socket, client_address))
        except KeyboardInterrupt:
            print("Couldn't find a client")
        finally:
            self.socket.close()

    def connection_handler(self, client):
        connection, address = client
        print(f"Handling connection from {address}.")

        while True:
            try:
                # Receive command (1 byte)
                cmd = connection.recv(CMD_FIELD_LEN)
                if not cmd:
                    break  # Client disconnected

                cmd_int = int.from_bytes(cmd, byteorder='big')

                if cmd_int == CMD["LIST"]:
                    # Get list of files and send to client
                    file_list = os.listdir(SHARED_DIR)
                    response = "\n".join(file_list).encode(MSG_ENCODING)
                    connection.sendall(len(response).to_bytes(8, 'big') + response)

                elif cmd_int == CMD["GET"]:
                    # Handle GET (Already implemented)
                    filename = connection.recv(Server.RECV_SIZE).decode(MSG_ENCODING)
                    filepath = os.path.join(SHARED_DIR, filename)
                    
                    if os.path.exists(filepath):
                        with open(filepath, 'rb') as f:
                            file_data = f.read()
                        connection.sendall(len(file_data).to_bytes(8, 'big') + file_data)
                    else:
                        connection.sendall(b"FILE_NOT_FOUND")

                elif cmd_int == CMD["PUT"]:
                    # Handle file upload
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

    RECV_SIZE = 10

    # Define the local file name where the downloaded file will be
    # saved.
    LOCAL_FILE_NAME = "localfile.txt"

    def __init__(self):
        self.get_socket()
        self.connect_to_server()
        self.run()
        
        
    def run(self):
        while True:
            command = input("Enter command (list, get<file>, put<file>,bye): ").strip().split()
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
        self.socket.sendall(CMD["LIST"].to_bytes(1,'big'))
        file_list_size = int.from_bytes(self.socket.recv(8), 'big')
        file_list = self.socket.recv(file_list_size).decode(MSG_ENCODING)
        print("Shared Files :\n" + file_list)
    
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

    def socket_recv_size(self, length):
        bytes = self.socket.recv(length)
        if len(bytes) < length:
            self.socket.close()
            exit()
        return(bytes)
            
    def get_file(self):

        # Create the packet GET field.
        get_field = CMD["GET"].to_bytes(CMD_FIELD_LEN, byteorder='big')

        # Create the packet filename field.
        filename_field = Server.REMOTE_FILE_NAME.encode(MSG_ENCODING)

        # Create the packet.
        pkt = get_field + filename_field

        # Send the request packet to the server.
        self.socket.sendall(pkt)

        # Read the file size field.
        file_size_bytes = self.socket_recv_size(FILE_SIZE_FIELD_LEN)
        if len(file_size_bytes) == 0:
               self.socket.close()
               return

        # Make sure that you interpret it in host byte order.
        file_size = int.from_bytes(file_size_bytes, byteorder='big')

        # Receive the file itself.
        recvd_bytes_total = bytearray()
        try:
            # Keep doing recv until the entire file is downloaded. 
            while len(recvd_bytes_total) < file_size:
                recvd_bytes_total += self.socket.recv(Client.RECV_SIZE)

            # Create a file using the received filename and store the
            # data.
            print("Received {} bytes. Creating file: {}" \
                  .format(len(recvd_bytes_total), Client.LOCAL_FILE_NAME))

            with open(Client.LOCAL_FILE_NAME, 'w') as f:
                f.write(recvd_bytes_total.decode(MSG_ENCODING))
        except KeyboardInterrupt:
            print()
            exit(1)
        # If the socket has been closed by the server, break out
        # and close it on this end.
        except socket.error:
            self.socket.close()
            
########################################################################

if __name__ == '__main__':
    roles = {'client': Client,'server': Server}
    parser = argparse.ArgumentParser()

    parser.add_argument('-r', '--role',
                        choices=roles, 
                        help='server or client role',
                        required=True, type=str)

    args = parser.parse_args()
    roles[args.role]()

########################################################################






