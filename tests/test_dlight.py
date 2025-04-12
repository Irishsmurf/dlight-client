import unittest
import asyncio
import socket # Still needed for socket errors, constants
import json
import struct
import time # Keep for synchronous _generate_command_id if needed by mocks
import uuid
import binascii
import logging
from unittest.mock import patch, MagicMock, ANY, call, AsyncMock

# --- Import from the refactored package structure ---
try:
    # Import the public interface defined in dlightclient/__init__.py
    from dlightclient import (
        AsyncDLightClient,
        discover_devices, # Now a standalone function
        DLightError,
        DLightConnectionError,
        DLightTimeoutError,
        DLightCommandError,
        DLightResponseError,
        # Import constants needed for tests
        FACTORY_RESET_IP,
        DEFAULT_TCP_PORT,
        DEFAULT_UDP_DISCOVERY_PORT,
        DEFAULT_UDP_RESPONSE_PORT,
        BROADCAST_ADDRESS,
        UDP_DISCOVERY_PAYLOAD_HEX,
        DEFAULT_TIMEOUT,
        MAX_PAYLOAD_SIZE, # Import for testing limits
        STATUS_SUCCESS, # Import for checking success status
    )
    # Import the internal protocol class for UDP testing if needed directly
    from dlightclient.discovery import _DiscoveryProtocol

    # Define module paths for patching specific implementations
    CLIENT_MODULE_PATH = 'dlightclient.client'
    DISCOVERY_MODULE_PATH = 'dlightclient.discovery'
    _IMPORT_SUCCESS = True

except ImportError as e:
    _IMPORT_SUCCESS = False
    print(f"Could not import from dlightclient package. Ensure it's installed or accessible.")
    print(f"Import Error: {e}")
    # Define dummy classes/variables if import fails
    CLIENT_MODULE_PATH = 'dlightclient.client' # Fallback path
    DISCOVERY_MODULE_PATH = 'dlightclient.discovery' # Fallback path
    class DLightError(Exception): pass
    class DLightConnectionError(DLightError): pass
    class DLightTimeoutError(DLightConnectionError): pass
    class DLightCommandError(DLightError): pass
    class DLightResponseError(DLightError): pass
    class AsyncDLightClient:
         def __init__(self, *args, **kwargs): print("WARNING: Using dummy AsyncDLightClient")
         async def _async_send_tcp_command(self, *args, **kwargs): return {"status": "DUMMY_SUCCESS"}
         async def set_light_state(self, *args, **kwargs): pass # Add dummy methods called in tests
         async def set_brightness(self, *args, **kwargs): pass
         async def set_color_temperature(self, *args, **kwargs): pass
         async def query_device_state(self, *args, **kwargs): return {"states": {}}
         async def query_device_info(self, *args, **kwargs): return {}
         async def connect_to_wifi(self, *args, **kwargs): return {}
    async def discover_devices(*args, **kwargs):
        # Minimal dummy implementation for fallback if needed by other tests
        print("WARNING: Using dummy discover_devices")
        await asyncio.sleep(0.01) # Allow loop to run briefly
        return []
    class _DiscoveryProtocol: # Dummy protocol for fallback
        def __init__(self, disc_set, res_list):
            self.results_list = res_list
            self.discovered_devices_set = disc_set
        def datagram_received(self, data, addr):
             # Basic append for dummy testing if needed
             print("WARNING: Dummy protocol received data")
             try:
                 info = json.loads(data.decode('utf-8'))
                 info['ip_address'] = addr[0]
                 if addr[0] not in self.discovered_devices_set:
                     self.results_list.append(info)
                     self.discovered_devices_set.add(addr[0])
             except: pass # Ignore errors in dummy

    # Dummy constants
    FACTORY_RESET_IP = "192.168.4.1"
    DEFAULT_TCP_PORT = 3333
    DEFAULT_UDP_DISCOVERY_PORT = 9478
    DEFAULT_UDP_RESPONSE_PORT = 9487
    BROADCAST_ADDRESS = "255.255.255.255"
    UDP_DISCOVERY_PAYLOAD_HEX = "476f6f676c654e50455f457269635f5761796e65"
    DEFAULT_TIMEOUT = 5.0
    MAX_PAYLOAD_SIZE = 10 * 1024
    STATUS_SUCCESS = "SUCCESS"


# Helper remains the same
def create_mock_response(payload_dict: dict) -> bytes:
    """Encodes a dict into the dLight response format (header + payload)."""
    payload_bytes = json.dumps(payload_dict).encode('utf-8')
    header = struct.pack('>I', len(payload_bytes)) # Big-endian 4-byte length
    return header + payload_bytes

# --- Test Cases ---

# Use standard TestCase for validation tests that don't need an event loop
class TestAsyncDLightClientValidation(unittest.TestCase):
    """Tests input validation for client methods (synchronous checks)."""

    @classmethod
    def setUpClass(cls):
        if not _IMPORT_SUCCESS:
            raise unittest.SkipTest("Skipping Validation tests due to import failure.")

    def setUp(self):
        # Instantiate the real client class from the refactored structure
        self.client = AsyncDLightClient()
        self.target_ip = "192.168.1.100"
        self.device_id = "testdevice1"

    # Patch the internal command sending method within the client module
    @patch(f'{CLIENT_MODULE_PATH}.AsyncDLightClient._async_send_tcp_command', new_callable=AsyncMock)
    def test_set_brightness_valid(self, mock_send_cmd):
        """Test brightness validation."""
        mock_send_cmd.return_value = {"status": STATUS_SUCCESS}
        # Use asyncio.run() as the test method itself is synchronous
        asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 0))
        asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 50))
        asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 100))
        asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 50.5)) # Should cast to int
        # Check the command passed to the (mocked) underlying send method
        call_args, _ = mock_send_cmd.call_args_list[-1]
        command = call_args[1] # command dict is the second arg to _async_send_tcp_command
        self.assertEqual(command['commands'][0]['brightness'], 50) # Asserts int casting

    def test_set_brightness_invalid(self):
        """Test invalid brightness raises ValueError."""
        with self.assertRaisesRegex(ValueError, "Brightness must be between 0 and 100"):
            # Validation happens before await, so no asyncio.run needed here
            asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, -1))
        with self.assertRaisesRegex(ValueError, "Brightness must be between 0 and 100"):
            asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 101))

    # Patch the internal command sending method within the client module
    @patch(f'{CLIENT_MODULE_PATH}.AsyncDLightClient._async_send_tcp_command', new_callable=AsyncMock)
    def test_set_color_temperature_valid(self, mock_send_cmd):
        """Test color temp validation."""
        mock_send_cmd.return_value = {"status": STATUS_SUCCESS}
        asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 2600))
        asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 4500))
        asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 6000))
        asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 4500.7)) # Should cast to int
        call_args, _ = mock_send_cmd.call_args_list[-1]
        command = call_args[1]
        self.assertEqual(command['commands'][0]['color']['temperature'], 4500) # Asserts int casting

    def test_set_color_temperature_invalid(self):
        """Test invalid color temp raises ValueError."""
        with self.assertRaisesRegex(ValueError, "Color temperature must be between 2600 and 6000"):
            asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 2599))
        with self.assertRaisesRegex(ValueError, "Color temperature must be between 2600 and 6000"):
            asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 6001))


# Use IsolatedAsyncioTestCase for tests involving actual awaits on mocked objects
# Patch asyncio.open_connection where it's used: inside the client module
@patch(f'{CLIENT_MODULE_PATH}.asyncio.open_connection', new_callable=AsyncMock)
class TestAsyncDLightClientTCP(unittest.IsolatedAsyncioTestCase):
    """Tests async TCP command sending and response handling, mocking network."""

    @classmethod
    def setUpClass(cls):
        if not _IMPORT_SUCCESS:
            raise unittest.SkipTest("Skipping TCP tests due to import failure.")

    def setUp(self):
        # Instantiate the real client
        self.client = AsyncDLightClient(default_timeout=1.0)
        self.target_ip = "192.168.1.100"
        self.device_id = "testdevice1"

    def _configure_mock_streams(self, mock_open_connection, read_error=None, write_error=None, read_data=None):
        """Helper to configure mock StreamReader and StreamWriter."""
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_open_connection.return_value = (mock_reader, mock_writer)

        # Configure reader behavior
        if read_error:
            mock_reader.readexactly.side_effect = read_error
        elif read_data:
             # Simulate reading header then payload
             if isinstance(read_data, bytes) and len(read_data) >= 4:
                 header = read_data[:4]
                 payload = read_data[4:]
                 mock_reader.readexactly.side_effect = [header, payload, asyncio.IncompleteReadError(b'', None)] # Add error for subsequent calls
             # Handle case where only header is provided (e.g., zero payload test)
             elif isinstance(read_data, bytes) and len(read_data) == 4:
                  mock_reader.readexactly.side_effect = [read_data, asyncio.IncompleteReadError(b'', None)]
             else: # Handle cases where read_data isn't a full response or is an error itself
                 mock_reader.readexactly.side_effect = [read_data, asyncio.IncompleteReadError(b'', None)] if not isinstance(read_data, Exception) else read_data
        else:
            # Default to incomplete read if no data/error specified
            mock_reader.readexactly.side_effect = asyncio.IncompleteReadError(partial=b'', expected=4)

        # Configure writer behavior
        if write_error:
            mock_writer.drain.side_effect = write_error
        mock_writer.wait_closed = AsyncMock() # Ensure awaitable
        mock_writer.is_closing.return_value = False # For finally block check
        # Add get_extra_info mock needed by _async_send_tcp_command logging/closing
        mock_writer.get_extra_info.return_value = (self.target_ip, DEFAULT_TCP_PORT)

        return mock_reader, mock_writer

    # Test methods are async def
    async def test_send_tcp_success(self, mock_open_connection):
        """Test successful async TCP command send and response."""
        cmd_id = "cmd-async-123"
        # Patch the client instance's ID generator method directly
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": STATUS_SUCCESS, "on": True}
            mock_response_bytes = create_mock_response(success_payload)
            mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_data=mock_response_bytes)

            response = await self.client.set_light_state(self.target_ip, self.device_id, True) # Use await

            # Assertions remain similar, checking mocks were called correctly
            mock_open_connection.assert_awaited_once_with(self.target_ip, DEFAULT_TCP_PORT)
            mock_writer.write.assert_called_once()
            sent_data = mock_writer.write.call_args[0][0]
            sent_cmd = json.loads(sent_data.decode('utf-8'))
            self.assertEqual(sent_cmd['commandId'], cmd_id)
            self.assertEqual(sent_cmd['commands'][0]['on'], True)
            mock_writer.drain.assert_awaited_once()

            payload_len = len(json.dumps(success_payload).encode('utf-8'))
            expected_calls = [call(4), call(payload_len)] # Header, Payload
            self.assertEqual(mock_reader.readexactly.await_args_list, expected_calls)

            self.assertEqual(response, success_payload)
            mock_writer.close.assert_called_once()
            mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_query_state(self, mock_open_connection):
        """Test successful query_device_state command."""
        cmd_id = "cmd-async-query"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            query_response_payload = {
                "commandId": cmd_id,
                "deviceId": self.device_id,
                "status": STATUS_SUCCESS,
                "states": {"on": False, "brightness": 50, "color": {"temperature": 4000}}
            }
            mock_response_bytes = create_mock_response(query_response_payload)
            mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_data=mock_response_bytes)

            response = await self.client.query_device_state(self.target_ip, self.device_id)

            mock_open_connection.assert_awaited_once_with(self.target_ip, DEFAULT_TCP_PORT)
            mock_writer.write.assert_called_once()
            sent_data = mock_writer.write.call_args[0][0]
            sent_cmd = json.loads(sent_data.decode('utf-8'))
            self.assertEqual(sent_cmd['commandId'], cmd_id)
            self.assertEqual(sent_cmd['commandType'], "QUERY_DEVICE_STATES")
            mock_writer.drain.assert_awaited_once()

            payload_len = len(json.dumps(query_response_payload).encode('utf-8'))
            expected_calls = [call(4), call(payload_len)] # Header, Payload
            self.assertEqual(mock_reader.readexactly.await_args_list, expected_calls)

            self.assertEqual(response, query_response_payload)
            mock_writer.close.assert_called_once()
            mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_zero_payload_response(self, mock_open_connection):
        """Test handling of a response with zero payload length."""
        cmd_id = "cmd-async-zero"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            # Simulate response with only a header indicating 0 length
            zero_payload_header = struct.pack('>I', 0)
            mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_data=zero_payload_header)

            # Use a command that might plausibly return no payload on success (e.g., set state)
            response = await self.client.set_light_state(self.target_ip, self.device_id, False)

            mock_open_connection.assert_awaited_once_with(self.target_ip, DEFAULT_TCP_PORT)
            mock_writer.write.assert_called_once()
            mock_writer.drain.assert_awaited_once()

            # Only the header should be read
            expected_calls = [call(4)]
            self.assertEqual(mock_reader.readexactly.await_args_list, expected_calls)

            # Check that the client synthesized a success response
            self.assertEqual(response, {"status": STATUS_SUCCESS, "_payload_length": 0})
            mock_writer.close.assert_called_once()
            mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_max_payload_exceeded(self, mock_open_connection):
        """Test error when header indicates payload size exceeds MAX_PAYLOAD_SIZE."""
        cmd_id = "cmd-async-large"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            # Simulate response with a header indicating excessive length
            large_length = MAX_PAYLOAD_SIZE + 1
            large_payload_header = struct.pack('>I', large_length)
            mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_data=large_payload_header)

            with self.assertRaisesRegex(DLightResponseError, f"Payload length {large_length}.*exceeds maximum limit"):
                await self.client.query_device_info(self.target_ip, self.device_id)

            mock_open_connection.assert_awaited_once_with(self.target_ip, DEFAULT_TCP_PORT)
            mock_writer.write.assert_called_once()
            mock_writer.drain.assert_awaited_once()

            # Only the header should be read before error
            expected_calls = [call(4)]
            self.assertEqual(mock_reader.readexactly.await_args_list, expected_calls)

            mock_writer.close.assert_called_once()
            mock_writer.wait_closed.assert_awaited_once()


    async def test_send_tcp_read_payload_incomplete(self, mock_open_connection):
        """Test reading payload resulting in IncompleteReadError."""
        cmd_id = "cmd-async-incomplete"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": STATUS_SUCCESS, "brightness": 55}
            payload_bytes = json.dumps(success_payload).encode('utf-8')
            header = struct.pack('>I', len(payload_bytes))
            chunk1 = payload_bytes[:10] # Partial payload data

            # Simulate header ok, but payload read gets incomplete error
            read_error = asyncio.IncompleteReadError(partial=chunk1, expected=len(payload_bytes))
            mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection)
            # Set side effect: header is read, then the error occurs on payload read
            mock_reader.readexactly.side_effect = [header, read_error]

            with self.assertRaisesRegex(DLightResponseError, "Connection closed unexpectedly while reading payload"):
                await self.client.set_brightness(self.target_ip, self.device_id, 55)

            mock_open_connection.assert_awaited_once_with(self.target_ip, DEFAULT_TCP_PORT)
            mock_writer.write.assert_called_once()
            mock_writer.drain.assert_awaited_once()
            # Check readexactly was called for header (4 bytes) and then for payload
            expected_calls = [call(4), call(len(payload_bytes))]
            self.assertEqual(mock_reader.readexactly.await_args_list, expected_calls)
            mock_writer.close.assert_called_once()
            mock_writer.wait_closed.assert_awaited_once()


    async def test_send_tcp_non_success_status(self, mock_open_connection):
        """Test handling non-SUCCESS status."""
        cmd_id = "cmd-async-fail"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            fail_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "ERROR_DEVICE_BUSY"}
            mock_response_bytes = create_mock_response(fail_payload)
            mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_data=mock_response_bytes)

            with self.assertRaisesRegex(DLightResponseError, "dLight returned non-SUCCESS status: 'ERROR_DEVICE_BUSY'"):
                await self.client.query_device_info(self.target_ip, self.device_id)
            mock_writer.close.assert_called_once()
            mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_connect_timeout(self, mock_open_connection):
        """Test connection timeout using asyncio.TimeoutError."""
        mock_open_connection.side_effect = asyncio.TimeoutError("Connect timed out") # Simulate timeout during open_connection
        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout connecting to {self.target_ip}"):
            await self.client.query_device_state(self.target_ip, self.device_id)
        mock_open_connection.assert_awaited_once()
        # Writer/Reader are not created, so close is not called

    async def test_send_tcp_connect_refused(self, mock_open_connection):
        """Test connection refused error."""
        mock_open_connection.side_effect = ConnectionRefusedError("Connection refused")
        with self.assertRaisesRegex(DLightConnectionError, f"Connection refused by {self.target_ip}"):
            await self.client.query_device_state(self.target_ip, self.device_id)
        mock_open_connection.assert_awaited_once()

    async def test_send_tcp_read_header_timeout(self, mock_open_connection):
        """Test timeout receiving header (via readexactly)."""
        mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection)
        # Simulate timeout *during* the first readexactly call (for the header)
        mock_reader.readexactly.side_effect = asyncio.TimeoutError("Header read timed out")

        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout reading header for command*"):
             await self.client.query_device_info(self.target_ip, self.device_id)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_read_payload_timeout(self, mock_open_connection):
        """Test timeout receiving payload."""
        header = struct.pack('>I', 100) # Expect 100 byte payload
        mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection)
        # Simulate header OK, but timeout on second readexactly (for the payload)
        mock_reader.readexactly.side_effect = [header, asyncio.TimeoutError("Payload read timed out")]

        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout reading payload (100 bytes)*"):
             await self.client.query_device_info(self.target_ip, self.device_id)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_incomplete_header(self, mock_open_connection):
        """Test receiving incomplete header."""
        incomplete_data = b'\x00\x00'
        read_error = asyncio.IncompleteReadError(partial=incomplete_data, expected=4)
        mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection)
        # Set error for first read (header)
        mock_reader.readexactly.side_effect = read_error

        with self.assertRaisesRegex(DLightResponseError, "Connection closed unexpectedly while reading header"):
            await self.client.query_device_state(self.target_ip, self.device_id)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_invalid_payload_json(self, mock_open_connection):
        """Test invalid JSON payload."""
        invalid_payload = b'{"status": "SUCCESS", "on": tru' # Incomplete JSON
        header = struct.pack('>I', len(invalid_payload))
        mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection)
        # Provide header and invalid payload sequentially
        mock_reader.readexactly.side_effect = [header, invalid_payload]

        with self.assertRaisesRegex(DLightResponseError, "Failed to decode JSON payload"):
            await self.client.set_light_state(self.target_ip, self.device_id, True)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()

    async def test_connect_to_wifi_uses_factory_ip(self, mock_open_connection):
        """Verify async connect_to_wifi targets factory IP by default."""
        cmd_id = "cmd-async-wifi"
        # Patch the ID generator on the instance
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": STATUS_SUCCESS}
            mock_response_bytes = create_mock_response(success_payload)
            mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_data=mock_response_bytes)

            await self.client.connect_to_wifi(self.device_id, "MySSID", "MyPassword")

            # Assert connection was attempted to the FACTORY_RESET_IP
            mock_open_connection.assert_awaited_once_with(FACTORY_RESET_IP, DEFAULT_TCP_PORT)
            mock_writer.close.assert_called_once()
            mock_writer.wait_closed.assert_awaited_once()


# Use IsolatedAsyncioTestCase for tests involving actual awaits on mocked objects
# Patch asyncio's loop methods and sleep where they are used: in the discovery module
@patch(f'{DISCOVERY_MODULE_PATH}.asyncio.sleep', new_callable=AsyncMock)
@patch(f'{DISCOVERY_MODULE_PATH}.asyncio.get_running_loop')
class TestAsyncDLightClientUDP(unittest.IsolatedAsyncioTestCase):
    """Tests async UDP Discovery, mocking loop and protocol."""

    @classmethod
    def setUpClass(cls):
        if not _IMPORT_SUCCESS:
            raise unittest.SkipTest("Skipping UDP tests due to import failure.")

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
            listener_protocol = protocol_factory() # Create real protocol for listener
            listener_result = (mock_listen_transport, listener_protocol)

            # Simulate sender creation (second call)
            if send_error and mock_create_endpoint.await_count == 2:
                 print(f"TEST: Simulating sender endpoint error: {send_error}")
                 raise send_error
            sender_result = (mock_send_transport, MagicMock()) # Dummy protocol for sender

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
        self.assertEqual(devices, []) # Expect empty list on timeout
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
        shared_results, shared_set, protocol_instance_holder, \
            mock_listen_transport, mock_send_transport = self._configure_udp_endpoint_mock(
                mock_loop.create_datagram_endpoint
            )

        # Device details to simulate
        device_ip = "192.168.1.101"
        device_id = "asyncdev1"
        response_payload_dict = {"deviceModel": "M1", "deviceId": device_id, "swVersion": "1", "hwVersion": "1"}
        response_bytes = json.dumps(response_payload_dict).encode('utf-8')
        sender_address = (device_ip, 12345) # Source address of simulated response

        # Define the side effect for mock_sleep: Call the captured protocol instance's method
        async def sleep_and_receive(*args, **kwargs):
            proto_instance = protocol_instance_holder[0]
            self.assertIsNotNone(proto_instance, "Protocol instance was not captured by factory")
            # Manually call the protocol's method to simulate receiving data
            proto_instance.datagram_received(response_bytes, sender_address)

        mock_sleep.side_effect = sleep_and_receive # Assign the side effect

        # --- Call the function under test ---
        devices = await discover_devices(discovery_duration=0.1)

        # --- Assertions ---
        # Assert against the list modified by the protocol instance via the side effect
        self.assertEqual(len(shared_results), 1) # Check the list managed by the test
        expected_device_info = response_payload_dict.copy()
        expected_device_info['ip_address'] = device_ip # Check IP was added
        self.assertEqual(shared_results[0], expected_device_info)
        self.assertEqual(shared_set, {device_ip}) # Check set was updated

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

        shared_results, shared_set, protocol_instance_holder, \
            mock_listen_transport, mock_send_transport = self._configure_udp_endpoint_mock(
                mock_loop.create_datagram_endpoint
            )

        # --- Device 1 ---
        dev1_ip = "192.168.1.101"
        dev1_id = "dev1"
        dev1_payload = {"deviceId": dev1_id, "deviceModel": "M1"}
        dev1_bytes = json.dumps(dev1_payload).encode('utf-8')
        dev1_addr = (dev1_ip, 12345)
        # --- Device 2 ---
        dev2_ip = "192.168.1.102"
        dev2_id = "dev2"
        dev2_payload = {"deviceId": dev2_id, "deviceModel": "M2"}
        dev2_bytes = json.dumps(dev2_payload).encode('utf-8')
        dev2_addr = (dev2_ip, 54321)

        # Side effect to simulate receiving two datagrams
        async def sleep_and_receive_multiple(*args, **kwargs):
            proto_instance = protocol_instance_holder[0]
            self.assertIsNotNone(proto_instance)
            proto_instance.datagram_received(dev1_bytes, dev1_addr)
            proto_instance.datagram_received(dev2_bytes, dev2_addr) # Receive second one

        mock_sleep.side_effect = sleep_and_receive_multiple

        await discover_devices(discovery_duration=0.1)

        # Assertions: Check shared list contains both devices
        self.assertEqual(len(shared_results), 2)
        self.assertEqual(shared_set, {dev1_ip, dev2_ip})
        # Check content (order might vary, check presence)
        found_ips = {d['ip_address'] for d in shared_results}
        self.assertEqual(found_ips, {dev1_ip, dev2_ip})
        found_ids = {d['deviceId'] for d in shared_results}
        self.assertEqual(found_ids, {dev1_id, dev2_id})


    async def test_discover_devices_duplicate_response(self, mock_get_loop, mock_sleep):
        """Test async discovery handles duplicate responses from the same IP."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        shared_results, shared_set, protocol_instance_holder, \
            mock_listen_transport, mock_send_transport = self._configure_udp_endpoint_mock(
                mock_loop.create_datagram_endpoint
            )

        # Device details
        device_ip = "192.168.1.105"
        device_id = "dupdev"
        payload_dict = {"deviceId": device_id}
        payload_bytes = json.dumps(payload_dict).encode('utf-8')
        sender_address = (device_ip, 12345)

        # Side effect to simulate receiving the same datagram twice
        async def sleep_and_receive_duplicate(*args, **kwargs):
            proto_instance = protocol_instance_holder[0]
            self.assertIsNotNone(proto_instance)
            proto_instance.datagram_received(payload_bytes, sender_address)
            proto_instance.datagram_received(payload_bytes, sender_address) # Send again

        mock_sleep.side_effect = sleep_and_receive_duplicate

        await discover_devices(discovery_duration=0.1)

        # Assertions: Check shared list contains only one entry
        self.assertEqual(len(shared_results), 1)
        self.assertEqual(shared_set, {device_ip})
        expected_device_info = payload_dict.copy()
        expected_device_info['ip_address'] = device_ip
        self.assertEqual(shared_results[0], expected_device_info)


    async def test_discover_devices_malformed_json(self, mock_get_loop, mock_sleep):
        """Test async discovery handles malformed JSON responses gracefully."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        shared_results, shared_set, protocol_instance_holder, \
            mock_listen_transport, mock_send_transport = self._configure_udp_endpoint_mock(
                mock_loop.create_datagram_endpoint
            )

        # Malformed data
        malformed_bytes = b'{"deviceId": "bad", "model":'
        sender_address = ("192.168.1.200", 12345)

        # Side effect to simulate receiving bad data
        async def sleep_and_receive_bad(*args, **kwargs):
            proto_instance = protocol_instance_holder[0]
            self.assertIsNotNone(proto_instance)
            # Patch logger within discovery module to check warnings
            with patch(f'{DISCOVERY_MODULE_PATH}._LOGGER') as mock_logger:
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
            mock_loop.create_datagram_endpoint,
            listen_error=PermissionError("Permission denied for UDP bind")
        )

        # Patch logger to check error message
        with patch(f'{DISCOVERY_MODULE_PATH}._LOGGER') as mock_logger:
            devices = await discover_devices(discovery_duration=0.1)
            # Assertions
            self.assertEqual(devices, []) # Expect empty list on error
            mock_logger.error.assert_called_once()
            self.assertIn("Permission denied for UDP broadcast or binding", mock_logger.error.call_args[0][0])

        # Check endpoint creation was attempted only once
        self.assertEqual(mock_loop.create_datagram_endpoint.await_count, 1)
        mock_sleep.assert_not_awaited() # Should exit before sleep


    async def test_discover_devices_os_error_bind(self, mock_get_loop, mock_sleep):
        """Test discovery handles OSError (e.g., port in use) during listener bind."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        # Configure endpoint mock to raise OSError on first call (listener)
        self._configure_udp_endpoint_mock(
            mock_loop.create_datagram_endpoint,
            listen_error=OSError("Address already in use")
        )

        # Patch logger to check error message
        with patch(f'{DISCOVERY_MODULE_PATH}._LOGGER') as mock_logger:
            devices = await discover_devices(discovery_duration=0.1)
            # Assertions
            self.assertEqual(devices, []) # Expect empty list on error
            mock_logger.error.assert_called_once()
            self.assertIn("Network error during discovery", mock_logger.error.call_args[0][0])

        # Check endpoint creation was attempted only once
        self.assertEqual(mock_loop.create_datagram_endpoint.await_count, 1)
        mock_sleep.assert_not_awaited() # Should exit before sleep


if __name__ == '__main__':
    # Configure logging for tests if desired
    # logging.basicConfig(level=logging.DEBUG)
    unittest.main()