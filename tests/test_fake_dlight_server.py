# tests/test_fake_dlight_server.py
"""Contract tests for the standalone fake device in tools/.

That tool is not imported by the library, so nothing else would notice if it
drifted from the protocol it exists to imitate -- which is exactly what had
happened: it restated the ports and the probe payload as its own literals.
These tests hold it to the library's definitions.
"""

import asyncio
import pathlib
import sys
import unittest

from dlightclient import STATUS_SUCCESS, constants
from dlightclient._frame import read_response

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "tools"))

import fake_dlight_server  # noqa: E402  (needs the sys.path entry above)


class TestFakeDeviceSpeaksTheLibrarysWireFormat(unittest.IsolatedAsyncioTestCase):
    def _device(self) -> "fake_dlight_server.FakeDLight":
        return fake_dlight_server.FakeDLight("fake-1", "dLight-Fake", "1.0.0-fake", "rev1")

    async def _parse(self, response: dict) -> dict:
        """Encodes as the fake does, then reads it back as the client does."""
        reader = asyncio.StreamReader()
        reader.feed_data(fake_dlight_server.encode_response(response))
        reader.feed_eof()
        return await read_response(reader, 1.0, "fake device")

    async def test_query_state_response_parses(self):
        device = self._device()
        device.state["brightness"] = 42
        response = device.handle_command(
            {"commandId": "c1", "deviceId": "fake-1", "commandType": "QUERY_DEVICE_STATES", "commands": []}
        )
        parsed = await self._parse(response)
        self.assertEqual(parsed["status"], STATUS_SUCCESS)
        self.assertEqual(parsed["states"]["brightness"], 42)

    async def test_query_info_response_parses(self):
        response = self._device().handle_command(
            {"commandId": "c2", "deviceId": "fake-1", "commandType": "QUERY_DEVICE_INFO", "commands": []}
        )
        parsed = await self._parse(response)
        self.assertEqual(parsed["deviceModel"], "dLight-Fake")

    async def test_execute_response_parses(self):
        response = self._device().handle_command(
            {"commandId": "c3", "deviceId": "fake-1", "commandType": "EXECUTE", "commands": [{"on": True}]}
        )
        self.assertEqual((await self._parse(response))["status"], STATUS_SUCCESS)

    def test_does_not_echo_command_id(self):
        """A real device does not echo commandId reliably enough to correlate.

        Echoing it here would model a more capable device than exists, and let
        anything depending on correlation pass against the fake and fail
        against hardware. See ADR 0001.
        """
        response = self._device().handle_command(
            {"commandId": "c4", "deviceId": "fake-1", "commandType": "EXECUTE", "commands": [{"on": True}]}
        )
        self.assertNotIn("commandId", response)


class TestFakeDeviceUsesLibraryConstants(unittest.TestCase):
    def test_ports_and_probe_come_from_the_library(self):
        self.assertEqual(fake_dlight_server.DEFAULT_TCP_PORT, constants.DEFAULT_TCP_PORT)
        self.assertEqual(fake_dlight_server.DISCOVERY_PORT, constants.DEFAULT_UDP_DISCOVERY_PORT)
        self.assertEqual(fake_dlight_server.DISCOVERY_RESPONSE_PORT, constants.DEFAULT_UDP_RESPONSE_PORT)

    def test_probe_payload_matches_the_one_the_client_broadcasts(self):
        import binascii

        self.assertEqual(
            fake_dlight_server.DISCOVERY_PROBE,
            binascii.unhexlify(constants.UDP_DISCOVERY_PAYLOAD_HEX),
        )


if __name__ == "__main__":
    unittest.main()
