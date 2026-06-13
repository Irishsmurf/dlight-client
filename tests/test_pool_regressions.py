# tests/test_pool_regressions.py
"""Regression tests for connection-pool concurrency defects.

These encode two bugs in the persistent-connection feature:

1. Two concurrent first commands to the same device each create a private
   lock, so both open connections and one socket leaks.
2. A read timeout with no retries left does not evict the pooled connection,
   so the next command reads the previous command's late response.

Both were marked expectedFailure until the ConnectionPool extraction landed;
they now guard against reintroducing the bugs.
"""

import asyncio
import unittest

from fake_server import FakeDLightServer

from dlightclient import (
    STATUS_SUCCESS,
    AsyncDLightClient,
    DLightTimeoutError,
)


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

    async def test_transparent_reconnect_on_stale_connection(self):
        """A persistent connection that goes stale triggers a transparent reconnect on next command."""
        client = AsyncDLightClient(persistent=True, default_timeout=1.0, max_retries=0)
        try:
            # First send: opens a connection and caches it.
            res1 = await self._send(client, 1)
            self.assertEqual(res1["status"], STATUS_SUCCESS)
            self.assertEqual(self.server.connection_count, 1)

            # Server will reset the next connection attempt/command
            self.server.reset_connection()

            # Second send: uses cached connection, encounters reset, and transparently reconnects.
            # It should succeed because it retries on the new connection.
            res2 = await self._send(client, 2)
            self.assertEqual(res2["status"], STATUS_SUCCESS)

            # Connection count should be 2 because it had to open a new connection for the retry
            self.assertEqual(self.server.connection_count, 2)
        finally:
            await client.close()

    async def test_no_transparent_reconnect_on_fresh_connection_failure(self):
        """A failure on a brand-new connection is NOT retried (avoids masking real errors)."""
        client = AsyncDLightClient(persistent=True, default_timeout=1.0, max_retries=0)
        try:
            # Server will reset the connection immediately on first command
            self.server.reset_connection()

            # Since it's a new connection, it should fail immediately without retrying.
            from dlightclient.exceptions import DLightConnectionError
            with self.assertRaises(DLightConnectionError):
                await self._send(client, 1)

            # Connection count should be 1 (first failed connection) and no successful retry occurred.
            self.assertEqual(self.server.connection_count, 1)
        finally:
            await client.close()


if __name__ == "__main__":
    unittest.main()
