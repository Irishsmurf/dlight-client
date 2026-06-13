import asyncio
import unittest

from fake_server import FakeDLightServer

from dlightclient import (
    STATUS_SUCCESS,
    AsyncDLightClient,
    DLightTimeoutError,
)


class TestAsyncDLightClientRetry(unittest.IsolatedAsyncioTestCase):
    """Tests for the automatic retry logic in AsyncDLightClient.

    Runs against a real in-process TCP server (FakeDLightServer) so the
    assertions hold regardless of how the transport is implemented.
    """

    def setUp(self):
        self.device_id = "testdevice1"

    async def asyncSetUp(self):
        self.server = FakeDLightServer()
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.stop()

    async def test_retry_on_timeout_then_success(self):
        """A read timeout on the first attempt results in a retry and success."""
        client = AsyncDLightClient(default_timeout=0.2, max_retries=1, retry_backoff=0.01)
        self.server.hang()  # first attempt: no response -> timeout

        res = await client._async_send_tcp_command(
            self.server.host,
            {"commandType": "QUERY_DEVICE_STATES", "deviceId": self.device_id, "commands": []},
            port=self.server.port,
        )

        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertEqual(len(self.server.received_commands), 2)
        self.assertEqual(self.server.connection_count, 2)

    async def test_retry_exhausted_raises_error(self):
        """If all attempts time out, DLightTimeoutError is raised."""
        client = AsyncDLightClient(default_timeout=0.2, max_retries=2, retry_backoff=0.01)
        self.server.hang()
        self.server.hang()
        self.server.hang()

        with self.assertRaises(DLightTimeoutError):
            await client._async_send_tcp_command(
                self.server.host,
                {"commandType": "QUERY_DEVICE_STATES", "deviceId": self.device_id, "commands": []},
                port=self.server.port,
            )

        # 1 original attempt + 2 retries
        self.assertEqual(len(self.server.received_commands), 3)
        self.assertEqual(self.server.connection_count, 3)

    async def test_retry_on_connection_error(self):
        """A refused connection results in a retry once the device is back."""
        port = self.server.port
        await self.server.stop()  # nothing listening -> connection refused

        async def restart_server():
            await asyncio.sleep(0.05)
            await self.server.start(port=port)

        restart_task = asyncio.create_task(restart_server())
        try:
            client = AsyncDLightClient(default_timeout=1.0, max_retries=1, retry_backoff=0.3)
            res = await client._async_send_tcp_command(
                self.server.host,
                {"commandType": "QUERY_DEVICE_STATES", "deviceId": self.device_id, "commands": []},
                port=port,
            )
        finally:
            await restart_task

        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertEqual(len(self.server.received_commands), 1)

    async def test_retry_on_read_failure(self):
        """A connection reset (RST) during the read results in a retry."""
        client = AsyncDLightClient(default_timeout=1.0, max_retries=1, retry_backoff=0.01)
        self.server.reset_connection()  # first attempt: RST while client awaits header

        res = await client._async_send_tcp_command(
            self.server.host,
            {"commandType": "QUERY_DEVICE_STATES", "deviceId": self.device_id, "commands": []},
            port=self.server.port,
        )

        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertEqual(len(self.server.received_commands), 2)
        self.assertEqual(self.server.connection_count, 2)


if __name__ == "__main__":
    unittest.main()
