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
from dlightclient._frame import (
    decode_command,
    encode_command,
    encode_response,
    mask_command,
    read_response,
)


def frame(payload_dict: dict) -> bytes:
    payload = json.dumps(payload_dict).encode("utf-8")
    return struct.pack(">I", len(payload)) + payload


class TestWireFormatAnchors(unittest.IsolatedAsyncioTestCase):
    """Byte-literal anchors, pinning the wire format independently of the codec.

    Every other framing test in this file builds its bytes with the same
    ``struct.pack(">I", ...)`` the codec uses, so a change to the prefix format
    would move test and implementation together and stay green. These assert
    against literals typed out by hand, which is what makes it safe for the
    fake servers to share this codec: if the client and the fakes ever agree
    with each other but disagree with the wire, these fail.
    """

    ACK_ON_THE_WIRE = b'\x00\x00\x00\x15{"status": "SUCCESS"}'

    def test_encode_response_emits_exact_bytes(self):
        self.assertEqual(encode_response({"status": "SUCCESS"}), self.ACK_ON_THE_WIRE)

    async def test_read_response_accepts_the_same_literal(self):
        reader = asyncio.StreamReader()
        reader.feed_data(self.ACK_ON_THE_WIRE)
        reader.feed_eof()
        result = await read_response(reader, 1.0, "anchor")
        self.assertEqual(result["status"], STATUS_SUCCESS)

    def test_length_prefix_is_big_endian(self):
        # 258 bytes of payload -> 0x00000102, which little-endian would invert.
        encoded = encode_response({"pad": "x" * 247})
        self.assertEqual(len(encoded) - 4, 258)
        self.assertEqual(encoded[:4], b"\x00\x00\x01\x02")


class TestEncodeResponse(unittest.IsolatedAsyncioTestCase):
    async def test_round_trips_through_read_response(self):
        payload = {"status": STATUS_SUCCESS, "states": {"on": True, "brightness": 40}}
        reader = asyncio.StreamReader()
        reader.feed_data(encode_response(payload))
        reader.feed_eof()
        self.assertEqual(await read_response(reader, 1.0, "round trip"), payload)

    def test_empty_payload_still_carries_a_length_prefix(self):
        self.assertEqual(encode_response({}), b"\x00\x00\x00\x02{}")


class TestDecodeCommand(unittest.TestCase):
    """The request stream is bare JSON: no length prefix, no delimiter."""

    def test_returns_none_and_consumes_nothing_when_incomplete(self):
        buffer = bytearray(b'{"commandId": "c1", "comm')
        self.assertIsNone(decode_command(buffer))
        self.assertEqual(buffer, bytearray(b'{"commandId": "c1", "comm'))

    def test_decodes_one_command_and_consumes_exactly_its_bytes(self):
        buffer = bytearray(b'{"a": 1}{"b": 2}')
        self.assertEqual(decode_command(buffer), {"a": 1})
        self.assertEqual(buffer, bytearray(b'{"b": 2}'))
        self.assertEqual(decode_command(buffer), {"b": 2})
        self.assertEqual(buffer, bytearray())

    def test_handles_a_multibyte_character_split_across_reads(self):
        # ensure_ascii=False is essential: the default would escape "é" to
        # é and the buffer would be pure ASCII, testing nothing.
        payload = json.dumps({"name": "café"}, ensure_ascii=False).encode("utf-8")
        self.assertIn(b"\xc3\xa9", payload)  # the two bytes of "é"

        # Split between them, which is where a real read boundary can land.
        split = payload.index(b"\xc3\xa9") + 1
        buffer = bytearray(payload[:split])
        self.assertIsNone(decode_command(buffer))
        self.assertEqual(buffer, bytearray(payload[:split]), "nothing consumed while incomplete")

        buffer.extend(payload[split:])
        self.assertEqual(decode_command(buffer), {"name": "café"})
        self.assertEqual(buffer, bytearray())

    def test_consumes_byte_length_not_character_length(self):
        """Guard on the one genuinely subtle line in the decoder.

        ``raw_decode`` reports a *character* offset while the buffer holds
        bytes. Deleting by character count would leave a stray trailing byte
        for every multibyte character, desynchronising every later command on
        the connection.
        """
        first = json.dumps({"n": "üüü"}, ensure_ascii=False).encode("utf-8")
        self.assertGreater(len(first), len(json.dumps({"n": "üüü"}, ensure_ascii=False)))

        buffer = bytearray(first + b'{"next": true}')
        self.assertEqual(decode_command(buffer), {"n": "üüü"})
        self.assertEqual(buffer, bytearray(b'{"next": true}'), "consumed the wrong number of bytes")
        self.assertEqual(decode_command(buffer), {"next": True})

    def test_empty_buffer_is_incomplete_not_an_error(self):
        self.assertIsNone(decode_command(bytearray()))

    def test_malformed_json_is_incomplete_until_it_is_not(self):
        buffer = bytearray(b"not json at all")
        self.assertIsNone(decode_command(buffer))


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
