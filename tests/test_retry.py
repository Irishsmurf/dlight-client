import unittest
import asyncio
import json
import struct
from unittest.mock import patch, AsyncMock, call
from dlightclient import (
    AsyncDLightClient,
    DLightTimeoutError,
    STATUS_SUCCESS,
)

# Use the same module path as in other tests for consistency
CLIENT_MODULE_PATH = "dlightclient.client"


def create_mock_response(payload_dict: dict) -> bytes:
    """Encodes a dict into the dLight response format (header + payload)."""
    payload_bytes = json.dumps(payload_dict).encode("utf-8")
    header = struct.pack(">I", len(payload_bytes))
    return header + payload_bytes


class TestAsyncDLightClientRetry(unittest.IsolatedAsyncioTestCase):
    """Tests for the automatic retry logic in AsyncDLightClient."""

    def setUp(self):
        self.target_ip = "192.168.1.100"
        self.device_id = "testdevice1"
        self.resp_bytes = create_mock_response({"status": STATUS_SUCCESS})

    def _configure_mock_streams(self, mock_open_connection):
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_open_connection.return_value = (mock_reader, mock_writer)

        mock_reader.readexactly.side_effect = [self.resp_bytes[:4], self.resp_bytes[4:]]
        mock_writer.wait_closed = AsyncMock()
        mock_writer.is_closing.return_value = False
        mock_writer.get_extra_info.return_value = (self.target_ip, 3333)
        return mock_reader, mock_writer

    @patch(f"{CLIENT_MODULE_PATH}.asyncio.open_connection", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_on_timeout_then_success(self, mock_sleep, mock_open_connection):
        """Test that a timeout results in a retry and then success."""
        client = AsyncDLightClient(max_retries=1, retry_backoff=0.1)

        # First attempt fails with timeout, second succeeds
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)

        # side_effect for open_connection: first raises TimeoutError, second returns streams
        mock_open_connection.side_effect = [asyncio.TimeoutError, (mock_reader, mock_writer)]

        mock_reader.readexactly.side_effect = [self.resp_bytes[:4], self.resp_bytes[4:]]
        mock_writer.wait_closed = AsyncMock()
        mock_writer.is_closing.return_value = False
        mock_writer.get_extra_info.return_value = (self.target_ip, 3333)

        res = await client.query_device_state(self.target_ip, self.device_id)

        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertEqual(mock_open_connection.await_count, 2)
        mock_sleep.assert_awaited_once_with(0.1)

    @patch(f"{CLIENT_MODULE_PATH}.asyncio.open_connection", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_exhausted_raises_error(self, mock_sleep, mock_open_connection):
        """Test that if all retries fail, the error is raised."""
        client = AsyncDLightClient(max_retries=2, retry_backoff=0.1)

        # All 3 attempts (1 original + 2 retries) fail
        mock_open_connection.side_effect = [asyncio.TimeoutError, asyncio.TimeoutError, asyncio.TimeoutError]

        with self.assertRaises(DLightTimeoutError):
            await client.query_device_state(self.target_ip, self.device_id)

        self.assertEqual(mock_open_connection.await_count, 3)
        self.assertEqual(mock_sleep.await_count, 2)
        # Check backoff sequence: 0.1, 0.2
        mock_sleep.assert_has_awaits([call(0.1), call(0.2)])

    @patch(f"{CLIENT_MODULE_PATH}.asyncio.open_connection", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_on_connection_error(self, mock_sleep, mock_open_connection):
        """Test that a ConnectionRefusedError results in a retry."""
        client = AsyncDLightClient(max_retries=1, retry_backoff=0.1)

        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)

        mock_open_connection.side_effect = [ConnectionRefusedError("Refused"), (mock_reader, mock_writer)]

        mock_reader.readexactly.side_effect = [self.resp_bytes[:4], self.resp_bytes[4:]]
        mock_writer.wait_closed = AsyncMock()
        mock_writer.is_closing.return_value = False
        mock_writer.get_extra_info.return_value = (self.target_ip, 3333)

        res = await client.query_device_state(self.target_ip, self.device_id)

        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertEqual(mock_open_connection.await_count, 2)
        mock_sleep.assert_awaited_once_with(0.1)

    @patch(f"{CLIENT_MODULE_PATH}.asyncio.open_connection", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_retry_on_read_failure(self, mock_sleep, mock_open_connection):
        """Test that a failure during data reading results in a retry."""
        client = AsyncDLightClient(max_retries=1, retry_backoff=0.1)

        mock_reader1 = AsyncMock(spec=asyncio.StreamReader)
        mock_writer1 = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer1.wait_closed = AsyncMock()
        mock_writer1.is_closing.return_value = False
        mock_writer1.get_extra_info.return_value = (self.target_ip, 3333)

        # First read fails
        mock_reader1.readexactly.side_effect = OSError("Read failed")

        mock_reader2 = AsyncMock(spec=asyncio.StreamReader)
        mock_writer2 = AsyncMock(spec=asyncio.StreamWriter)
        mock_writer2.wait_closed = AsyncMock()
        mock_writer2.is_closing.return_value = False
        mock_writer2.get_extra_info.return_value = (self.target_ip, 3333)

        # Second read succeeds
        mock_reader2.readexactly.side_effect = [self.resp_bytes[:4], self.resp_bytes[4:]]

        mock_open_connection.side_effect = [(mock_reader1, mock_writer1), (mock_reader2, mock_writer2)]

        res = await client.query_device_state(self.target_ip, self.device_id)

        self.assertEqual(res["status"], STATUS_SUCCESS)
        self.assertEqual(mock_open_connection.await_count, 2)
        mock_sleep.assert_awaited_once_with(0.1)
        # Ensure first writer was closed
        mock_writer1.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
