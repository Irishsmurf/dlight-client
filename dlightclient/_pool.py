# dlightclient/_pool.py
"""Connection management for the dLight TCP client."""

import asyncio
import logging
import ssl as ssl_module
import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional, Tuple, Union, cast

from .exceptions import DLightConnectionError, DLightTimeoutError

_LOGGER = logging.getLogger(__name__)

_SSLArg = Optional[Union[bool, ssl_module.SSLContext]]


class ReconnectingState:
    """Shared state for transparent reconnection on stale connections."""

    def __init__(
        self,
        pool: "ConnectionPool",
        host: str,
        port: int,
        ssl: _SSLArg,
        connect_timeout: float,
        is_reused: bool,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        self.pool = pool
        self.host = host
        self.port = port
        self.ssl = ssl
        self.connect_timeout = connect_timeout
        self.is_reused = is_reused
        self.reader = reader
        self.writer = writer
        self.write_buffer = bytearray()
        self.retried = False

    async def reconnect_and_retry(self) -> bool:
        """Attempts to transparently reconnect and replay buffered writes.

        Returns:
            True if reconnect and replay succeeded, False if already retried
            or if the connection was not reused.
        """
        if self.retried or not self.is_reused:
            return False

        self.retried = True
        _LOGGER.debug(
            f"Connection error on reused connection to {self.host}:{self.port}. "
            "Attempting transparent reconnect."
        )

        # 1. Discard the stale connection
        await self.pool._close_writer(self.writer)

        # 2. Open a new connection to the same host/port
        try:
            connect_future = asyncio.open_connection(self.host, self.port, ssl=self.ssl)
            self.reader, self.writer = await asyncio.wait_for(
                connect_future, timeout=self.connect_timeout
            )
            _LOGGER.debug(
                f"Transparent reconnect established to {self.writer.get_extra_info('peername')}"
            )
        except asyncio.TimeoutError as e:
            raise DLightTimeoutError(f"Timeout connecting to {self.host}:{self.port}") from e
        except ConnectionRefusedError as e:
            raise DLightConnectionError(f"Connection refused by {self.host}:{self.port}") from e
        except OSError as e:
            raise DLightConnectionError(f"Network error connecting to {self.host}:{self.port}: {e}") from e

        # 3. Retry the failed command once on the new connection
        if self.write_buffer:
            try:
                self.writer.write(self.write_buffer)
                await asyncio.wait_for(self.writer.drain(), timeout=self.connect_timeout)
            except asyncio.TimeoutError as e:
                raise DLightTimeoutError(f"Timeout during transparent reconnect write/drain: {e}") from e
            except Exception as e:
                _LOGGER.error(f"Transparent reconnect failed during write/drain: {e}")
                raise DLightConnectionError(
                    f"Network error during transparent reconnect write/drain: {e}"
                ) from e

        return True


class ReconnectingStreamWriter:
    """Proxy StreamWriter that handles transparent reconnection on write failure."""

    def __init__(self, state: ReconnectingState):
        self._state = state

    def write(self, data: bytes) -> None:
        self._state.write_buffer.extend(data)
        self._state.writer.write(data)

    def writelines(self, data: Any) -> None:
        for chunk in data:
            self.write(chunk)

    def write_eof(self) -> None:
        self._state.writer.write_eof()

    def can_write_eof(self) -> bool:
        return self._state.writer.can_write_eof()

    @property
    def transport(self) -> Any:
        return self._state.writer.transport

    async def drain(self) -> None:
        try:
            await self._state.writer.drain()
        except OSError as e:
            if not isinstance(e, asyncio.CancelledError):
                if await self._state.reconnect_and_retry():
                    return
            raise

    def is_closing(self) -> bool:
        return self._state.writer.is_closing()

    def close(self) -> None:
        self._state.writer.close()

    async def wait_closed(self) -> None:
        await self._state.writer.wait_closed()

    def get_extra_info(self, name: str, default: Any = None) -> Any:
        return self._state.writer.get_extra_info(name, default)


class ReconnectingStreamReader:
    """Proxy StreamReader that handles transparent reconnection on read failure."""

    def __init__(self, state: ReconnectingState):
        self._state = state

    async def read(self, n: int = -1) -> bytes:
        try:
            return await self._state.reader.read(n)
        except (OSError, asyncio.IncompleteReadError) as e:
            if not isinstance(e, asyncio.CancelledError):
                if await self._state.reconnect_and_retry():
                    return await self._state.reader.read(n)
            raise

    async def readline(self) -> bytes:
        try:
            return await self._state.reader.readline()
        except (OSError, asyncio.IncompleteReadError) as e:
            if not isinstance(e, asyncio.CancelledError):
                if await self._state.reconnect_and_retry():
                    return await self._state.reader.readline()
            raise

    async def readexactly(self, n: int) -> bytes:
        try:
            return await self._state.reader.readexactly(n)
        except (OSError, asyncio.IncompleteReadError) as e:
            if not isinstance(e, asyncio.CancelledError):
                if await self._state.reconnect_and_retry():
                    return await self._state.reader.readexactly(n)
            raise

    async def readuntil(self, separator: bytes = b"\n") -> bytes:
        try:
            return await self._state.reader.readuntil(separator)
        except (OSError, asyncio.IncompleteReadError) as e:
            if not isinstance(e, asyncio.CancelledError):
                if await self._state.reconnect_and_retry():
                    return await self._state.reader.readuntil(separator)
            raise

    def at_eof(self) -> bool:
        return self._state.reader.at_eof()


class ConnectionPool:
    """Manages TCP connections to dLight devices.

    With ``persistent=False`` every connection is closed after use. With
    ``persistent=True`` connections are kept open and reused per
    (host, port, ssl) key. Access per key is serialized by a lock, and a
    connection whose use raised any exception is always evicted and closed —
    a stream that failed mid-exchange can never be reused.

    For persistent connections, if a connection goes stale (e.g. peer resets
    or closes the connection) during use, the pool transparently discards it,
    establishes a new connection, and retries the failed read/write operation
    once before raising an error.
    """

    def __init__(self, persistent: bool, idle_timeout: float):
        self.persistent = persistent
        self.idle_timeout = idle_timeout
        # Key -> (reader, writer, last_activity_time). Entries are checked
        # out (removed) while in use; per-key locks serialize checkout.
        self._connections: Dict[str, Tuple[asyncio.StreamReader, asyncio.StreamWriter, float]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    @staticmethod
    def _key(host: str, port: int, ssl: _SSLArg) -> str:
        # Distinct SSLContext instances must not share connections.
        ssl_identifier: Union[bool, ssl_module.SSLContext, str, None] = ssl
        if ssl and not isinstance(ssl, bool):
            ssl_identifier = f"ctx_{id(ssl)}"
        return f"{host}:{port}:{ssl_identifier}"

    @asynccontextmanager
    async def connection(
        self, host: str, port: int, ssl: _SSLArg, connect_timeout: float
    ) -> AsyncIterator[Tuple[asyncio.StreamReader, asyncio.StreamWriter]]:
        """Yields a (reader, writer) pair for one request/response exchange."""
        key = self._key(host, port, ssl)
        # dict.setdefault runs without awaiting, so all concurrent callers
        # observe the same lock for a given key.
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            reader, writer, is_reused = await self._checkout(key, host, port, ssl, connect_timeout)
            state = ReconnectingState(self, host, port, ssl, connect_timeout, is_reused, reader, writer)
            wrapped_reader = cast(asyncio.StreamReader, ReconnectingStreamReader(state))
            wrapped_writer = cast(asyncio.StreamWriter, ReconnectingStreamWriter(state))
            try:
                yield wrapped_reader, wrapped_writer
            except BaseException:
                await self._close_writer(state.writer)
                raise
            else:
                if self.persistent and not state.writer.is_closing():
                    self._connections[key] = (state.reader, state.writer, time.time())
                else:
                    await self._close_writer(state.writer)

    async def _checkout(
        self, key: str, host: str, port: int, ssl: _SSLArg, connect_timeout: float
    ) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter, bool]:
        cached = self._connections.pop(key, None)
        if cached is not None:
            reader, writer, last_activity = cached
            if not writer.is_closing() and time.time() - last_activity <= self.idle_timeout:
                _LOGGER.debug(f"Reusing persistent connection for {key}")
                return reader, writer, True
            _LOGGER.debug(f"Cached connection for {key} is stale, discarding.")
            await self._close_writer(writer)

        _LOGGER.debug(f"Opening new connection to {host}:{port}")
        try:
            connect_future = asyncio.open_connection(host, port, ssl=ssl)
            reader, writer = await asyncio.wait_for(connect_future, timeout=connect_timeout)
            _LOGGER.debug(f"Connection established to {writer.get_extra_info('peername')}")
            return reader, writer, False
        except asyncio.TimeoutError:
            raise DLightTimeoutError(f"Timeout connecting to {host}:{port}") from None
        except ConnectionRefusedError as e:
            raise DLightConnectionError(f"Connection refused by {host}:{port}") from e
        except OSError as e:
            raise DLightConnectionError(f"Network error connecting to {host}:{port}: {e}") from e

    @staticmethod
    async def _close_writer(writer: asyncio.StreamWriter) -> None:
        if writer.is_closing():
            return
        try:
            writer.close()
            await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
        except Exception as e:
            _LOGGER.debug(f"Error closing connection: {e}")

    async def close_all(self) -> None:
        """Closes all pooled connections."""
        _LOGGER.debug(f"Closing {len(self._connections)} persistent connections")
        while self._connections:
            _, (_, writer, _) = self._connections.popitem()
            await self._close_writer(writer)
