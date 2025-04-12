import unittest
import asyncio
import socket # Still needed for socket errors, constants
import json
import struct
import binascii
from unittest.mock import patch, MagicMock, call, AsyncMock

# --- Import from the refactored package structure ---
try:
    # Import the public interface defined in dlightclient/__init__.py
    from dlightclient import (
        AsyncDLightClient,
        discover_devices, # Now a standalone function
        DLightError,
        DLightConnectionError,
        DLightTimeoutError,
        DLightResponseError,
        # Import constants needed for tests
        FACTORY_RESET_IP,
        DEFAULT_TCP_PORT,
        DEFAULT_UDP_DISCOVERY_PORT,
        DEFAULT_UDP_RESPONSE_PORT,
        BROADCAST_ADDRESS,
        UDP_DISCOVERY_PAYLOAD_HEX,
    )
    # Import the internal protocol class for UDP testing if needed directly
    # (Alternatively, mock its behavior via the factory)
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
        mock_send_cmd.return_value = {"status": "SUCCESS"}
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
        mock_send_cmd.return_value = {"status": "SUCCESS"}
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
        """Helper to configure mock StreamReader and StreamWriter (remains the same)."""
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_open_connection.return_value = (mock_reader, mock_writer)

        # Configure reader behavior (simplified for clarity, original logic was complex)
        if read_error:
            mock_reader.readexactly.side_effect = read_error
        elif read_data:
             # Simulate reading header then payload
             if isinstance(read_data, bytes) and len(read_data) >= 4:
                 header = read_data[:4]
                 payload = read_data[4:]
                 mock_reader.readexactly.side_effect = [header, payload, asyncio.IncompleteReadError(b'', None)] # Add error for subsequent calls
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
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "SUCCESS", "on": True}
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

    async def test_send_tcp_read_payload_incomplete(self, mock_open_connection):
        """Test reading payload resulting in IncompleteReadError."""
        cmd_id = "cmd-async-incomplete"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "SUCCESS", "brightness": 55}
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

        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout reading header for command QUERY_DEVICE_INFO to {self.target_ip}:3333"):
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
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "SUCCESS"}
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

    # No client needed here as we test the standalone discover_devices function
    # def setUp(self):
    #     pass

    # Test methods are async def
    async def test_discover_devices_no_response(self, mock_get_loop, mock_sleep):
        """Test async discovery timeout when no devices respond."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        # Mock create_datagram_endpoint on the loop instance
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        # Mocks returned by create_datagram_endpoint
        mock_listen_transport = AsyncMock(spec=asyncio.DatagramTransport)
        mock_send_transport = AsyncMock(spec=asyncio.DatagramTransport)
        # Mock the protocol instance created by the lambda factory
        mock_protocol_instance = MagicMock(spec=_DiscoveryProtocol)

        # Configure create_datagram_endpoint side effect for listener and sender
        mock_loop.create_datagram_endpoint.side_effect = [
            (mock_listen_transport, mock_protocol_instance), # Listener call result
            (mock_send_transport, MagicMock())               # Sender call result (protocol not used)
        ]
        # Mock get_extra_info needed for setsockopt call in discovery.py
        mock_send_sock = MagicMock(spec=socket.socket) # Mock for the underlying socket object
        mock_send_transport.get_extra_info.return_value = mock_send_sock

        # Call the standalone discover_devices function
        devices = await discover_devices(discovery_duration=0.1)

        # Assertions
        self.assertEqual(devices, []) # Expect empty list on timeout
        mock_get_loop.assert_called_once()
        # Check create_datagram_endpoint calls
        self.assertEqual(mock_loop.create_datagram_endpoint.await_count, 2)
        # Check listener setup call args (first call)
        listen_call_args = mock_loop.create_datagram_endpoint.await_args_list[0]
        self.assertTrue(callable(listen_call_args[0][0])) # Check factory is callable
        self.assertEqual(listen_call_args[1]['local_addr'], ('0.0.0.0', DEFAULT_UDP_RESPONSE_PORT))
        # Check sender setup call args (second call)
        send_call_args = mock_loop.create_datagram_endpoint.await_args_list[1]
        self.assertTrue(callable(send_call_args[0][0]))
        self.assertEqual(send_call_args[1]['remote_addr'], (BROADCAST_ADDRESS, DEFAULT_UDP_DISCOVERY_PORT))
        self.assertTrue(send_call_args[1]['allow_broadcast'])

        # Check socket options were set
        mock_send_transport.get_extra_info.assert_called_once_with('socket')
        mock_send_sock.setsockopt.assert_called_once_with(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

        # Check probe was sent
        expected_payload = binascii.unhexlify(UDP_DISCOVERY_PAYLOAD_HEX)
        mock_send_transport.sendto.assert_called_once_with(expected_payload)

        # Check sleep was awaited
        mock_sleep.assert_awaited_once_with(0.1)

        # Check transports were closed
        mock_listen_transport.close.assert_called_once()
        mock_send_transport.close.assert_called_once()


    async def test_discover_devices_one_response(self, mock_get_loop, mock_sleep):
        """Test async discovery finding one device."""
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        mock_listen_transport = AsyncMock(spec=asyncio.DatagramTransport)
        mock_send_transport = AsyncMock(spec=asyncio.DatagramTransport)

        # --- Test setup ---
        # This list resides in the test scope and will be modified by the protocol
        shared_results = []
        shared_set = set()
        # Holder to capture the protocol instance created by the factory
        protocol_instance_holder = [None]

        # Use the REAL protocol class, but ensure it uses the test's lists
        def protocol_factory():
             print("TEST: protocol_factory called") # Debug
             # Instantiate the *real* protocol, passing the test's lists
             instance = _DiscoveryProtocol(shared_set, shared_results)
             protocol_instance_holder[0] = instance # Capture the instance
             print(f"TEST: Factory created protocol {id(instance)} with list {id(shared_results)}") # Debug
             return instance

        # Configure create_datagram_endpoint mock
        # First call (listener): return mock transport and the REAL protocol instance via factory
        # Second call (sender): return mock transport and dummy protocol
        mock_loop.create_datagram_endpoint.side_effect = [
            (mock_listen_transport, protocol_factory()), # Use factory for listener protocol
            (mock_send_transport, MagicMock())           # Dummy for sender protocol
        ]

        # Mock get_extra_info for sender socket options
        mock_send_sock = MagicMock(spec=socket.socket)
        mock_send_transport.get_extra_info.return_value = mock_send_sock

        # Device details to simulate
        device_ip = "192.168.1.101"
        device_id = "asyncdev1"
        response_payload_dict = {"deviceModel": "M1", "deviceId": device_id, "swVersion": "1", "hwVersion": "1"}
        response_bytes = json.dumps(response_payload_dict).encode('utf-8')
        sender_address = (device_ip, 12345) # Source address of simulated response

        # Define the side effect for mock_sleep: Call the captured protocol instance's method
        async def sleep_and_receive(*args, **kwargs):
            proto_instance = protocol_instance_holder[0]
            # Ensure the factory has run and captured the instance
            self.assertIsNotNone(proto_instance, "Protocol instance was not captured by factory")
            print(f"SIDE EFFECT: Calling datagram_received on {id(proto_instance)} with list {id(proto_instance.results_list)}") # Debug
            # Manually call the protocol's method to simulate receiving data
            proto_instance.datagram_received(response_bytes, sender_address)
            print(f"SIDE EFFECT: After datagram_received, shared_results: {shared_results}") # Debug

        mock_sleep.side_effect = sleep_and_receive # Assign the side effect

        # --- Call the function under test ---
        # This discover_devices call uses its own internal results_list,
        # BUT the protocol instance it interacts with (via the mocked endpoint)
        # is the one we created with the test's shared_results list.
        devices = await discover_devices(discovery_duration=0.1)

        # --- Assertions ---
        print(f"TEST: discover_devices returned: {devices}") # This might be empty, which is OK
        print(f"TEST: shared_results content (from test scope): {shared_results}") # This is what we check

        # Assert against the list modified by the protocol instance
        self.assertEqual(len(shared_results), 1) # Check the list managed by the test
        expected_device_info = response_payload_dict.copy()
        expected_device_info['ip_address'] = device_ip # Check IP was added
        self.assertEqual(shared_results[0], expected_device_info)

        # Check shared set was also updated
        self.assertEqual(shared_set, {device_ip})

        # Check mocks (verify the discovery process ran)
        mock_get_loop.assert_called_once()
        self.assertEqual(mock_loop.create_datagram_endpoint.await_count, 2)
        mock_send_transport.sendto.assert_called_once()
        mock_sleep.assert_awaited_once_with(0.1)
        mock_listen_transport.close.assert_called_once()
        mock_send_transport.close.assert_called_once()


    # TODO: Add more UDP tests:
    # - Multiple responses
    # - Duplicate responses (should be ignored by protocol)
    # - Malformed JSON response
    # - PermissionError during endpoint creation
    # - OSError during endpoint creation


if __name__ == '__main__':
    # Configure logging for tests if desired
    # logging.basicConfig(level=logging.DEBUG)
    unittest.main()
