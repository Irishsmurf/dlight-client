import asyncio
import json
import socket
import struct
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from fake_server import FakeDLightServer

# --- Import from the package structure (an import failure must fail loudly) ---
from dlightclient import (
    FACTORY_RESET_IP,
    MAX_PAYLOAD_SIZE,
    STATUS_SUCCESS,
    AsyncDLightClient,
    DLightConnectionError,
    DLightResponseError,
    DLightTimeoutError,
    discover_devices,
    discover_devices_stream,
)

# Import the internal protocol class for UDP testing

# Module paths for patching specific implementations
CLIENT_MODULE_PATH = "dlightclient.client"
DISCOVERY_MODULE_PATH = "dlightclient.discovery"


# --- Test Cases ---


# Use standard TestCase for validation tests that don't need an event loop
class TestAsyncDLightClientValidation(unittest.TestCase):
    """Tests input validation for client methods (synchronous checks)."""

    def setUp(self):
        # Instantiate the real client class from the refactored structure
        self.client = AsyncDLightClient()
        self.target_ip = "192.168.1.100"
        self.device_id = "testdevice1"

    # Patch the internal command sending method within the client module
    @patch(f"{CLIENT_MODULE_PATH}.AsyncDLightClient._async_send_tcp_command", new_callable=AsyncMock)
    def test_set_brightness_valid(self, mock_send_cmd):
        """Test brightness validation."""
        mock_send_cmd.return_value = {"status": STATUS_SUCCESS}
        # Use asyncio.run() as the test method itself is synchronous
        asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 0))
        asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 50))
        asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 100))
        asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 50.5))  # Should cast to int
        # Check the command passed to the (mocked) underlying send method
        call_args, _ = mock_send_cmd.call_args_list[-1]
        command = call_args[1]  # command dict is the second arg to _async_send_tcp_command
        self.assertEqual(command["commands"][0]["brightness"], 50)  # Asserts int casting

    def test_set_brightness_invalid(self):
        """Test invalid brightness raises ValueError."""
        with self.assertRaisesRegex(ValueError, "Brightness must be between 0 and 100"):
            # Validation happens before await, so no asyncio.run needed here
            asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, -1))
        with self.assertRaisesRegex(ValueError, "Brightness must be between 0 and 100"):
            asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 101))

    # Patch the internal command sending method within the client module
    @patch(f"{CLIENT_MODULE_PATH}.AsyncDLightClient._async_send_tcp_command", new_callable=AsyncMock)
    def test_set_color_temperature_valid(self, mock_send_cmd):
        """Test color temp validation."""
        mock_send_cmd.return_value = {"status": STATUS_SUCCESS}
        asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 2600))
        asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 4500))
        asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 6000))
        asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 4500.7))  # Should cast to int
        call_args, _ = mock_send_cmd.call_args_list[-1]
        command = call_args[1]
        self.assertEqual(command["commands"][0]["color"]["temperature"], 4500)  # Asserts int casting

    def test_set_color_temperature_invalid(self):
        """Test invalid color temp raises ValueError."""
        with self.assertRaisesRegex(ValueError, "Color temperature must be between 2600 and 6000"):
            asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 2599))
        with self.assertRaisesRegex(ValueError, "Color temperature must be between 2600 and 6000"):
            asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 6001))


# Tests run against a real in-process TCP server speaking the dLight protocol
# (tests/fake_server.py), so they assert observable behavior rather than the
# client's internal stream read/write sequence.
class TestAsyncDLightClientTCP(unittest.IsolatedAsyncioTestCase):
    """Tests async TCP command sending and response handling."""

    def setUp(self):
        self.client = AsyncDLightClient(default_timeout=0.5)
        self.device_id = "testdevice1"

    async def asyncSetUp(self):
        self.server = FakeDLightServer()
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.stop()

    def _command(self, command_type="QUERY_DEVICE_STATES", **extra):
        command = {
            "commandId": "cmd-test-123",
            "deviceId": self.device_id,
            "commandType": command_type,
            "commands": [],
        }
        command.update(extra)
        return command

    async def _send(self, command_type="QUERY_DEVICE_STATES", **extra):
        return await self.client._async_send_tcp_command(
            self.server.host, self._command(command_type, **extra), port=self.server.port
        )

    async def test_send_tcp_success(self):
        """Test successful TCP command send and response."""
        success_payload = {
            "commandId": "cmd-test-123",
            "deviceId": self.device_id,
            "status": STATUS_SUCCESS,
            "on": True,
        }
        self.server.respond(success_payload)

        response = await self._send("EXECUTE", commands=[{"on": True}])

        self.assertEqual(response, success_payload)
        self.assertEqual(len(self.server.received_commands), 1)
        sent_cmd = self.server.received_commands[0]
        self.assertEqual(sent_cmd["commandId"], "cmd-test-123")
        self.assertEqual(sent_cmd["commands"][0]["on"], True)
        # Non-persistent client closes the connection after the call
        await asyncio.sleep(0.05)
        self.assertEqual(self.server.closed_connections, 1)

    async def test_send_tcp_query_state(self):
        """Test successful query response with a states payload."""
        query_response_payload = {
            "commandId": "cmd-test-123",
            "deviceId": self.device_id,
            "status": STATUS_SUCCESS,
            "states": {"on": False, "brightness": 50, "color": {"temperature": 4000}},
        }
        self.server.respond(query_response_payload)

        response = await self._send("QUERY_DEVICE_STATES")

        self.assertEqual(response, query_response_payload)
        self.assertEqual(self.server.received_commands[0]["commandType"], "QUERY_DEVICE_STATES")

    async def test_send_tcp_zero_payload_response(self):
        """Test handling of a response with zero payload length."""
        self.server.respond_raw(struct.pack(">I", 0))

        response = await self._send("EXECUTE", commands=[{"on": False}])

        # The client synthesizes a success response for empty payloads
        self.assertEqual(response, {"status": STATUS_SUCCESS})

    async def test_send_tcp_max_payload_exceeded(self):
        """Test error when header indicates payload size exceeds MAX_PAYLOAD_SIZE."""
        large_length = MAX_PAYLOAD_SIZE + 1
        self.server.respond_raw(struct.pack(">I", large_length))

        with self.assertRaisesRegex(DLightResponseError, f"Payload length {large_length}.*exceeds maximum limit"):
            await self._send("QUERY_DEVICE_INFO")

    async def test_send_tcp_read_payload_incomplete(self):
        """Test the connection closing mid-payload."""
        # Header promises 100 bytes but only 10 arrive before the close
        self.server.respond_raw(struct.pack(">I", 100) + b"0123456789", close=True)

        with self.assertRaisesRegex(DLightResponseError, "Connection closed unexpectedly while reading payload"):
            await self._send("EXECUTE", commands=[{"brightness": 55}])

    async def test_send_tcp_non_success_status(self):
        """Test handling non-SUCCESS status."""
        self.server.respond({"commandId": "cmd-test-123", "deviceId": self.device_id, "status": "ERROR_DEVICE_BUSY"})

        with self.assertRaisesRegex(DLightResponseError, "dLight returned non-SUCCESS status: 'ERROR_DEVICE_BUSY'"):
            await self._send("QUERY_DEVICE_INFO")

    async def test_send_tcp_connect_timeout(self):
        """Test connection timeout.

        A connect timeout cannot be simulated deterministically on loopback,
        so this one test stubs the connection establishment.
        """
        with patch("dlightclient._pool.asyncio.open_connection", new_callable=AsyncMock) as mock_open:
            mock_open.side_effect = asyncio.TimeoutError("Connect timed out")
            with self.assertRaisesRegex(DLightTimeoutError, "Timeout connecting to"):
                await self._send("QUERY_DEVICE_STATES")

    async def test_send_tcp_connect_refused(self):
        """Test connection refused error (nothing listening on the port)."""
        port = self.server.port
        await self.server.stop()

        with self.assertRaisesRegex(DLightConnectionError, "Connection refused by"):
            await self.client._async_send_tcp_command(self.server.host, self._command(), port=port)

    async def test_send_tcp_read_header_timeout(self):
        """Test timeout waiting for the response header."""
        self.server.hang()

        with self.assertRaisesRegex(DLightTimeoutError, "Timeout reading header for command"):
            await self._send("QUERY_DEVICE_INFO")

    async def test_send_tcp_read_payload_timeout(self):
        """Test timeout waiting for the payload after a valid header."""
        self.server.respond_raw(struct.pack(">I", 100))  # promise 100 bytes, never send them

        with self.assertRaisesRegex(DLightTimeoutError, r"Timeout reading payload \(100 bytes\)"):
            await self._send("QUERY_DEVICE_INFO")

    async def test_send_tcp_incomplete_header(self):
        """Test the connection closing mid-header."""
        self.server.respond_raw(b"\x00\x00", close=True)

        with self.assertRaisesRegex(DLightResponseError, "Connection closed unexpectedly while reading header"):
            await self._send("QUERY_DEVICE_STATES")

    async def test_send_tcp_invalid_payload_json(self):
        """Test invalid JSON payload."""
        invalid_payload = b'{"status": "SUCCESS", "on": tru'  # Truncated JSON
        self.server.respond_raw(struct.pack(">I", len(invalid_payload)) + invalid_payload)

        with self.assertRaisesRegex(DLightResponseError, "Failed to decode JSON payload"):
            await self._send("EXECUTE", commands=[{"on": True}])

    async def test_send_tcp_echoed_command(self):
        """Test that a device echoing the command back is treated as an error."""
        self.server.echo()

        with self.assertRaisesRegex(DLightResponseError, "echoed back the command"):
            await self._send("EXECUTE", commands=[{"on": True}])

    async def test_connect_to_wifi_full_path(self):
        """Test connect_to_wifi over the wire (explicit target ip/port)."""
        self.server.respond({"status": STATUS_SUCCESS})

        await self.client.connect_to_wifi(
            self.device_id, "MySSID", "MyPassword", target_ip=self.server.host, port=self.server.port
        )

        sent_cmd = self.server.received_commands[0]
        self.assertEqual(sent_cmd["commandType"], "SSID_CONNECT")
        self.assertEqual(sent_cmd["ssid"], "MySSID")
        self.assertEqual(sent_cmd["password"], "MyPassword")

    async def test_connect_to_wifi_uses_factory_ip(self):
        """Verify connect_to_wifi targets the factory-reset IP by default."""
        with patch.object(self.client, "_async_send_tcp_command", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"status": STATUS_SUCCESS}

            await self.client.connect_to_wifi(self.device_id, "MySSID", "MyPassword")

            call_args, _ = mock_send.call_args
            self.assertEqual(call_args[0], FACTORY_RESET_IP)


# Use IsolatedAsyncioTestCase for tests involving actual awaits on mocked objects
# Patch asyncio's loop methods and sleep where they are used: in the discovery module
def _fake_discovery_endpoints(responses=(), listen_error=None):
    """Build a stand-in for ``loop.create_datagram_endpoint``.

    The first call (the listener) gets the real protocol; the second (the
    sender) gets a transport whose ``sendto`` makes every ``(bytes, addr)`` in
    *responses* arrive at the listener, as lamps answering the probe would.
    Returns ``(create_endpoint, listen_transport, send_transport, calls)``.
    """
    listen_transport = MagicMock(spec=asyncio.DatagramTransport)
    send_transport = MagicMock(spec=asyncio.DatagramTransport)
    calls = []

    async def create_endpoint(protocol_factory, **kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            if listen_error is not None:
                raise listen_error
            listener = protocol_factory()
            listen_transport.close.side_effect = lambda: asyncio.get_running_loop().call_soon(
                listener.connection_lost, None
            )

            def answer_probe(_payload):
                for data, addr in responses:
                    asyncio.get_running_loop().call_soon(listener.datagram_received, data, addr)

            send_transport.sendto.side_effect = answer_probe
            return listen_transport, listener
        return send_transport, protocol_factory()

    return create_endpoint, listen_transport, send_transport, calls


def _response(ip, **payload):
    return json.dumps(payload).encode("utf-8"), (ip, 12345)


class TestAsyncDLightClientUDP(unittest.IsolatedAsyncioTestCase):
    """Tests discover_devices against a faked datagram endpoint."""

    async def _discover(self, responses=(), listen_error=None, **kwargs):
        create_endpoint, listen_transport, send_transport, calls = _fake_discovery_endpoints(responses, listen_error)
        loop = asyncio.get_running_loop()
        with patch.object(loop, "create_datagram_endpoint", new=create_endpoint):
            devices = await discover_devices(discovery_duration=kwargs.pop("discovery_duration", 0.05), **kwargs)
        return devices, listen_transport, send_transport, calls

    async def test_discover_devices_no_response(self):
        """No replies within the window yields an empty list and closes both sockets."""
        devices, listen_transport, send_transport, calls = await self._discover()

        self.assertEqual(devices, [])
        self.assertEqual(len(calls), 2)
        send_transport.sendto.assert_called_once()
        listen_transport.close.assert_called_once()
        send_transport.close.assert_called_once()

    async def test_discover_devices_sends_the_probe_as_literal_text(self):
        """The probe goes out as the 40 ASCII characters; real lamps ignore the hex-decoded bytes."""
        _, _, send_transport, _ = await self._discover()

        send_transport.sendto.assert_called_once_with(b"476f6f676c654e50455f457269635f5761796e65")

    async def test_discover_devices_one_response(self):
        """A single reply is returned with the sender's IP stamped on it."""
        devices, listen_transport, send_transport, _ = await self._discover(
            [_response("192.168.1.101", deviceModel="M1", deviceId="asyncdev1", swVersion="1", hwVersion="1")]
        )

        self.assertEqual(
            devices,
            [
                {
                    "deviceModel": "M1",
                    "deviceId": "asyncdev1",
                    "swVersion": "1",
                    "hwVersion": "1",
                    "ip_address": "192.168.1.101",
                }
            ],
        )
        listen_transport.close.assert_called_once()
        send_transport.close.assert_called_once()

    async def test_discover_devices_multiple_responses(self):
        """Replies from several lamps are all returned."""
        devices, _, _, _ = await self._discover(
            [
                _response("192.168.1.101", deviceId="dev1", deviceModel="M1"),
                _response("192.168.1.102", deviceId="dev2", deviceModel="M2"),
            ]
        )

        self.assertEqual({d["ip_address"] for d in devices}, {"192.168.1.101", "192.168.1.102"})
        self.assertEqual({d["deviceId"] for d in devices}, {"dev1", "dev2"})

    async def test_discover_devices_duplicate_response(self):
        """Repeated replies from one IP are reported once."""
        reply = _response("192.168.1.105", deviceId="dupdev")
        devices, _, _, _ = await self._discover([reply, reply])

        self.assertEqual(devices, [{"deviceId": "dupdev", "ip_address": "192.168.1.105"}])

    async def test_discover_devices_malformed_json(self):
        """A reply that is not JSON is logged and skipped."""
        with patch(f"{DISCOVERY_MODULE_PATH}._LOGGER") as mock_logger:
            devices, _, _, _ = await self._discover([(b'{"deviceId": "bad", "model":', ("192.168.1.200", 12345))])

        self.assertEqual(devices, [])
        mock_logger.warning.assert_called_once()
        self.assertIn("Error decoding discovery response", mock_logger.warning.call_args[0][0])

    async def test_discover_devices_permission_error_bind(self):
        """PermissionError binding the listener is logged and yields an empty list."""
        with patch(f"{DISCOVERY_MODULE_PATH}._LOGGER") as mock_logger:
            devices, _, send_transport, calls = await self._discover(
                listen_error=PermissionError("Permission denied for UDP bind")
            )

        self.assertEqual(devices, [])
        self.assertEqual(len(calls), 1)
        send_transport.sendto.assert_not_called()
        mock_logger.error.assert_called_once()
        self.assertIn("Permission denied for UDP broadcast or binding", mock_logger.error.call_args[0][0])

    async def test_discover_devices_os_error_bind(self):
        """OSError binding the listener (e.g. port in use) is logged and yields an empty list."""
        with patch(f"{DISCOVERY_MODULE_PATH}._LOGGER") as mock_logger:
            devices, _, _, calls = await self._discover(listen_error=OSError("Address already in use"))

        self.assertEqual(devices, [])
        self.assertEqual(len(calls), 1)
        mock_logger.error.assert_called_once()
        self.assertIn("Network error during discovery", mock_logger.error.call_args[0][0])

    async def test_discover_devices_passes_ports_and_broadcast(self):
        """Ports and broadcast address reach the endpoints; the sender requests broadcast."""
        _, _, _, calls = await self._discover(response_port=1111, discovery_port=2222, broadcast_address="10.0.0.255")

        self.assertEqual(calls[0]["local_addr"], ("0.0.0.0", 1111))
        self.assertEqual(calls[1]["remote_addr"], ("10.0.0.255", 2222))
        self.assertTrue(calls[1]["allow_broadcast"])

    async def test_discover_devices_back_to_back_rebinds_response_port(self):
        """A discovery started as soon as the previous one returns can bind the same port."""
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.bind(("127.0.0.1", 0))
            response_port = probe.getsockname()[1]

        with patch(f"{DISCOVERY_MODULE_PATH}._LOGGER") as mock_logger:
            for _ in range(2):
                await discover_devices(
                    discovery_duration=0.01, response_port=response_port, broadcast_address="127.0.0.1"
                )

        mock_logger.error.assert_not_called()

    async def test_discover_devices_closes_sockets_when_cancelled(self):
        """Cancelling discover_devices mid-window still releases both sockets."""
        create_endpoint, listen_transport, send_transport, _ = _fake_discovery_endpoints()
        loop = asyncio.get_running_loop()
        with patch.object(loop, "create_datagram_endpoint", new=create_endpoint):
            task = asyncio.create_task(discover_devices(discovery_duration=10))
            await asyncio.sleep(0.01)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task

        listen_transport.close.assert_called_once()
        send_transport.close.assert_called_once()


class TestAsyncDLightClientPersistence(unittest.IsolatedAsyncioTestCase):
    """Tests connection pooling and persistent connections."""

    def setUp(self):
        self.device_id = "testdevice1"

    async def asyncSetUp(self):
        self.server = FakeDLightServer()
        await self.server.start()

    async def asyncTearDown(self):
        await self.server.stop()

    def _command(self, n=1):
        return {
            "commandId": f"cmd-persist-{n}",
            "deviceId": self.device_id,
            "commandType": "QUERY_DEVICE_STATES",
            "commands": [],
        }

    async def _send(self, client, n=1):
        return await client._async_send_tcp_command(self.server.host, self._command(n), port=self.server.port)

    async def test_non_persistent_closes_connection(self):
        """A non-persistent client opens and closes a connection per call."""
        client = AsyncDLightClient(persistent=False, default_timeout=0.5)

        await self._send(client, 1)
        await self._send(client, 2)

        self.assertEqual(self.server.connection_count, 2)
        await asyncio.sleep(0.05)
        self.assertEqual(self.server.closed_connections, 2)

    async def test_persistent_reuses_connection(self):
        """A persistent client reuses one connection for sequential calls."""
        client = AsyncDLightClient(persistent=True, default_timeout=0.5)
        try:
            await self._send(client, 1)
            await self._send(client, 2)
            self.assertEqual(self.server.connection_count, 1)
            self.assertEqual(self.server.closed_connections, 0)
        finally:
            await client.close()

        await asyncio.sleep(0.05)
        self.assertEqual(self.server.closed_connections, 1)

    async def test_context_manager_persistence(self):
        """A persistent client used as a context manager reuses connections
        inside the block and closes them on exit."""
        async with AsyncDLightClient(persistent=True, default_timeout=0.5) as client:
            await self._send(client, 1)
            await self._send(client, 2)
            self.assertEqual(self.server.connection_count, 1)
            self.assertEqual(self.server.closed_connections, 0)

        await asyncio.sleep(0.05)
        self.assertEqual(self.server.closed_connections, 1)


class TestAsyncDLightClientUDPStream(unittest.IsolatedAsyncioTestCase):
    """Tests the async streaming UDP discovery."""

    async def test_discover_devices_stream_one_response(self):
        """Test discover_devices_stream yielding one device."""
        loop = asyncio.get_running_loop()
        mock_listen_transport = AsyncMock(spec=asyncio.DatagramTransport)
        mock_send_transport = AsyncMock(spec=asyncio.DatagramTransport)

        protocol_instance_holder = [None]
        await_count = 0

        async def mock_create_datagram_endpoint(protocol_factory, local_addr=None, remote_addr=None, **kwargs):
            nonlocal await_count
            await_count += 1
            if await_count == 1:
                proto = protocol_factory()
                protocol_instance_holder[0] = proto
                mock_listen_transport.close.side_effect = lambda: loop.call_soon(proto.connection_lost, None)
                return (mock_listen_transport, proto)
            else:
                return (mock_send_transport, MagicMock())

        # Patch create_datagram_endpoint on the running event loop
        with patch.object(loop, "create_datagram_endpoint", new=mock_create_datagram_endpoint):
            device_ip = "192.168.1.101"
            device_id = "streamdev1"
            response_payload_dict = {"deviceModel": "M1", "deviceId": device_id}
            response_bytes = json.dumps(response_payload_dict).encode("utf-8")
            sender_address = (device_ip, 12345)

            devices = []

            async def run_stream():
                async for dev in discover_devices_stream(timeout=0.2):
                    devices.append(dev)

            stream_task = asyncio.create_task(run_stream())
            await asyncio.sleep(0.01)

            proto_instance = protocol_instance_holder[0]
            self.assertIsNotNone(proto_instance)
            proto_instance.datagram_received(response_bytes, sender_address)

            await stream_task

            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]["deviceId"], device_id)
            self.assertEqual(devices[0]["ip_address"], device_ip)

            mock_listen_transport.close.assert_called_once()
            mock_send_transport.close.assert_called_once()

    async def test_discover_devices_stream_multiple_responses(self):
        """Test discover_devices_stream yielding multiple devices incrementally."""
        loop = asyncio.get_running_loop()
        mock_listen_transport = AsyncMock(spec=asyncio.DatagramTransport)
        mock_send_transport = AsyncMock(spec=asyncio.DatagramTransport)

        protocol_instance_holder = [None]
        await_count = 0

        async def mock_create_datagram_endpoint(protocol_factory, local_addr=None, remote_addr=None, **kwargs):
            nonlocal await_count
            await_count += 1
            if await_count == 1:
                proto = protocol_factory()
                protocol_instance_holder[0] = proto
                mock_listen_transport.close.side_effect = lambda: loop.call_soon(proto.connection_lost, None)
                return (mock_listen_transport, proto)
            else:
                return (mock_send_transport, MagicMock())

        with patch.object(loop, "create_datagram_endpoint", new=mock_create_datagram_endpoint):
            dev1_ip = "192.168.1.101"
            dev1_payload = {"deviceModel": "M1", "deviceId": "dev1"}
            dev1_bytes = json.dumps(dev1_payload).encode("utf-8")

            dev2_ip = "192.168.1.102"
            dev2_payload = {"deviceModel": "M2", "deviceId": "dev2"}
            dev2_bytes = json.dumps(dev2_payload).encode("utf-8")

            devices = []

            async def run_stream():
                async for dev in discover_devices_stream(timeout=0.3):
                    devices.append(dev)

            stream_task = asyncio.create_task(run_stream())
            await asyncio.sleep(0.01)

            proto_instance = protocol_instance_holder[0]
            self.assertIsNotNone(proto_instance)

            # Receive first device
            proto_instance.datagram_received(dev1_bytes, (dev1_ip, 12345))
            await asyncio.sleep(0.02)
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]["deviceId"], "dev1")

            # Receive second device
            proto_instance.datagram_received(dev2_bytes, (dev2_ip, 12345))
            await asyncio.sleep(0.02)
            self.assertEqual(len(devices), 2)
            self.assertEqual(devices[1]["deviceId"], "dev2")

            await stream_task
            self.assertEqual(len(devices), 2)

    async def test_discover_devices_stream_deduplication(self):
        """Test discover_devices_stream deduplicates by IP address."""
        loop = asyncio.get_running_loop()
        mock_listen_transport = AsyncMock(spec=asyncio.DatagramTransport)
        mock_send_transport = AsyncMock(spec=asyncio.DatagramTransport)

        protocol_instance_holder = [None]
        await_count = 0

        async def mock_create_datagram_endpoint(protocol_factory, local_addr=None, remote_addr=None, **kwargs):
            nonlocal await_count
            await_count += 1
            if await_count == 1:
                proto = protocol_factory()
                protocol_instance_holder[0] = proto
                mock_listen_transport.close.side_effect = lambda: loop.call_soon(proto.connection_lost, None)
                return (mock_listen_transport, proto)
            else:
                return (mock_send_transport, MagicMock())

        with patch.object(loop, "create_datagram_endpoint", new=mock_create_datagram_endpoint):
            dev_ip = "192.168.1.101"
            dev_payload = {"deviceModel": "M1", "deviceId": "dev1"}
            dev_bytes = json.dumps(dev_payload).encode("utf-8")

            devices = []

            async def run_stream():
                async for dev in discover_devices_stream(timeout=0.2):
                    devices.append(dev)

            stream_task = asyncio.create_task(run_stream())
            await asyncio.sleep(0.01)

            proto_instance = protocol_instance_holder[0]
            self.assertIsNotNone(proto_instance)

            # Receive the same device twice
            proto_instance.datagram_received(dev_bytes, (dev_ip, 12345))
            proto_instance.datagram_received(dev_bytes, (dev_ip, 12345))
            await asyncio.sleep(0.02)

            await stream_task
            self.assertEqual(len(devices), 1)

    async def test_discover_devices_stream_drains_queue_on_timeout(self):
        """Test discover_devices_stream yields items remaining in the queue after timeout."""
        loop = asyncio.get_running_loop()
        mock_listen_transport = AsyncMock(spec=asyncio.DatagramTransport)
        mock_send_transport = AsyncMock(spec=asyncio.DatagramTransport)

        protocol_instance_holder = [None]
        await_count = 0

        async def mock_create_datagram_endpoint(protocol_factory, local_addr=None, remote_addr=None, **kwargs):
            nonlocal await_count
            await_count += 1
            if await_count == 1:
                proto = protocol_factory()
                protocol_instance_holder[0] = proto
                mock_listen_transport.close.side_effect = lambda: loop.call_soon(proto.connection_lost, None)
                return (mock_listen_transport, proto)
            else:
                return (mock_send_transport, MagicMock())

        with patch.object(loop, "create_datagram_endpoint", new=mock_create_datagram_endpoint):
            dev1_ip = "192.168.1.101"
            dev1_payload = {"deviceModel": "M1", "deviceId": "dev1"}
            dev1_bytes = json.dumps(dev1_payload).encode("utf-8")

            dev2_ip = "192.168.1.102"
            dev2_payload = {"deviceModel": "M2", "deviceId": "dev2"}
            dev2_bytes = json.dumps(dev2_payload).encode("utf-8")

            gen = discover_devices_stream(timeout=0.01)

            step_task = asyncio.create_task(gen.__anext__())
            await asyncio.sleep(0.005)

            proto_instance = protocol_instance_holder[0]
            self.assertIsNotNone(proto_instance)

            proto_instance.datagram_received(dev1_bytes, (dev1_ip, 12345))
            proto_instance.datagram_received(dev2_bytes, (dev2_ip, 12345))

            first_dev = await step_task
            self.assertEqual(first_dev["deviceId"], "dev1")

            await asyncio.sleep(0.02)

            second_dev = await gen.__anext__()
            self.assertEqual(second_dev["deviceId"], "dev2")

            with self.assertRaises(StopAsyncIteration):
                await gen.__anext__()

    async def test_discover_devices_stream_permission_error(self):
        """Test discover_devices_stream handling of PermissionError during bind."""
        loop = asyncio.get_running_loop()

        async def mock_create_datagram_endpoint(protocol_factory, local_addr=None, remote_addr=None, **kwargs):
            raise PermissionError("Permission denied for UDP bind")

        with patch.object(loop, "create_datagram_endpoint", new=mock_create_datagram_endpoint):
            devices = []
            async for dev in discover_devices_stream(timeout=0.2):
                devices.append(dev)
            self.assertEqual(devices, [])


if __name__ == "__main__":
    # Configure logging for tests if desired
    # logging.basicConfig(level=logging.DEBUG)
    unittest.main()
