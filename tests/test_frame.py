# tests/test_frame.py
"""Unit tests for the dLight wire-format codec (dlightclient/_frame.py)."""

import asyncio
import json
import struct
import unittest

from dlightclient import (
    MAX_PAYLOAD_SIZE,
    STATUS_SUCCESS,
    DLightCommandError,
    DLightResponseError,
    DLightTimeoutError,
)
from dlightclient._frame import encode_command, mask_command, read_response


def frame(payload_dict: dict) -> bytes:
    payload = json.dumps(payload_dict).encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


class TestEncodeCommand(unittest.TestCase):
    def test_round_trip(self):
        command = {"commandId": "c1", "commandType": "EXECUTE", "commands": [{"on": True}]}
        self.assertEqual(json.loads(encode_command(command).decode("utf-8")), command)

    def test_unserializable_raises_command_error_with_masked_credentials(self):
        command = {"password": "hunter2", "bad": object()}
        with self.assertRaises(DLightCommandError) as ctx:
            encode_command(command)
        self.assertNotIn("hunter2", str(ctx.exception))


class TestMaskCommand(unittest.TestCase):
    def test_masks_credentials_without_mutating_original(self):
        command = {"ssid": "HomeWifi", "password": "hunter2", "deviceId": "d1"}
        masked = mask_command(command)
        self.assertEqual(masked["ssid"], "********")
        self.assertEqual(masked["password"], "********")
        self.assertEqual(masked["deviceId"], "d1")
        self.assertEqual(command["password"], "hunter2")

    def test_returns_command_unchanged_when_nothing_sensitive(self):
        command = {"deviceId": "d1"}
        self.assertIs(mask_command(command), command)


class TestReadResponse(unittest.IsolatedAsyncioTestCase):
    def _reader_with(self, data: bytes, eof: bool = True) -> asyncio.StreamReader:
        reader = asyncio.StreamReader()
        reader.feed_data(data)
        if eof:
            reader.feed_eof()
        return reader

    async def test_success_payload(self):
        payload = {"status": STATUS_SUCCESS, "states": {"on": True}}
        reader = self._reader_with(frame(payload))
        self.assertEqual(await read_response(reader, 1.0, "test"), payload)

    async def test_zero_payload_synthesizes_success(self):
        reader = self._reader_with(struct.pack(">I", 0))
        self.assertEqual(await read_response(reader, 1.0, "test"), {"status": STATUS_SUCCESS})

    async def test_oversized_payload_rejected(self):
        reader = self._reader_with(struct.pack(">I", MAX_PAYLOAD_SIZE + 1))
        with self.assertRaisesRegex(DLightResponseError, "exceeds maximum limit"):
            await read_response(reader, 1.0, "test")

    async def test_invalid_json_rejected(self):
        bad = b'{"status": "SUCCESS", "on": tru'
        reader = self._reader_with(struct.pack(">I", len(bad)) + bad)
        with self.assertRaisesRegex(DLightResponseError, "Failed to decode JSON payload"):
            await read_response(reader, 1.0, "test")

    async def test_invalid_utf8_rejected(self):
        bad = b"\xff\xfe\xfd"
        reader = self._reader_with(struct.pack(">I", len(bad)) + bad)
        with self.assertRaisesRegex(DLightResponseError, "Failed to decode"):
            await read_response(reader, 1.0, "test")

    async def test_echoed_command_rejected(self):
        command = {"commandId": "c1", "commandType": "EXECUTE"}
        reader = self._reader_with(frame(command))
        with self.assertRaisesRegex(DLightResponseError, "echoed back the command"):
            await read_response(reader, 1.0, "test", command=command)

    async def test_non_success_status_rejected(self):
        reader = self._reader_with(frame({"status": "ERROR_DEVICE_BUSY"}))
        with self.assertRaisesRegex(DLightResponseError, "non-SUCCESS status: 'ERROR_DEVICE_BUSY'"):
            await read_response(reader, 1.0, "test")

    async def test_incomplete_header_rejected(self):
        reader = self._reader_with(b"\x00\x00")
        with self.assertRaisesRegex(DLightResponseError, "while reading header"):
            await read_response(reader, 1.0, "test")

    async def test_incomplete_payload_rejected(self):
        reader = self._reader_with(struct.pack(">I", 100) + b"0123456789")
        with self.assertRaisesRegex(DLightResponseError, "while reading payload"):
            await read_response(reader, 1.0, "test")

    async def test_header_timeout(self):
        reader = self._reader_with(b"", eof=False)  # no data, connection stays open
        with self.assertRaisesRegex(DLightTimeoutError, "Timeout reading header"):
            await read_response(reader, 0.05, "test")

    async def test_payload_timeout(self):
        reader = self._reader_with(struct.pack(">I", 100), eof=False)
        with self.assertRaisesRegex(DLightTimeoutError, r"Timeout reading payload \(100 bytes\)"):
            await read_response(reader, 0.05, "test")


if __name__ == "__main__":
    unittest.main()
