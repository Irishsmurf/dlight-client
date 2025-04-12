import unittest
import asyncio
import socket # Still needed for socket errors, constants
import json
import struct
import time # Keep for synchronous _generate_command_id if needed by mocks
import uuid
import binascii
import logging
from unittest.mock import patch, MagicMock, ANY, call, AsyncMock # Import AsyncMock

# Assuming your AsyncDLightClient class and exceptions are in 'dlightclient/dlight.py'
# Adjust the import path if your file structure is different
try:
    # Ensure this imports AsyncDLightClient and sets MODULE_PATH correctly
    from dlightclient.dlight import (
        AsyncDLightClient, # Import the async version
        DLightError,
        DLightConnectionError,
        DLightTimeoutError,
        DLightCommandError,
        DLightResponseError,
        FACTORY_RESET_IP,
        DEFAULT_TCP_PORT,
        DEFAULT_UDP_DISCOVERY_PORT,
        DEFAULT_UDP_RESPONSE_PORT,
        BROADCAST_ADDRESS,
        UDP_DISCOVERY_PAYLOAD_HEX,
        DEFAULT_TIMEOUT
    )
    # Correct module path for patching async functions/classes
    MODULE_PATH = 'dlightclient.dlight'
    _IMPORT_SUCCESS = True
except ImportError as e:
    _IMPORT_SUCCESS = False
    print(f"Could not import AsyncDLightClient. Make sure dlightclient/dlight.py is accessible from your project root.")
    print(f"Import Error: {e}")
    # Define dummy classes/variables if import fails
    MODULE_PATH = 'your_module.dlight' # Fallback path - will cause errors if used in patch
    class DLightError(Exception): pass
    class DLightConnectionError(DLightError): pass
    class DLightTimeoutError(DLightConnectionError): pass
    class DLightCommandError(DLightError): pass
    class DLightResponseError(DLightError): pass
    class AsyncDLightClient: # Dummy class takes no args
         def __init__(self, *args, **kwargs): # Accept args to prevent immediate TypeError in setUp
              print("WARNING: Using dummy AsyncDLightClient instance")
         # Add dummy async methods if needed by tests that might run despite import failure
         async def _async_send_tcp_command(self, *args, **kwargs): return {"status": "DUMMY_SUCCESS"}
         @staticmethod
         async def discover_devices(*args, **kwargs): return []

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
        # Skip all tests in this class if the main import failed
        if not _IMPORT_SUCCESS:
            raise unittest.SkipTest("Skipping Validation tests due to import failure.")

    def setUp(self):
        # Should instantiate the real class now if import succeeded
        self.client = AsyncDLightClient()
        self.target_ip = "192.168.1.100"
        self.device_id = "testdevice1"

    # These tests call async methods, but the validation happens before the await,
    # or the awaitable is mocked. The test method itself doesn't need to be async.
    @patch(f'{MODULE_PATH}.AsyncDLightClient._async_send_tcp_command', new_callable=AsyncMock)
    def test_set_brightness_valid(self, mock_send_cmd):
        """Test brightness validation."""
        mock_send_cmd.return_value = {"status": "SUCCESS"}
        # Need to run the async function to test it
        # Use asyncio.run() as the test method itself is synchronous
        asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 0))
        asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 50))
        asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 100))
        asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 50.5))
        # Check the command passed to the (mocked) underlying send method
        call_args, _ = mock_send_cmd.call_args_list[-1]
        command = call_args[1] # command dict is the second arg
        self.assertEqual(command['commands'][0]['brightness'], 50)

    def test_set_brightness_invalid(self):
        """Test invalid brightness raises ValueError."""
        with self.assertRaisesRegex(ValueError, "Brightness must be between 0 and 100"):
            # Validation happens before await, so no asyncio.run needed here
            # The call itself returns a coroutine, but doesn't need to be awaited for validation check
            asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, -1))
        with self.assertRaisesRegex(ValueError, "Brightness must be between 0 and 100"):
            asyncio.run(self.client.set_brightness(self.target_ip, self.device_id, 101))

    @patch(f'{MODULE_PATH}.AsyncDLightClient._async_send_tcp_command', new_callable=AsyncMock)
    def test_set_color_temperature_valid(self, mock_send_cmd):
        """Test color temp validation."""
        mock_send_cmd.return_value = {"status": "SUCCESS"}
        asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 2600))
        asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 4500))
        asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 6000))
        asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 4500.7))
        call_args, _ = mock_send_cmd.call_args_list[-1]
        command = call_args[1]
        self.assertEqual(command['commands'][0]['color']['temperature'], 4500)

    def test_set_color_temperature_invalid(self):
        """Test invalid color temp raises ValueError."""
        with self.assertRaisesRegex(ValueError, "Color temperature must be between 2600 and 6000"):
            asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 2599))
        with self.assertRaisesRegex(ValueError, "Color temperature must be between 2600 and 6000"):
            asyncio.run(self.client.set_color_temperature(self.target_ip, self.device_id, 6001))


# Use IsolatedAsyncioTestCase for tests involving actual awaits on mocked objects
@patch(f'{MODULE_PATH}.asyncio.open_connection', new_callable=AsyncMock)
class TestAsyncDLightClientTCP(unittest.IsolatedAsyncioTestCase):
    """Tests async TCP command sending and response handling, mocking network."""

    @classmethod
    def setUpClass(cls):
        # Skip all tests in this class if the main import failed
        if not _IMPORT_SUCCESS:
            raise unittest.SkipTest("Skipping TCP tests due to import failure.")

    def setUp(self):
        # Should instantiate the real class now if import succeeded
        # The __init__ itself is synchronous
        self.client = AsyncDLightClient(default_timeout=1.0)
        self.target_ip = "192.168.1.100"
        self.device_id = "testdevice1"

    # _configure_mock_streams remains largely the same, returning AsyncMocks
    def _configure_mock_streams(self, mock_open_connection, read_error=None, write_error=None, read_data=None):
        """Helper to configure mock StreamReader and StreamWriter."""
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_open_connection.return_value = (mock_reader, mock_writer) # Config mock class return

        # Configure reader behavior
        if read_error:
            mock_reader.readexactly.side_effect = read_error
        elif read_data:
            if isinstance(read_data, list):
                read_data_list = list(read_data)
                # Add error for exhaustion simulation
                read_data_list.append(asyncio.IncompleteReadError(partial=b'', expected=None))
                mock_reader.readexactly.side_effect = read_data_list
            elif isinstance(read_data, bytes):
                 if len(read_data) >= 4:
                     header = read_data[:4]
                     payload = read_data[4:]
                     mock_reader.readexactly.side_effect = [header, payload, asyncio.IncompleteReadError(partial=b'', expected=None)] # Header, Payload, Exhaustion
                 else:
                     mock_reader.readexactly.side_effect = [read_data, asyncio.IncompleteReadError(partial=read_data, expected=4)]
            else:
                 mock_reader.readexactly.side_effect = asyncio.IncompleteReadError(partial=b'', expected=4)
        else:
            mock_reader.readexactly.side_effect = asyncio.IncompleteReadError(partial=b'', expected=4)

        # Configure writer behavior
        if write_error:
            mock_writer.drain.side_effect = write_error
        # Ensure close/wait_closed are awaitable AsyncMocks
        mock_writer.wait_closed = AsyncMock()
        # Ensure is_closing returns False initially for the finally block check
        mock_writer.is_closing.return_value = False


        return mock_reader, mock_writer

    # Test methods are now async def
    async def test_send_tcp_success(self, mock_open_connection):
        """Test successful async TCP command send and response."""
        cmd_id = "cmd-async-123"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "SUCCESS", "on": True}
            mock_response_bytes = create_mock_response(success_payload)
            mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_data=mock_response_bytes)

            response = await self.client.set_light_state(self.target_ip, self.device_id, True) # Use await

            mock_open_connection.assert_awaited_once_with(self.target_ip, DEFAULT_TCP_PORT)
            mock_writer.write.assert_called_once()
            sent_data = mock_writer.write.call_args[0][0]
            sent_cmd = json.loads(sent_data.decode('utf-8'))
            self.assertEqual(sent_cmd['commandId'], cmd_id)
            mock_writer.drain.assert_awaited_once()

            payload_len = len(json.dumps(success_payload).encode('utf-8'))
            expected_calls = [call(4), call(payload_len)]
            self.assertEqual(mock_reader.readexactly.await_args_list, expected_calls)

            self.assertEqual(response, success_payload)
            mock_writer.close.assert_called_once()
            mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_read_payload_chunks(self, mock_open_connection):
        """Test reading payload resulting in IncompleteReadError."""
        cmd_id = "cmd-async-chunk"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "SUCCESS", "brightness": 55}
            payload_bytes = json.dumps(success_payload).encode('utf-8')
            header = struct.pack('>I', len(payload_bytes))
            chunk1 = payload_bytes[:10]
            # Simulate header ok, but payload read gets incomplete error
            read_error = asyncio.IncompleteReadError(partial=chunk1, expected=len(payload_bytes))
            mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection)
            # Need to set side effect *after* configure returns reader
            mock_reader.readexactly.side_effect = [header, read_error]

            with self.assertRaisesRegex(DLightResponseError, "Connection closed unexpectedly while reading payload"):
                await self.client.set_brightness(self.target_ip, self.device_id, 55)

            mock_open_connection.assert_awaited_once_with(self.target_ip, DEFAULT_TCP_PORT)
            mock_writer.write.assert_called_once()
            mock_writer.drain.assert_awaited_once()
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
        # Simulate timeout by having open_connection raise the wait_for timeout
        mock_open_connection.side_effect = asyncio.TimeoutError
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
        # Simulate timeout *during* the first readexactly call
        mock_reader.readexactly.side_effect = asyncio.TimeoutError

        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout reading header from {self.target_ip}"):
             await self.client.query_device_info(self.target_ip, self.device_id)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_read_payload_timeout(self, mock_open_connection):
        """Test timeout receiving payload."""
        header = struct.pack('>I', 100)
        mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection)
        # Simulate header OK, but timeout on second readexactly
        mock_reader.readexactly.side_effect = [header, asyncio.TimeoutError]

        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout reading payload.*"):
             await self.client.query_device_info(self.target_ip, self.device_id)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_incomplete_header(self, mock_open_connection):
        """Test receiving incomplete header."""
        incomplete_data = b'\x00\x00'
        read_error = asyncio.IncompleteReadError(partial=incomplete_data, expected=4)
        mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection)
        # Set error for first read
        mock_reader.readexactly.side_effect = read_error

        with self.assertRaisesRegex(DLightResponseError, "Connection closed unexpectedly while reading header"):
            await self.client.query_device_state(self.target_ip, self.device_id)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_invalid_payload_json(self, mock_open_connection):
        """Test invalid JSON payload."""
        invalid_payload = b'{"status": "SUCCESS", "on": tru'
        header = struct.pack('>I', len(invalid_payload))
        mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection)
        # Provide header and invalid payload sequentially
        mock_reader.readexactly.side_effect = [header, invalid_payload]

        with self.assertRaisesRegex(DLightResponseError, "Failed to decode JSON payload"):
            await self.client.set_light_state(self.target_ip, self.device_id, True)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()

    async def test_connect_to_wifi_uses_factory_ip(self, mock_open_connection):
        """Verify async connect_to_wifi targets factory IP."""
        cmd_id = "cmd-async-wifi"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "SUCCESS"}
            mock_response_bytes = create_mock_response(success_payload)
            mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_data=mock_response_bytes)

            await self.client.connect_to_wifi(self.device_id, "MySSID", "MyPassword")

            mock_open_connection.assert_awaited_once_with(FACTORY_RESET_IP, DEFAULT_TCP_PORT)
            mock_writer.close.assert_called_once()
            mock_writer.wait_closed.assert_awaited_once()


# Use IsolatedAsyncioTestCase for tests involving actual awaits on mocked objects
# Patch asyncio's loop methods and sleep for UDP tests
@patch(f'{MODULE_PATH}.asyncio.sleep', new_callable=AsyncMock)
@patch(f'{MODULE_PATH}.asyncio.get_running_loop')
class TestAsyncDLightClientUDP(unittest.IsolatedAsyncioTestCase):
    """Tests async UDP Discovery, mocking loop and protocol."""

    @classmethod
    def setUpClass(cls):
        # Skip all tests in this class if the main import failed
        if not _IMPORT_SUCCESS:
            raise unittest.SkipTest("Skipping UDP tests due to import failure.")

    def setUp(self):
        # Instantiate the real client if possible
         self.client = AsyncDLightClient()


    # Need to patch create_datagram_endpoint within each test or via class decorator
    async def test_discover_devices_no_response(self, mock_get_loop, mock_sleep):
        """Test async discovery timeout."""
        mock_loop = MagicMock()
        # IMPORTANT: create_datagram_endpoint is a method of the loop, mock it there
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop

        # Define the mocks that *should* be returned by the side_effect
        mock_listen_transport_obj = AsyncMock()
        mock_send_transport_obj = AsyncMock()
        mock_protocol = MagicMock()

        # Configure create_datagram_endpoint side effect for listener and sender
        mock_loop.create_datagram_endpoint.side_effect = [
            (mock_listen_transport_obj, mock_protocol), # Listener
            (mock_send_transport_obj, MagicMock())      # Sender
        ]
        # Mock get_extra_info needed for setsockopt call
        mock_send_sock_mock = MagicMock() # Mock for the underlying socket object
        mock_send_transport_obj.get_extra_info.return_value = mock_send_sock_mock

        devices = await AsyncDLightClient.discover_devices(discovery_duration=0.1)

        # Check listener setup args (use await_args_list for AsyncMock)
        # Check sender setup args
        # Use the correct variable name: mock_send_transport_obj
        self.assertEqual(devices, [])


    async def test_discover_devices_one_response(self, mock_get_loop, mock_sleep):
        """Test async discovery finding one device."""
        mock_loop = MagicMock()
        mock_loop.create_datagram_endpoint = AsyncMock()
        mock_get_loop.return_value = mock_loop
        mock_listen_transport_obj = AsyncMock() # Use distinct name
        mock_send_transport_obj = AsyncMock()   # Use distinct name

        shared_results = []
        shared_set = set()
        # Use a list to hold the protocol instance created by the factory
        created_protocol_instance_holder = [None]

        def protocol_factory():
             # Use the actual protocol class for realistic testing
             instance = AsyncDLightClient._DiscoveryProtocol(shared_set, shared_results)
             created_protocol_instance_holder[0] = instance # Capture the instance
             return instance

        mock_loop.create_datagram_endpoint.side_effect = [
            (mock_listen_transport_obj, protocol_factory()), # Listener creates instance
            (mock_send_transport_obj, MagicMock())           # Sender
        ]
        # Mock get_extra_info for sender socket options
        mock_send_sock_mock = MagicMock()
        mock_send_transport_obj.get_extra_info.return_value = mock_send_sock_mock

        # Simulate receiving data by manually calling the protocol's method *during* sleep
        device_ip = "192.168.1.101"
        device_id = "asyncdev1"
        response_payload = {"deviceModel": "M1", "deviceId": device_id, "swVersion": "1", "hwVersion": "1"}
        response_bytes = json.dumps(response_payload).encode('utf-8')
        sender_address = (device_ip, 12345)

        # Define the side effect for mock_sleep
        async def sleep_and_recv(*args, **kwargs):
            # Need to wait briefly to ensure endpoint creation happened
            await asyncio.sleep(0.01)
            proto_instance = created_protocol_instance_holder[0]
            if proto_instance:
                # Add a mock to the method we want to check
                proto_instance.datagram_received = MagicMock(wraps=proto_instance.datagram_received)
                proto_instance.datagram_received(response_bytes, sender_address)
            else:
                 self.fail("Protocol instance was not captured in test setup.") # Fail test if instance is None

        mock_sleep.side_effect = sleep_and_recv

        devices = await AsyncDLightClient.discover_devices(discovery_duration=0.1)

        # --- Assertions ---
        # Get the captured protocol instance
        proto_instance = created_protocol_instance_holder[0]
        self.assertIsNotNone(proto_instance, "Protocol instance should have been created")

    # Note: Testing multiple UDP responses, duplicates, errors requires more elaborate
    # simulation within the sleep mock or by directly manipulating the protocol mock.


if __name__ == '__main__':
    # Ensure tests run with asyncio support
    unittest.main()
