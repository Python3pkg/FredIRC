# Copyright (c) 2013 Tobias Marquardt
#
# Distributed under terms of the (2-clause) BSD  license.

"""
TODO
"""

from abc import ABCMeta
from abc import abstractmethod
import asyncio
import codecs
import logging
from queue import Queue
from threading import Thread

from fredirc.errors import NotConnectedError


class ConnectionEvent(object):
    CONNECTED = 1
    DATA_AVAILABLE = 2
    SHUTDOWN = 3


class Connection(asyncio.Protocol, metaclass=ABCMeta):
    """ Abstract base class for a connection to an IRC server.

    A Connection wraps a network connection to the server. It uses the asyncio module internally for
    asynchronous communication to the server. The Connection also has a client instance and is responsible
    for forwarding messages from the server to the client and vice versa. The communication with the client
    must be implemented in subclasses by overwriting the abstract methods.

    .. note:: Only start(), terminate() und send_message() should be called from outside of the class (from
        the client object)!
    """

    def __init__(self, client, server, port):
        asyncio.Protocol.__init__(self)
        self._logger = logging.getLogger('FredIRC')
        self._client = client
        self._server = server
        self._port = port
        # Register customized decoding error handler
        codecs.register_error('log_and_replace', self._decoding_error_handler)

    @abstractmethod
    def connection_shutdown(self):
        """ TODO """
        pass

    @abstractmethod
    def connection_initiation(self):
        """ TODO """
        pass

    @abstractmethod
    def message_dispatching(self):
        """ TODO """
        pass

    @abstractmethod
    def start(self):
        """ Establish the connection and run the network event loop.

            This method might be blocking or non-blocking depending on it's actual implementation.
            From outside of the class, this is the method that should be called, *not* run()!
            Implementation notes:
            run() should be called from the implementation of start(). So this interface is compatible
            to Python's Thread module.
        """
        pass

    def run(self):
        """ Runs the infinite event loop of the Connection.

            Blocks, until the event loop is terminated by calling terminate().
            This method intentionally fullfills the Thread interface, so a subclass of Connection that
            also inherits from Thread can be run in a separate thread without any modification to the event
            loop related code.
        """
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            task = asyncio.Task(loop.create_connection(self, self._server, self._port))
            loop.run_until_complete(task)
            loop.run_forever()

    def terminate(self):
        """ Gracefully terminate the Connection and the IO event loop.

        The client is notified that the connection is terminated and can no longer
        be used (by calling _signal_shutdown())..
        Any upcoming calls to send_message() will raise an exception.

        If the connection was not yet started or already terminated this method will have no effect and
        silently return.
        """
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.stop() #TODO really thread-safe?
            # TODO where to call close() on the loop?
            self.connection_shutdown()

    def send_message(self, message):
        """ Send a message to the server.

        Args:
            message (str): A valid IRC message. Only carriage return and line feed are appended automatically.
        """
        if asyncio.get_event_loop().is_running():
            self._logger.debug('Sending message: ' + message)
            message = message + '\r\n'
            self._transport.write(message.encode('utf-8'))
        else:
            raise NotConnectedError("TODO")

    def data_received(self, data):
        """ Implementation of inherited method (from :class:`asyncio.Protocol`). """
        try:
            data = data.decode('utf-8', 'log_and_replace').splitlines()
            for message in data:
                self._logger.debug('Incoming message: ' + message)
                self.message_dispatching(message)
        # Shutdown client if unhandled exception occurs, as EventLoop does not provide a handle_error() method so far.
        except Exception:
            self._logger.exception('Unhandled Exception while running an IRCClient:')
            self._logger.critical('Shutting down the client, due to an unhandled exception!')
            self.terminate()


    def _decoding_error_handler(self, error):
        """ Error handler that is used with the byte.decode() method.

        Does the same as the built-in 'replace' error handler, but logs an error message before.

        Args:
            error (UnicodeDecodeError): The error that was raised during decode.
        """
        self._logger.error('Invalid character encoding: ' + error.reason)
        self._logger.error('Replacing the malformed character.')
        return codecs.replace_errors(error)


    def __call__(self):
        """ Returns this Connection instance. Used as factory method for BaseEventLoop.create_connection(). """
        return self

    # --- Implemented methods from asyncio.Protocol ---

    def connection_made(self, transport):
        """ Implementation of inherited method (from :class:`asyncio.Protocol`). """
        self._transport = transport
        self.connection_initiation()

    def connect_lost(self, exc):
        """ Implementation of inherited method (from :class:`asyncio.Protocol`). """
        self._logger.info('Connection closed.')
        self.terminate()

    def eof_received(self):
        """ Implementation of inherited method (from :class:`asyncio.Protocol`). """
        self._logger.debug('Received EOF')
        self.terminate()


class StandaloneConnection(Connection):

    def __init__(self, client, server, port):
        super().__init__(client, server, port)

    # --- Implemented methods superclasses ---

    def connection_initiation(self):
        self._client._connection_established()

    def connection_shutdown(self):
        self._client._connection_shutdown()

    def message_dispatching(self, message):
        self._client._handle(message)

    def start(self):
        """ TODO doc: imitates behaviour of Thread """
        self.run()

