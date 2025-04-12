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
    # Corrected module path for patching async functions/classes
    MODULE_PATH = 'dlightclient.dlight'
except ImportError as e:
    print(f"Could not import AsyncDLightClient. Make sure dlightclient/dlight.py is accessible from your project root.")
    print(f"Import Error: {e}")
    # Define dummy classes/variables if import fails
    MODULE_PATH = 'your_module.dlight' # Adjust this path
    class DLightError(Exception): pass
    class DLightConnectionError(DLightError): pass
    class DLightTimeoutError(DLightConnectionError): pass
    class DLightCommandError(DLightError): pass
    class DLightResponseError(DLightError): pass
    class AsyncDLightClient: pass # Dummy class
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

# Validation tests remain synchronous as they don't involve async calls directly
class TestAsyncDLightClientValidation(unittest.TestCase):
    """Tests input validation for client methods (synchronous checks)."""

    def setUp(self):
        try:
            self.client = AsyncDLightClient()
        except Exception as e:
             self.fail(f"FATAL: Could not instantiate AsyncDLightClient. Error: {e}")
        self.target_ip = "192.168.1.100"
        self.device_id = "testdevice1"

    @patch(f'{MODULE_PATH}.AsyncDLightClient._async_send_tcp_command', new_callable=AsyncMock)
    async def test_set_brightness_valid(self, mock_send_cmd):
        """Test brightness validation (using async method)."""
        mock_send_cmd.return_value = {"status": "SUCCESS"}
        await self.client.set_brightness(self.target_ip, self.device_id, 0)
        await self.client.set_brightness(self.target_ip, self.device_id, 50)
        await self.client.set_brightness(self.target_ip, self.device_id, 100)
        await self.client.set_brightness(self.target_ip, self.device_id, 50.5)
        # Check the command passed to the (mocked) underlying send method
        call_args, _ = mock_send_cmd.call_args_list[-1]
        command = call_args[1] # command dict is the second arg
        self.assertEqual(command['commands'][0]['brightness'], 50)

    async def test_set_brightness_invalid(self):
        """Test invalid brightness raises ValueError."""
        # No network call needed, so test remains simple
        with self.assertRaisesRegex(ValueError, "Brightness must be between 0 and 100"):
            # Call is now async, but validation happens before await
            await self.client.set_brightness(self.target_ip, self.device_id, -1)
        with self.assertRaisesRegex(ValueError, "Brightness must be between 0 and 100"):
            await self.client.set_brightness(self.target_ip, self.device_id, 101)

    @patch(f'{MODULE_PATH}.AsyncDLightClient._async_send_tcp_command', new_callable=AsyncMock)
    async def test_set_color_temperature_valid(self, mock_send_cmd):
        """Test color temp validation (using async method)."""
        mock_send_cmd.return_value = {"status": "SUCCESS"}
        await self.client.set_color_temperature(self.target_ip, self.device_id, 2600)
        await self.client.set_color_temperature(self.target_ip, self.device_id, 4500)
        await self.client.set_color_temperature(self.target_ip, self.device_id, 6000)
        await self.client.set_color_temperature(self.target_ip, self.device_id, 4500.7)
        call_args, _ = mock_send_cmd.call_args_list[-1]
        command = call_args[1]
        self.assertEqual(command['commands'][0]['color']['temperature'], 4500)

    async def test_set_color_temperature_invalid(self):
        """Test invalid color temp raises ValueError."""
        with self.assertRaisesRegex(ValueError, "Color temperature must be between 2600 and 6000"):
            await self.client.set_color_temperature(self.target_ip, self.device_id, 2599)
        with self.assertRaisesRegex(ValueError, "Color temperature must be between 2600 and 6000"):
            await self.client.set_color_temperature(self.target_ip, self.device_id, 6001)


# Patch asyncio's open_connection for TCP tests
@patch(f'{MODULE_PATH}.asyncio.open_connection', new_callable=AsyncMock)
class TestAsyncDLightClientTCP(unittest.IsolatedAsyncioTestCase): # Use IsolatedAsyncioTestCase
    """Tests async TCP command sending and response handling, mocking network."""

    def setUp(self):
        try:
            self.client = AsyncDLightClient(default_timeout=1.0)
        except Exception as e:
             self.fail(f"FATAL: Could not instantiate AsyncDLightClient. Error: {e}")
        self.target_ip = "192.168.1.100"
        self.device_id = "testdevice1"

    def _configure_mock_streams(self, mock_open_connection, read_error=None, write_error=None, read_data=None):
        """Helper to configure mock StreamReader and StreamWriter."""
        mock_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_writer = AsyncMock(spec=asyncio.StreamWriter)

        # Configure open_connection to return these mocks
        mock_open_connection.return_value = (mock_reader, mock_writer)

        # Configure reader behavior
        if read_error:
            mock_reader.readexactly.side_effect = read_error
        elif read_data:
            if isinstance(read_data, list):
                # Simulate sequential reads, end with IncompleteReadError or empty bytes
                read_data_list = list(read_data)
                # Add error for exhaustion simulation if needed, or just let it raise default
                # read_data_list.append(asyncio.IncompleteReadError(partial=b'', expected=None))
                mock_reader.readexactly.side_effect = read_data_list
            elif isinstance(read_data, bytes):
                 # Single full response provided (header + payload)
                 if len(read_data) >= 4:
                     header = read_data[:4]
                     payload = read_data[4:]
                     # Return header, then payload
                     mock_reader.readexactly.side_effect = [header, payload]
                 else:
                     # Data too short for header
                     mock_reader.readexactly.side_effect = [read_data, asyncio.IncompleteReadError(partial=read_data, expected=4)]
            else:
                 mock_reader.readexactly.side_effect = asyncio.IncompleteReadError(partial=b'', expected=4) # Default error
        else:
            # Default: simulate immediate EOF or incomplete read
            mock_reader.readexactly.side_effect = asyncio.IncompleteReadError(partial=b'', expected=4)

        # Configure writer behavior (only drain and close really matter for errors)
        if write_error:
            mock_writer.drain.side_effect = write_error # Simulate error on drain
            # Or simulate error on write itself if needed: mock_writer.write.side_effect = write_error

        # Ensure close/wait_closed are awaitable
        mock_writer.wait_closed = AsyncMock()

        return mock_reader, mock_writer


    async def test_send_tcp_success(self, mock_open_connection):
        """Test successful async TCP command send and response."""
        cmd_id = "cmd-async-123"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "SUCCESS", "on": True}
            mock_response_bytes = create_mock_response(success_payload)
            mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_data=mock_response_bytes)

            # Call the async method
            response = await self.client.set_light_state(self.target_ip, self.device_id, True)

            # Assertions
            mock_open_connection.assert_awaited_once_with(self.target_ip, DEFAULT_TCP_PORT)
            mock_writer.write.assert_called_once()
            sent_data = mock_writer.write.call_args[0][0]
            sent_cmd = json.loads(sent_data.decode('utf-8'))
            self.assertEqual(sent_cmd['commandId'], cmd_id)
            # ... check other command parts ...
            mock_writer.drain.assert_awaited_once()

            # Check readexactly calls
            payload_len = len(json.dumps(success_payload).encode('utf-8'))
            expected_calls = [call(4), call(payload_len)] # Header, then payload
            self.assertEqual(mock_reader.readexactly.await_args_list, expected_calls)

            self.assertEqual(response, success_payload)
            mock_writer.close.assert_called_once()
            mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_read_payload_chunks(self, mock_open_connection):
        """Test reading payload in chunks (less direct simulation with readexactly)."""
        # Note: readexactly simplifies this, but we can test IncompleteReadError
        cmd_id = "cmd-async-chunk"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "SUCCESS", "brightness": 55}
            payload_bytes = json.dumps(success_payload).encode('utf-8')
            header = struct.pack('>I', len(payload_bytes))
            chunk1 = payload_bytes[:10]
            # Simulate header ok, but payload read gets incomplete error
            read_error = asyncio.IncompleteReadError(partial=chunk1, expected=len(payload_bytes))
            mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_data=[header, read_error])
            # Need to set side effect *after* configure returns reader
            mock_reader.readexactly.side_effect = [header, read_error]

            with self.assertRaisesRegex(DLightResponseError, "Connection closed unexpectedly while reading"):
                await self.client.set_brightness(self.target_ip, self.device_id, 55)

            # Assertions
            mock_open_connection.assert_awaited_once_with(self.target_ip, DEFAULT_TCP_PORT)
            mock_writer.write.assert_called_once()
            mock_writer.drain.assert_awaited_once()
            # Check readexactly calls: header, then attempt payload read
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
        mock_open_connection.side_effect = asyncio.TimeoutError # Simulate timeout during open_connection
        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout communicating with {self.target_ip}"):
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
        # Simulate timeout *during* the first readexactly call
        mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_error=asyncio.TimeoutError)
        # Must set side_effect after mock creation
        mock_reader.readexactly.side_effect = asyncio.TimeoutError

        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout communicating with {self.target_ip}"):
             await self.client.query_device_info(self.target_ip, self.device_id)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_read_payload_timeout(self, mock_open_connection):
        """Test timeout receiving payload."""
        header = struct.pack('>I', 100)
        # Simulate header OK, but timeout on second readexactly
        mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection)
        mock_reader.readexactly.side_effect = [header, asyncio.TimeoutError]

        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout communicating with {self.target_ip}"):
             await self.client.query_device_info(self.target_ip, self.device_id)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_incomplete_header(self, mock_open_connection):
        """Test receiving incomplete header."""
        incomplete_data = b'\x00\x00'
        read_error = asyncio.IncompleteReadError(partial=incomplete_data, expected=4)
        mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_error=read_error)
        mock_reader.readexactly.side_effect = read_error # Set error for first read

        with self.assertRaisesRegex(DLightResponseError, "Connection closed unexpectedly while reading"):
            await self.client.query_device_state(self.target_ip, self.device_id)
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_awaited_once()

    async def test_send_tcp_invalid_payload_json(self, mock_open_connection):
        """Test invalid JSON payload."""
        invalid_payload = b'{"status": "SUCCESS", "on": tru'
        header = struct.pack('>I', len(invalid_payload))
        mock_reader, mock_writer = self._configure_mock_streams(mock_open_connection, read_data=[header, invalid_payload])
        # Need side effect for list
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


# Patch asyncio's loop methods for UDP tests
@patch(f'{MODULE_PATH}.asyncio.get_running_loop')
class TestAsyncDLightClientUDP(unittest.IsolatedAsyncioTestCase):
    """Tests async UDP Discovery, mocking loop and protocol."""

    def setUp(self):
        try:
            self.client = AsyncDLightClient()
        except Exception as e:
             self.fail(f"FATAL: Could not instantiate AsyncDLightClient. Error: {e}")

    # Mock the loop and its create_datagram_endpoint method
    async def test_discover_devices_no_response(self, mock_get_loop):
        """Test async discovery timeout."""
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop
        mock_transport = AsyncMock()
        mock_protocol = MagicMock()
        # Configure create_datagram_endpoint to return mock transport/protocol
        # Need two calls: one for listener, one for sender
        mock_loop.create_datagram_endpoint.side_effect = [(mock_transport, mock_protocol), (AsyncMock(), MagicMock())]

        # Patch asyncio.sleep
        with patch(f'{MODULE_PATH}.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            devices = await AsyncDLightClient.discover_devices(discovery_duration=0.1)

            mock_loop.create_datagram_endpoint.assert_called()
            self.assertEqual(mock_loop.create_datagram_endpoint.call_count, 2)
            # Check listener setup args
            listener_call_args = mock_loop.create_datagram_endpoint.call_args_list[0]
            self.assertEqual(listener_call_args[1]['local_addr'], ('0.0.0.0', DEFAULT_UDP_RESPONSE_PORT))
            # Check sender setup args
            sender_call_args = mock_loop.create_datagram_endpoint.call_args_list[1]
            self.assertEqual(sender_call_args[1]['remote_addr'], (BROADCAST_ADDRESS, DEFAULT_UDP_DISCOVERY_PORT))

            # Check broadcast enabling attempt (might warn if socket unavailable in mock)
            mock_send_transport = mock_loop.create_datagram_endpoint.side_effect[1][0]
            mock_send_transport.get_extra_info.assert_called_with('socket')

            # Check probe send
            mock_send_transport.sendto.assert_called_once()

            mock_sleep.assert_awaited_once_with(0.1) # Check sleep duration
            self.assertEqual(devices, [])
            mock_transport.close.assert_called_once()
            mock_send_transport.close.assert_called_once()


    async def test_discover_devices_one_response(self, mock_get_loop):
        """Test async discovery finding one device."""
        mock_loop = MagicMock()
        mock_get_loop.return_value = mock_loop
        mock_listen_transport = AsyncMock()
        mock_send_transport = AsyncMock()
        # This is tricky: we need the *protocol instance* created by the lambda
        # We can capture the factory and call it manually, or mock the protocol directly
        shared_results = []
        shared_set = set()
        protocol_factory = lambda: AsyncDLightClient._DiscoveryProtocol(shared_set, shared_results)

        mock_loop.create_datagram_endpoint.side_effect = [
            (mock_listen_transport, protocol_factory()), # Call factory to get instance for listener
            (mock_send_transport, MagicMock()) # Sender
        ]

        # Simulate receiving data by manually calling the protocol's method
        device_ip = "192.168.1.101"
        device_id = "asyncdev1"
        response_payload = {
            "deviceModel": "GLAMP001", "deviceId": device_id,
            "swVersion": "1.0", "hwVersion": "1.1"
        }
        response_bytes = json.dumps(response_payload).encode('utf-8')
        sender_address = (device_ip, 12345)

        # Patch sleep and run discovery
        with patch(f'{MODULE_PATH}.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            # Define side effect *after* endpoint mock is configured
            async def sleep_and_simulate_recv(*args, **kwargs):
                # Simulate receiving data *during* the sleep period
                # Get the protocol instance created by the first call's side_effect
                proto_instance = mock_loop.create_datagram_endpoint.side_effect[0][1]
                proto_instance.datagram_received(response_bytes, sender_address)
                await asyncio.sleep(0.01) # Actual small sleep if needed by test timing

            mock_sleep.side_effect = sleep_and_simulate_recv

            devices = await AsyncDLightClient.discover_devices(discovery_duration=0.1)

            mock_sleep.assert_awaited_once_with(0.1)
            self.assertEqual(len(devices), 1)
            self.assertEqual(devices[0]['deviceId'], device_id)
            self.assertEqual(devices[0]['ip_address'], device_ip)
            mock_listen_transport.close.assert_called_once()
            mock_send_transport.close.assert_called_once()

    # Add more UDP tests: multiple responses, duplicates, errors - requires more complex protocol simulation


if __name__ == '__main__':
    # Running async tests requires the unittest runner to support it
    # or using a runner like pytest with pytest-asyncio
    unittest.main() # Standard runner works from Python 3.8+
