#!/bin/env python3
import socket
import threading
import select
from connection import Connection
from action_signal import Action
from bytes_convert import bytes2int
from time import sleep, time
import errno
from queue import Queue


class Socket:
    def __init__(self,
             port=1234,
             host=socket.gethostbyname(socket.gethostname()),
             BUFFER_SIZE=2048,
             QUEUE_SIZE=100,
             SERVER_EPOLL_BLOCK_TIME=10,
             CLIENT_EPOLL_BLOCK_TIME=1,
             IMMEDIATE_CLIENT_ADD=False):
        """
        :param port: The server port
        :param host: The server host name
        :param BUFFER_SIZE: The maximum size that the server will receive data at one time from a client
        :param QUEUE_SIZE: The maximum number of clients awaiting to be accepted by the server socket
        :param SERVER_EPOLL_BLOCK_TIME:
        :param CLIENT_EPOLL_BLOCK_TIME:
        :param IMMEDIATE_CLIENT_ADD: False = a client can start communicating with the server at MAX after CLIENT_EPOLL_BLOCK_TIME
        after which the client has been accepted
        True = The client epoll object will be triggered at client accept
        """
        # If no host is given the server is hosted on the local ip

        self.serve = True # All mainthreads will run aslong as serve is True
        self.host = host
        self.port = port
        self.BUFFER_SIZE = BUFFER_SIZE
        self.SERVER_EPOLL_BLOCK_TIME = SERVER_EPOLL_BLOCK_TIME
        self.CLIENT_EPOLL_BLOCK_TIME = CLIENT_EPOLL_BLOCK_TIME
        self.IMMEDIATE_CLIENT_ADD = IMMEDIATE_CLIENT_ADD


        # Starting the server socket
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((host, port))
        self.server_socket.listen(QUEUE_SIZE)
        self.server_socket.setblocking(0)

        self.server_epoll = select.epoll()
        self.server_epoll.register(self.server_socket.fileno(), select.EPOLLIN)
        self.client_epoll = select.epoll()

        self.clients = {}  # {fileno:clientobj}

        self.add_queue = Queue(0)
        self.recv_queue = Queue(0)

        # The four main threads
        self.accept_clients_thread = threading.Thread(target=self.accept_clients)  # Uses the server socket to accept new clients
        self.recv_data_thread = threading.Thread(target=self.recv_data)  # Uses the client sockets to recv data
        self.add_client_thread = threading.Thread(target=self.add_client) # Uses the add_queue to register new clients
        self.handle_recv_data_thread = threading.Thread(target=self.handle_recv_data)  # Uses the recv_queue to handle incoming data

    def accept_clients(self):
        """ Uses the server socket to accept incoming connections
            because the server socket is non-blocking epoll is used to block until a client is ready to be accepted
        """
        while self.serve:
            events = self.server_epoll.poll(self.SERVER_EPOLL_BLOCK_TIME)
            for fileno, event in events:
                if event:
                    conn, addr = self.server_socket.accept()
                    self.add_queue.put(Connection(conn, addr))

    def add_client(self):
        """ Adds a client when client is added to the add_queue queue object
        """
        while self.serve:
            conn = self.add_queue.get()
            fileno = conn.fileno()
            self.clients[fileno] = conn
            self.client_epoll.register(fileno, select.EPOLLIN)
            threading.Thread(target=self.on_client_connect, args=(fileno, )).start()

    def recv_data(self):
        """ Receives data from clients and adds it to the recv queue
        """
        while self.serve:
            events = self.client_epoll.poll(self.CLIENT_EPOLL_BLOCK_TIME)
            for fileno, event in events:
                if event:
                    try:
                        data = self.clients[fileno].conn.recv(self.BUFFER_SIZE)
                    except socket.error as e:
                        if e.args[0] not in (errno.EWOULDBLOCK, errno.EAGAIN):
                            # since this is a non-blocking socket.
                            self.unregister(fileno)
                        continue

                    if data == b'':
                        self.unregister(fileno)
                    else:
                        self.recv_queue.put([fileno, data])

    def handle_recv_data(self):
        while self.serve:
            fileno, data = self.recv_queue.get()
            self.clients[fileno].recv_buffer.append(data)
            self.on_message_recv(fileno, data)

    def unregister(self, fileno):
        try:
            self.client_epoll.unregister(fileno)
            threading.Thread(target=self.on_client_disconnect, args=(fileno,)).start()
        except FileNotFoundError:
            self.on_warning('Failed to remove: %s because client not registered in the epoll object' % conn.getip())

    def start(self):
        self.accept_clients_thread.start()
        self.recv_data_thread.start()
        self.add_client_thread.start()
        self.handle_recv_data_thread.start()
        self.on_start()

    # ---------------------------- the "on" functions --------------------------------
    def on_client_connect(self, conn):
        pass

    def on_start(self):
        pass

    def on_message_recv(self, fileno, data):
        # Triggers when server receives a message from the client
        # The message can be found in conn.recv_buffer where each
        # messages up to self.buffer_size is stored in a list
        print(data)

    def on_client_disconnect(self, conn):
        pass

    def on_server_shutting_down(self):
        pass

    def on_server_shut_down(self):
        pass

    def on_warning(self, msg):
        pass

    # --------------------------------------------------------------------------------


if __name__ == '__main__':
    class sock(Socket):
        def __init__(self, port):
            Socket.__init__(self, port, CLIENT_EPOLL_BLOCK_TIME=10)

        def on_start(self):
            print('Server started on: ', self.host, self.port)

        def on_client_connect(self, fileno):
            # print(self.clients[fileno].getip(), 'Connected')
            pass

        def on_message_recv(self, fileno, msg):
            # print(msg)
            # self.clients[fileno].send(b'hello from server\n')
            pass

        def on_client_disconnect(self, fileno):
            # print(self.clients[fileno].getip(), 'Disconnected')
            # self.clients[fileno].close()
            del self.clients[fileno]
            pass
        def on_server_shutting_down(self):
            print('Server shutting down')

        def on_server_shut_down(self):
            print('Server is now closed')

    s = sock(1234)
    s.start()