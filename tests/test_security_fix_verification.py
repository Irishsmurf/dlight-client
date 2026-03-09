import unittest
import asyncio
import json
import struct
from unittest.mock import patch, AsyncMock, MagicMock
from dlightclient import AsyncDLightClient, DLightCommandError, STATUS_SUCCESS


class TestSecurityFixes(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = AsyncDLightClient()
        self.target_ip = "192.168.4.1"
        self.device_id = "test-device"
        self.ssid = "SecretSSID"
        self.password = "SecretPassword"

    def _setup_mock_streams(self, mock_open):
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_open.return_value = (mock_reader, mock_writer)

        # Mock non-async methods
        mock_writer.write = MagicMock()
        mock_writer.get_extra_info.return_value = (self.target_ip, 3333)
        mock_writer.is_closing.return_value = False

        # Mock async methods
        mock_writer.drain = AsyncMock()
        mock_writer.wait_closed = AsyncMock()

        return mock_reader, mock_writer

    @patch("dlightclient.client._LOGGER")
    @patch("asyncio.open_connection", new_callable=AsyncMock)
    async def test_ssid_NOT_logged_at_info_level(self, mock_open, mock_logger):
        mock_reader, _ = self._setup_mock_streams(mock_open)

        # Prepare a valid response
        resp_payload = {"status": STATUS_SUCCESS, "commandId": "123"}
        resp_bytes = json.dumps(resp_payload).encode("utf-8")
        header = struct.pack(">I", len(resp_bytes))
        mock_reader.readexactly.side_effect = [header, resp_bytes]

        await self.client.connect_to_wifi(self.device_id, self.ssid, self.password)

        # Check if SSID was NOT logged at INFO level
        info_messages = [call.args[0] for call in mock_logger.info.call_args_list]
        ssid_leaked = any(self.ssid in msg for msg in info_messages)
        self.assertFalse(ssid_leaked, "SSID should NOT be leaked in INFO logs")

    @patch("dlightclient.client._LOGGER")
    @patch("asyncio.open_connection", new_callable=AsyncMock)
    async def test_ssid_masked_in_debug_log(self, mock_open, mock_logger):
        mock_reader, _ = self._setup_mock_streams(mock_open)

        resp_payload = {"status": STATUS_SUCCESS, "commandId": "123"}
        resp_bytes = json.dumps(resp_payload).encode("utf-8")
        header = struct.pack(">I", len(resp_bytes))
        mock_reader.readexactly.side_effect = [header, resp_bytes]

        await self.client.connect_to_wifi(self.device_id, self.ssid, self.password)

        # Check if SSID was masked in DEBUG logs
        debug_messages = [call.args[0] for call in mock_logger.debug.call_args_list]
        ssid_unmasked = any(f'"ssid": "{self.ssid}"' in msg for msg in debug_messages)
        self.assertFalse(ssid_unmasked, "SSID should be masked in DEBUG logs")

        ssid_masked = any('"ssid": "********"' in msg for msg in debug_messages)
        self.assertTrue(ssid_masked, "SSID should be masked with ******** in DEBUG logs")

    @patch("json.dumps")
    async def test_password_NOT_leaked_in_serialization_error(self, mock_json_dumps):
        # Force a TypeError during json.dumps for the real command
        # log_command uses json.dumps too in my test but in code it uses it for DEBUG logging

        def side_effect(obj, *args, **kwargs):
            if obj.get("password") == self.password:
                raise TypeError("Serialization failed")
            return json.dumps(obj, *args, **kwargs)

        mock_json_dumps.side_effect = side_effect

        command = {
            "commandType": "SSID_CONNECT",
            "ssid": self.ssid,
            "password": self.password
        }

        with self.assertRaises(DLightCommandError) as cm:
            await self.client._async_send_tcp_command(self.target_ip, command)

        error_msg = str(cm.exception)
        self.assertNotIn(self.password, error_msg, "Password should NOT be leaked in DLightCommandError message")
        self.assertIn("********", error_msg, "Password should be masked in DLightCommandError message")


if __name__ == "__main__":
    unittest.main()
