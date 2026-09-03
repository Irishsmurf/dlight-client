# tests/test_pool_regressions.py
"""Permanent invariants of the connection pool.

Two kinds of test live here.

**Concurrency regressions.** These encode two bugs in the persistent-connection
feature:

1. Two concurrent first commands to the same device each create a private
   lock, so both open connections and one socket leaks.
2. A read timeout with no retries left does not evict the pooled connection,
   so the next command reads the previous command's late response.

Both were marked expectedFailure until the ConnectionPool extraction landed;
they now guard against reintroducing the bugs.

**Delivery contract.** The pool never replays written bytes (ADR 0001). A
stale connection is caught by a pre-flight liveness check where possible, and
otherwise surfaces to the caller's retry loop -- it is never recovered by
re-sending a command the device may already have acted on. These tests state
that contract, and the pre-flight check has one of its own because it replaces
a safety feature that was deliberately removed.
"""

import asyncio
import socket
import struct
import threading
import time
import unittest

from fake_server import FakeDLightServer, frame

from dlightclient import (
    STATUS_SUCCESS,
    AsyncDLightClient,
    DLightConnectionError,
    DLightTimeoutError,
)
from dlightclient._pool import ConnectionPool


class TestConnectionPoolRegressions(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.device_id = "testdevice1"

    async def asyncSetUp(self):
        self.server = FakeDLightServer()
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.stop()

    def _command(self, n):
        return {
            "commandId": f"cmd-regress-{n}",
            "deviceId": self.device_id,
            "commandType": "QUERY_DEVICE_STATES",
            "commands": [],
        }

    async def _send(self, client, n):
        return await client._async_send_tcp_command(self.server.host, self._command(n), port=self.server.port)

    async def test_concurrent_first_commands_share_one_connection(self):
        """Concurrent first commands to one device must share one pooled connection."""
        client = AsyncDLightClient(persistent=True, default_timeout=1.0)
        try:
            results = await asyncio.gather(self._send(client, 1), self._send(client, 2))
        finally:
            await client.close()

        for result in results:
            self.assertEqual(result["status"], STATUS_SUCCESS)
        self.assertEqual(self.server.connection_count, 1)

    async def test_timeout_evicts_pooled_connection(self):
        """After a read timeout the pooled connection must not be reused.

        The first command's reply arrives after the client timed out. If the
        poisoned connection stays pooled, the second command reads the stale
        marker-1 reply instead of its own marker-2 reply.
        """
        client = AsyncDLightClient(persistent=True, default_timeout=0.5, max_retries=0)
        self.server.respond({"status": STATUS_SUCCESS, "marker": 1}, delay=0.8)  # arrives too late
        self.server.respond({"status": STATUS_SUCCESS, "marker": 2})
        try:
            with self.assertRaises(DLightTimeoutError):
                await self._send(client, 1)
            result = await self._send(client, 2)
        finally:
            await client.close()

        self.assertEqual(result.get("marker"), 2)
        self.assertEqual(self.server.connection_count, 2)

    async def test_stale_connection_surfaces_error_without_retries(self):
        """A reset on a reused connection is not recovered when max_retries=0.

        The pool never replays written bytes, so a failure the pre-flight check
        could not anticipate reaches the caller instead of being silently
        re-sent. Restoring the old behaviour is the caller's choice, made by
        setting max_retries (see the companion test below).
        """
        client = AsyncDLightClient(persistent=True, default_timeout=1.0, max_retries=0)
        try:
            res1 = await self._send(client, 1)
            self.assertEqual(res1["status"], STATUS_SUCCESS)
            self.assertEqual(self.server.connection_count, 1)

            # The server resets while handling the next command, after the
            # pre-flight check has already passed the connection as live.
            self.server.reset_connection()

            with self.assertRaises(DLightConnectionError):
                await self._send(client, 2)
        finally:
            await client.close()

    async def test_stale_connection_recovers_with_one_retry(self):
        """max_retries=1 restores what transparent reconnect used to do.

        The recovery is identical in effect, but the caller opted into it and
        the retry is bounded by exactly one counter.
        """
        client = AsyncDLightClient(persistent=True, default_timeout=1.0, max_retries=1, retry_backoff=0.0)
        try:
            res1 = await self._send(client, 1)
            self.assertEqual(res1["status"], STATUS_SUCCESS)

            self.server.reset_connection()

            res2 = await self._send(client, 2)
            self.assertEqual(res2["status"], STATUS_SUCCESS)
            self.assertEqual(self.server.connection_count, 2)
        finally:
            await client.close()

    async def test_fresh_connection_failure_surfaces(self):
        """A failure on a brand-new connection is never retried by the pool."""
        client = AsyncDLightClient(persistent=True, default_timeout=1.0, max_retries=0)
        try:
            self.server.reset_connection()

            with self.assertRaises(DLightConnectionError):
                await self._send(client, 1)

            self.assertEqual(self.server.connection_count, 1)
        finally:
            await client.close()

    async def test_peer_closed_pooled_connection_is_discarded_before_reuse(self):
        """The pre-flight check catches a peer that closed a pooled connection.

        This replaces transparent reconnect for its actual motivating case, and
        it is a characterization test: it passed before ADR 0001 too, because
        byte replay produced the same outcome by a worse route. Its job is to
        fail if the pre-flight check is ever weakened or "simplified" away,
        now that there is no replay to fall back on -- with max_retries=0 the
        pre-flight check is the only thing making this succeed.

        Note the server cannot observe a double send here: bytes written to the
        connection it already closed are never read by anyone, so asserting on
        received_commands would be vacuous. The real signal is that recovery
        happens at all without a retry budget.
        """
        client = AsyncDLightClient(persistent=True, default_timeout=1.0, max_retries=0)
        try:
            # Reply normally, then close -- the connection is pooled but dead.
            self.server.respond_raw(frame({"status": STATUS_SUCCESS}), close=True)
            res1 = await self._send(client, 1)
            self.assertEqual(res1["status"], STATUS_SUCCESS)

            # Let asyncio observe the peer's EOF before the next checkout.
            await asyncio.sleep(0.05)

            res2 = await self._send(client, 2)
            self.assertEqual(res2["status"], STATUS_SUCCESS)
        finally:
            await client.close()

        self.assertEqual(self.server.connection_count, 2)


class TestPreFlightLiveness(unittest.IsolatedAsyncioTestCase):
    """The pre-flight check must not rely on the event loop having noticed.

    ``is_closing`` and ``at_eof`` are derived from asyncio having already
    processed the peer's departure. A pooled connection is one nothing has read
    from recently, so that is exactly the case where the flags can be stale.
    These tests drive a peer from a separate thread and block the loop, so both
    flags are provably blind and only the MSG_PEEK probe can be answering.
    """

    async def _departed_peer(self, reset: bool):
        """Opens a connection whose peer departs while the event loop is blocked."""
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        port = listener.getsockname()[1]

        def serve():
            conn, _ = listener.accept()
            conn.recv(100)
            if reset:
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
            conn.close()

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()

        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"go")
        await writer.drain()
        # Block the loop so it cannot observe the departure. The peer is in
        # another thread, so it closes regardless.
        time.sleep(0.3)
        thread.join(timeout=1.0)
        listener.close()
        return reader, writer

    async def test_peek_detects_clean_close_the_flags_have_not_seen(self):
        reader, writer = await self._departed_peer(reset=False)
        try:
            self.assertFalse(writer.is_closing(), "precondition: loop has not seen the close")
            self.assertFalse(reader.at_eof(), "precondition: loop has not seen the close")
            self.assertFalse(ConnectionPool._is_live(reader, writer))
        finally:
            writer.close()

    async def test_peek_detects_reset_the_flags_have_not_seen(self):
        reader, writer = await self._departed_peer(reset=True)
        try:
            self.assertFalse(writer.is_closing(), "precondition: loop has not seen the reset")
            self.assertFalse(reader.at_eof(), "precondition: loop has not seen the reset")
            self.assertFalse(ConnectionPool._is_live(reader, writer))
        finally:
            writer.close()

    async def test_healthy_idle_connection_is_live(self):
        """An open connection with no pending data must not be discarded."""
        server = FakeDLightServer()
        await server.start()
        try:
            reader, writer = await asyncio.open_connection(server.host, server.port)
            try:
                self.assertTrue(ConnectionPool._is_live(reader, writer))
            finally:
                writer.close()
        finally:
            await server.stop()


if __name__ == "__main__":
    unittest.main()
