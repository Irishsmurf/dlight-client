# tests/fake_server.py
"""An in-process TCP server speaking the real dLight wire protocol.

Tests use this instead of mocking asyncio streams so they assert on
observable behavior (commands received, responses returned, connection
counts) rather than on the client's internal read/write call sequence.
"""

import asyncio
import json
import socket
import struct
from collections import deque
from typing import Any, Dict, List, Optional


def frame(payload_dict: Dict[str, Any]) -> bytes:
    """Encodes a dict into the dLight response format (4-byte BE length + JSON)."""
    payload = json.dumps(payload_dict).encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


class FakeDLightServer:
    """A scriptable fake dLight device.

    Behaviors are queued with the helper methods below and consumed one per
    received command (FIFO, shared across connections). With an empty queue
    the server replies with a framed ``{"status": "SUCCESS"}``.

    Usage::

        async with FakeDLightServer() as server:
            server.respond({"status": "SUCCESS", "states": {...}})
            await client.query_device_state(server.host, ..., port=server.port)
    """

    host = "127.0.0.1"

    def __init__(self):
        self.port: Optional[int] = None
        self.received_commands: List[Dict[str, Any]] = []
        self.connection_count = 0
        self.closed_connections = 0
        self._behaviors: deque = deque()
        self._server: Optional[asyncio.AbstractServer] = None
        self._tasks: set = set()

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()

    async def start(self, port: int = 0):
        """Starts listening. Pass a previous ``self.port`` to restart on it."""
        self._server = await asyncio.start_server(self._handle, self.host, port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        if self._server is not None:
            self._server.close()
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._server is not None:
            try:
                await self._server.wait_closed()
            except asyncio.CancelledError:
                pass
            self._server = None

    # --- Scripted behaviors (one consumed per received command) ---

    def respond(self, payload: Dict[str, Any], delay: float = 0.0):
        """Reply with a properly framed JSON payload, after an optional delay."""
        self._behaviors.append(("respond", payload, delay))

    def respond_raw(self, data: bytes, close: bool = False):
        """Reply with arbitrary bytes; optionally close the connection after."""
        self._behaviors.append(("raw_close" if close else "raw", data, 0.0))

    def hang(self):
        """Never reply (until the server is stopped); triggers client timeouts."""
        self._behaviors.append(("hang", None, 0.0))

    def echo(self):
        """Reply with the received command framed as the response payload."""
        self._behaviors.append(("echo", None, 0.0))

    def reset_connection(self):
        """Abort the connection with a TCP RST (client sees a network OSError)."""
        self._behaviors.append(("reset", None, 0.0))

    # --- Internals ---

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.connection_count += 1
        task = asyncio.current_task()
        self._tasks.add(task)
        buf = bytearray()
        try:
            while True:
                command = await self._read_command(reader, buf)
                if command is None:  # client closed the connection
                    break
                self.received_commands.append(command)

                if self._behaviors:
                    kind, arg, delay = self._behaviors.popleft()
                else:
                    kind, arg, delay = "respond", {"status": "SUCCESS"}, 0.0
                if delay:
                    await asyncio.sleep(delay)

                if kind == "respond":
                    writer.write(frame(arg))
                    await writer.drain()
                elif kind == "echo":
                    writer.write(frame(command))
                    await writer.drain()
                elif kind == "raw":
                    writer.write(arg)
                    await writer.drain()
                elif kind == "raw_close":
                    writer.write(arg)
                    await writer.drain()
                    break
                elif kind == "reset":
                    sock = writer.get_extra_info("socket")
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                    break
                elif kind == "hang":
                    await asyncio.Event().wait()  # parked until cancelled by stop()
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self._tasks.discard(task)
            self.closed_connections += 1
            try:
                writer.close()
            except Exception:
                pass

    @staticmethod
    async def _read_command(reader: asyncio.StreamReader, buf: bytearray) -> Optional[Dict[str, Any]]:
        """Reads one JSON command (the client sends bare JSON, no length prefix)."""
        decoder = json.JSONDecoder()
        while True:
            if buf:
                try:
                    text = bytes(buf).decode("utf-8")
                except UnicodeDecodeError:
                    text = None  # partial multibyte sequence; need more data
                if text is not None:
                    try:
                        obj, end = decoder.raw_decode(text)
                        del buf[: len(text[:end].encode("utf-8"))]
                        return obj
                    except json.JSONDecodeError:
                        pass  # incomplete JSON; need more data
            chunk = await reader.read(4096)
            if not chunk:
                return None
            buf.extend(chunk)
