# dlightclient/_pool.py
"""Connection management for the dLight TCP client."""

import asyncio
import logging
import socket
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

    The pool never replays written bytes. A pooled connection is checked for
    liveness before it is handed out, so a peer that closed or reset while the
    connection sat idle is discarded and replaced without the caller noticing.
    A failure that survives that check reaches the caller, whose retry loop
    decides whether re-sending the command is safe; the pool cannot know that.
    See ``docs/adr/0001-no-byte-replay-in-the-connection-pool.md``.
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

    @staticmethod
    def _is_live(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
        """Pre-flight liveness check for a pooled connection.

        Three checks, cheapest first. The two stream flags catch a peer that
        departed while the event loop was running: ``is_closing`` for a reset,
        ``at_eof`` for a clean close. Both are *derived* from the loop having
        already processed the event, so neither sees a peer that departed while
        the loop was busy elsewhere — and a pooled connection is by definition
        one nothing has read from recently.

        The third check asks the kernel instead. ``MSG_PEEK`` on a duplicated,
        non-blocking descriptor reports ground truth without consuming bytes or
        disturbing the stream: empty means the peer sent FIN, ``OSError`` means
        the connection is unusable, and ``BlockingIOError`` means it is simply
        idle and healthy. Under TLS the peek sees ciphertext, so only the EOF
        signal is meaningful — which is the signal wanted.

        This is still not a guarantee: a peer that vanishes without the local
        TCP stack noticing, or between this check and the next write, surfaces
        as an error to the caller. That is the intended outcome now that the
        pool no longer re-sends commands on the caller's behalf.
        """
        if writer.is_closing() or reader.at_eof():
            return False

        sock = writer.get_extra_info("socket")
        if sock is None:
            return True

        try:
            probe = sock.dup()
        except Exception:  # pragma: no cover - platform/transport dependent
            return True  # cannot probe; trust the flags above

        try:
            probe.setblocking(False)
            return probe.recv(1, socket.MSG_PEEK) != b""
        except (BlockingIOError, InterruptedError):
            return True  # nothing pending: open and idle
        except OSError:
            return False  # reset, or otherwise unusable
        except Exception:  # pragma: no cover - defensive
            return True
        finally:
            probe.close()

    async def _checkout(
        self, key: str, host: str, port: int, ssl: _SSLArg, connect_timeout: float
    ) -> Tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        cached = self._connections.pop(key, None)
        if cached is not None:
            reader, writer, last_activity = cached
            if time.time() - last_activity <= self.idle_timeout and self._is_live(reader, writer):
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
