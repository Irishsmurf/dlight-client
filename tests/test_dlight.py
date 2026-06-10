import unittest
import asyncio
import socket  # Still needed for socket errors, constants
import json
import struct
from unittest.mock import patch, MagicMock, AsyncMock

# --- Import from the package structure (an import failure must fail loudly) ---
from dlightclient import (
    AsyncDLightClient,
    discover_devices,
    DLightConnectionError,
    DLightTimeoutError,
    DLightResponseError,
    FACTORY_RESET_IP,
    MAX_PAYLOAD_SIZE,
    STATUS_SUCCESS,
)

# Import the internal protocol class for UDP testing
from dlightclient.discovery import _DiscoveryProtocol

from fake_server import FakeDLightServer

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
@patch(f"{DISCOVERY_MODULE_PATH}.asyncio.sleep", new_callable=AsyncMock)
@patch(f"{DISCOVERY_MODULE_PATH}.asyncio.get_running_loop")
class TestAsyncDLightClientUDP(unittest.IsolatedAsyncioTestCase):
    """Tests async UDP Discovery, mocking loop and protocol."""

    # Helper to configure the endpoint mock side effect for UDP tests
    def _configure_udp_endpoint_mock(self, mock_create_endpoint, listen_error=None, send_error=None):
        mock_listen_transport = AsyncMock(spec=asyncio.DatagramTransport)
        mock_send_transport = AsyncMock(spec=asyncio.DatagramTransport)
        mock_send_sock = MagicMock(spec=socket.socket)
        mock_send_transport.get_extra_info.return_value = mock_send_sock

        shared_results = []
        shared_set = set()
        protocol_instance_holder = [None]

        def protocol_factory():
            instance = _DiscoveryProtocol(shared_set, shared_results)
            protocol_instance_holder[0] = instance
            return instance

        # Define side effects based on potential errors during creation
        async def endpoint_side_effect(*args, **kwargs):
            # Simulate listener creation (first call)
            if listen_error and mock_create_endpoint.await_count == 1:
                print(f"TEST: Simulating listener endpoint error: {listen_error}")
                raise listen_error
            listener_protocol = protocol_factory()  # Create real protocol for listener
            listener_result = (mock_listen_transport, listener_protocol)

            # Simulate sender creation (second call)
            if send_error and mock_create_endpoint.await_count == 2:
                print(f"TEST: Simulating sender endpoint error: {send_error}")
                raise send_error
            sender_result = (mock_send_transport, MagicMock())  # Dummy protocol for sender

            # Return results based on call count
            if mock_create_endpoint.await_count == 1:
                return listener_result
            elif mock_create_endpoint.await_count == 2:
                return sender_result
            else:
                # Should not happen in current tests
                raise ValueError("create_datagram_endpoint called too many times")

        mock_create_endpoint.side_effect = endpoint_side_effect
        # Return shared list/set and holder for test assertions/side effects
        return shared_results, shared_set, protocol_instance_holder, mock_listen_transport, mock_send_transport

    # Test methods are async def
    async def test_discover_devices_no_response(self, mock_get_loop, mock_sleep):
        """Test async discovery timeout when no devices respond."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        # Configure endpoint mock (no errors expected here)
        _, _, _, mock_listen_transport, mock_send_transport = self._configure_udp_endpoint_mock(
            mock_loop.create_datagram_endpoint
        )

        # Call the standalone discover_devices function
        devices = await discover_devices(discovery_duration=0.1)

        # Assertions
        self.assertEqual(devices, [])  # Expect empty list on timeout
        mock_get_loop.assert_called_once()
        self.assertEqual(mock_loop.create_datagram_endpoint.await_count, 2)
        mock_send_transport.sendto.assert_called_once()
        mock_sleep.assert_awaited_once_with(0.1)
        mock_listen_transport.close.assert_called_once()
        mock_send_transport.close.assert_called_once()

    async def test_discover_devices_one_response(self, mock_get_loop, mock_sleep):
        """Test async discovery finding one device."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        # Configure endpoint mock, get shared lists and protocol holder
        shared_results, shared_set, protocol_instance_holder, mock_listen_transport, mock_send_transport = (
            self._configure_udp_endpoint_mock(mock_loop.create_datagram_endpoint)
        )

        # Device details to simulate
        device_ip = "192.168.1.101"
        device_id = "asyncdev1"
        response_payload_dict = {"deviceModel": "M1", "deviceId": device_id, "swVersion": "1", "hwVersion": "1"}
        response_bytes = json.dumps(response_payload_dict).encode("utf-8")
        sender_address = (device_ip, 12345)  # Source address of simulated response

        # Define the side effect for mock_sleep: Call the captured protocol instance's method
        async def sleep_and_receive(*args, **kwargs):
            proto_instance = protocol_instance_holder[0]
            self.assertIsNotNone(proto_instance, "Protocol instance was not captured by factory")
            # Manually call the protocol's method to simulate receiving data
            proto_instance.datagram_received(response_bytes, sender_address)

        mock_sleep.side_effect = sleep_and_receive  # Assign the side effect

        # --- Call the function under test ---
        await discover_devices(discovery_duration=0.1)

        # --- Assertions ---

        # Assert against the list modified by the protocol instance via the side effect
        self.assertEqual(len(shared_results), 1)  # Check the list managed by the test
        expected_device_info = response_payload_dict.copy()
        expected_device_info["ip_address"] = device_ip  # Check IP was added
        self.assertEqual(shared_results[0], expected_device_info)
        self.assertEqual(shared_set, {device_ip})  # Check set was updated

        # Verify the discovery process ran
        mock_get_loop.assert_called_once()
        self.assertEqual(mock_loop.create_datagram_endpoint.await_count, 2)
        mock_send_transport.sendto.assert_called_once()
        mock_sleep.assert_awaited_once_with(0.1)
        mock_listen_transport.close.assert_called_once()
        mock_send_transport.close.assert_called_once()

    async def test_discover_devices_multiple_responses(self, mock_get_loop, mock_sleep):
        """Test async discovery finding multiple devices."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        shared_results, shared_set, protocol_instance_holder, mock_listen_transport, mock_send_transport = (
            self._configure_udp_endpoint_mock(mock_loop.create_datagram_endpoint)
        )

        # --- Device 1 ---
        dev1_ip = "192.168.1.101"
        dev1_id = "dev1"
        dev1_payload = {"deviceId": dev1_id, "deviceModel": "M1"}
        dev1_bytes = json.dumps(dev1_payload).encode("utf-8")
        dev1_addr = (dev1_ip, 12345)
        # --- Device 2 ---
        dev2_ip = "192.168.1.102"
        dev2_id = "dev2"
        dev2_payload = {"deviceId": dev2_id, "deviceModel": "M2"}
        dev2_bytes = json.dumps(dev2_payload).encode("utf-8")
        dev2_addr = (dev2_ip, 54321)

        # Side effect to simulate receiving two datagrams
        async def sleep_and_receive_multiple(*args, **kwargs):
            proto_instance = protocol_instance_holder[0]
            self.assertIsNotNone(proto_instance)
            proto_instance.datagram_received(dev1_bytes, dev1_addr)
            proto_instance.datagram_received(dev2_bytes, dev2_addr)  # Receive second one

        mock_sleep.side_effect = sleep_and_receive_multiple

        await discover_devices(discovery_duration=0.1)

        # Assertions: Check shared list contains both devices
        self.assertEqual(len(shared_results), 2)
        self.assertEqual(shared_set, {dev1_ip, dev2_ip})
        # Check content (order might vary, check presence)
        found_ips = {d["ip_address"] for d in shared_results}
        self.assertEqual(found_ips, {dev1_ip, dev2_ip})
        found_ids = {d["deviceId"] for d in shared_results}
        self.assertEqual(found_ids, {dev1_id, dev2_id})

    async def test_discover_devices_duplicate_response(self, mock_get_loop, mock_sleep):
        """Test async discovery handles duplicate responses from the same IP."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        shared_results, shared_set, protocol_instance_holder, mock_listen_transport, mock_send_transport = (
            self._configure_udp_endpoint_mock(mock_loop.create_datagram_endpoint)
        )

        # Device details
        device_ip = "192.168.1.105"
        device_id = "dupdev"
        payload_dict = {"deviceId": device_id}
        payload_bytes = json.dumps(payload_dict).encode("utf-8")
        sender_address = (device_ip, 12345)

        # Side effect to simulate receiving the same datagram twice
        async def sleep_and_receive_duplicate(*args, **kwargs):
            proto_instance = protocol_instance_holder[0]
            self.assertIsNotNone(proto_instance)
            proto_instance.datagram_received(payload_bytes, sender_address)
            proto_instance.datagram_received(payload_bytes, sender_address)  # Send again

        mock_sleep.side_effect = sleep_and_receive_duplicate

        await discover_devices(discovery_duration=0.1)

        # Assertions: Check shared list contains only one entry
        self.assertEqual(len(shared_results), 1)
        self.assertEqual(shared_set, {device_ip})
        expected_device_info = payload_dict.copy()
        expected_device_info["ip_address"] = device_ip
        self.assertEqual(shared_results[0], expected_device_info)

    async def test_discover_devices_malformed_json(self, mock_get_loop, mock_sleep):
        """Test async discovery handles malformed JSON responses gracefully."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        shared_results, shared_set, protocol_instance_holder, mock_listen_transport, mock_send_transport = (
            self._configure_udp_endpoint_mock(mock_loop.create_datagram_endpoint)
        )

        # Malformed data
        malformed_bytes = b'{"deviceId": "bad", "model":'
        sender_address = ("192.168.1.200", 12345)

        # Side effect to simulate receiving bad data
        async def sleep_and_receive_bad(*args, **kwargs):
            proto_instance = protocol_instance_holder[0]
            self.assertIsNotNone(proto_instance)
            # Patch logger within discovery module to check warnings
            with patch(f"{DISCOVERY_MODULE_PATH}._LOGGER") as mock_logger:
                proto_instance.datagram_received(malformed_bytes, sender_address)
                # Check that a warning was logged
                mock_logger.warning.assert_called_once()
                self.assertIn("Error decoding discovery response", mock_logger.warning.call_args[0][0])

        mock_sleep.side_effect = sleep_and_receive_bad

        await discover_devices(discovery_duration=0.1)

        # Assertions: Check shared list is empty
        self.assertEqual(len(shared_results), 0)
        self.assertEqual(len(shared_set), 0)

    async def test_discover_devices_permission_error_bind(self, mock_get_loop, mock_sleep):
        """Test discovery handles PermissionError during listener bind."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        # Configure endpoint mock to raise PermissionError on first call (listener)
        self._configure_udp_endpoint_mock(
            mock_loop.create_datagram_endpoint, listen_error=PermissionError("Permission denied for UDP bind")
        )

        # Patch logger to check error message
        with patch(f"{DISCOVERY_MODULE_PATH}._LOGGER") as mock_logger:
            devices = await discover_devices(discovery_duration=0.1)
            # Assertions
            self.assertEqual(devices, [])  # Expect empty list on error
            mock_logger.error.assert_called_once()
            self.assertIn("Permission denied for UDP broadcast or binding", mock_logger.error.call_args[0][0])

        # Check endpoint creation was attempted only once
        self.assertEqual(mock_loop.create_datagram_endpoint.await_count, 1)
        mock_sleep.assert_not_awaited()  # Should exit before sleep

    async def test_discover_devices_os_error_bind(self, mock_get_loop, mock_sleep):
        """Test discovery handles OSError (e.g., port in use) during listener bind."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        # Configure endpoint mock to raise OSError on first call (listener)
        self._configure_udp_endpoint_mock(
            mock_loop.create_datagram_endpoint, listen_error=OSError("Address already in use")
        )

        # Patch logger to check error message
        with patch(f"{DISCOVERY_MODULE_PATH}._LOGGER") as mock_logger:
            devices = await discover_devices(discovery_duration=0.1)
            # Assertions
            self.assertEqual(devices, [])  # Expect empty list on error
            mock_logger.error.assert_called_once()
            self.assertIn("Network error during discovery", mock_logger.error.call_args[0][0])

        # Check endpoint creation was attempted only once
        self.assertEqual(mock_loop.create_datagram_endpoint.await_count, 1)
        mock_sleep.assert_not_awaited()  # Should exit before sleep


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


if __name__ == "__main__":
    # Configure logging for tests if desired
    # logging.basicConfig(level=logging.DEBUG)
    unittest.main()
