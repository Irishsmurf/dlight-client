# tests/test_pool_regressions.py
"""Regression tests for connection-pool concurrency defects.

These encode two bugs in the persistent-connection feature:

1. Two concurrent first commands to the same device each create a private
   lock, so both open connections and one socket leaks.
2. A read timeout with no retries left does not evict the pooled connection,
   so the next command reads the previous command's late response.

Each is marked expectedFailure until the fix lands; they must then pass
un-marked.
"""

import asyncio
import unittest

from dlightclient import (
    AsyncDLightClient,
    DLightTimeoutError,
    STATUS_SUCCESS,
)
from fake_server import FakeDLightServer


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

    @unittest.expectedFailure
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


if __name__ == "__main__":
    unittest.main()
