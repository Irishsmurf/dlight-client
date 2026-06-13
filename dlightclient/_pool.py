# dlightclient/_pool.py
"""Connection management for the dLight TCP client."""

import asyncio
import logging
import ssl as ssl_module
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Optional, Tuple, Union

from .exceptions import DLightConnectionError, DLightTimeoutError

_LOGGER = logging.getLogger(__name__)

_SSLArg = Optional[Union[bool, ssl_module.SSLContext]]


class ConnectionPool:
    """Manages TCP connections to dLight devices.

    With ``persistent=False`` every connection is closed after use. With
    ``persistent=True`` connections are kept open and reused per
    (host, port, ssl) key. Access per key is serialized by a lock, and a
    connection whose use raised any exception is always evicted and closed —
    a stream that failed mid-exchange can never be reused.
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
            reader, writer = await self._checkout(key, host, port, ssl, connect_timeout)
            try:
                yield reader, writer
            except BaseException:
                await self._close_writer(writer)
                raise
            else:
                if self.persistent and not writer.is_closing():
                    self._connections[key] = (reader, writer, time.time())
                else:
                    await self._close_writer(writer)

    async def _checkout(
        self, key: str, host: str, port: int, ssl: _SSLArg, connect_timeout: float
    ) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        cached = self._connections.pop(key, None)
        if cached is not None:
            reader, writer, last_activity = cached
            if not writer.is_closing() and time.time() - last_activity <= self.idle_timeout:
                _LOGGER.debug(f"Reusing persistent connection for {key}")
                return reader, writer
            _LOGGER.debug(f"Cached connection for {key} is stale, discarding.")
            await self._close_writer(writer)

        _LOGGER.debug(f"Opening new connection to {host}:{port}")
        try:
            connect_future = asyncio.open_connection(host, port, ssl=ssl)
            reader, writer = await asyncio.wait_for(connect_future, timeout=connect_timeout)
            _LOGGER.debug(f"Connection established to {writer.get_extra_info('peername')}")
            return reader, writer
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
