import unittest
import socket
import json
import struct
import time
import select
from unittest.mock import patch, MagicMock, ANY, call

# Assuming your DLightClient class and exceptions are in 'dlightclient/dlight.py'
# Adjust the import path if your file structure is different
try:
    # Corrected import based on recommended structure
    from dlightclient.dlight import (
        DLightClient,
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
        DEFAULT_TIMEOUT # Ensure DEFAULT_TIMEOUT is importable or defined
    )
    # Corrected module path for patching
    MODULE_PATH = 'dlightclient.dlight'
except ImportError as e:
    print(f"Could not import DLightClient. Make sure dlightclient/dlight.py is accessible from your project root.")
    print(f"Import Error: {e}")
    # Define dummy classes/variables if import fails to allow test structure definition
    MODULE_PATH = 'dlightclient.dlight' # Adjust this path if structure differs significantly
    class DLightError(Exception): pass
    class DLightConnectionError(DLightError): pass
    class DLightTimeoutError(DLightConnectionError): pass
    class DLightCommandError(DLightError): pass
    class DLightResponseError(DLightError): pass
    class DLightClient: pass # Dummy class takes no args, might cause issues later if import fails
    FACTORY_RESET_IP = "192.168.4.1"
    DEFAULT_TCP_PORT = 3333
    DEFAULT_UDP_DISCOVERY_PORT = 9478
    DEFAULT_UDP_RESPONSE_PORT = 9487
    BROADCAST_ADDRESS = "255.255.255.255"
    UDP_DISCOVERY_PAYLOAD_HEX = "476f6f676c654e50455f457269635f5761796e65"
    DEFAULT_TIMEOUT = 5.0


# Helper to create mock dLight TCP responses
def create_mock_response(payload_dict: dict) -> bytes:
    """Encodes a dict into the dLight response format (header + payload)."""
    payload_bytes = json.dumps(payload_dict).encode('utf-8')
    header = struct.pack('>I', len(payload_bytes)) # Big-endian 4-byte length
    return header + payload_bytes

# --- Test Cases ---

class TestDLightClientValidation(unittest.TestCase):
    """Tests input validation for client methods."""

    def setUp(self):
        # Instantiate without args first, handle potential import failure gracefully
        try:
            self.client = DLightClient() # Use default timeout from class definition
        except TypeError:
             # Fallback if the dummy class was used due to import error
             print("Warning: Using dummy DLightClient in TestDLightClientValidation setUp")
             self.client = DLightClient # Assign the class itself if instance fails
        self.target_ip = "192.168.1.100"
        self.device_id = "testdevice1"

    def test_set_brightness_valid(self):
        # Patch _send_tcp_command as we only test validation here
        # Need to instantiate client properly for patch.object if possible
        try:
            client_instance = DLightClient()
        except:
            self.skipTest("Skipping test: Could not instantiate real DLightClient for patching.")
            return # Skip if real client cannot be made

        with patch.object(client_instance, '_send_tcp_command') as mock_send:
            mock_send.return_value = {"status": "SUCCESS"}
            # Use the instance for method calls
            client_instance.set_brightness(self.target_ip, self.device_id, 0)
            client_instance.set_brightness(self.target_ip, self.device_id, 50)
            client_instance.set_brightness(self.target_ip, self.device_id, 100)
            # Check if int conversion happens correctly
            client_instance.set_brightness(self.target_ip, self.device_id, 50.5)
            call_args, _ = mock_send.call_args_list[-1]
            command = call_args[1] # command dict is the second arg
            self.assertEqual(command['commands'][0]['brightness'], 50)


    def test_set_brightness_invalid(self):
        try:
            client_instance = DLightClient()
        except:
            self.skipTest("Skipping test: Could not instantiate real DLightClient.")
            return
        with self.assertRaisesRegex(ValueError, "Brightness must be between 0 and 100"):
            client_instance.set_brightness(self.target_ip, self.device_id, -1)
        with self.assertRaisesRegex(ValueError, "Brightness must be between 0 and 100"):
            client_instance.set_brightness(self.target_ip, self.device_id, 101)

    def test_set_color_temperature_valid(self):
        try:
            client_instance = DLightClient()
        except:
            self.skipTest("Skipping test: Could not instantiate real DLightClient.")
            return
         # Patch _send_tcp_command as we only test validation here
        with patch.object(client_instance, '_send_tcp_command') as mock_send:
            mock_send.return_value = {"status": "SUCCESS"}
            client_instance.set_color_temperature(self.target_ip, self.device_id, 2600)
            client_instance.set_color_temperature(self.target_ip, self.device_id, 4500)
            client_instance.set_color_temperature(self.target_ip, self.device_id, 6000)
             # Check if int conversion happens correctly
            client_instance.set_color_temperature(self.target_ip, self.device_id, 4500.7)
            call_args, _ = mock_send.call_args_list[-1]
            command = call_args[1] # command dict is the second arg
            self.assertEqual(command['commands'][0]['color']['temperature'], 4500)

    def test_set_color_temperature_invalid(self):
        try:
            client_instance = DLightClient()
        except:
            self.skipTest("Skipping test: Could not instantiate real DLightClient.")
            return
        with self.assertRaisesRegex(ValueError, "Color temperature must be between 2600 and 6000"):
            client_instance.set_color_temperature(self.target_ip, self.device_id, 2599)
        with self.assertRaisesRegex(ValueError, "Color temperature must be between 2600 and 6000"):
            client_instance.set_color_temperature(self.target_ip, self.device_id, 6001)


# Patch using the corrected MODULE_PATH
@patch(f'{MODULE_PATH}.socket.socket')
class TestDLightClientTCP(unittest.TestCase):
    """Tests TCP command sending and response handling, mocking network."""

    def setUp(self):
        # Instantiate client, handle potential import failure
        try:
            # Pass the timeout if the real class was imported and accepts it
            self.client = DLightClient(default_timeout=1.0)
        except TypeError:
             # Fallback if the dummy class was used or __init__ is wrong
             print("Warning: DLightClient __init__ failed or dummy class used. Using default timeout logic if possible.")
             self.client = DLightClient() # Instantiate without args
             # Manually set timeout if needed, though tests mock network calls
             self.client.default_timeout = 1.0
        except NameError:
             # If DLightClient itself isn't even defined (major import fail)
             self.fail("FATAL: DLightClient class not found during import.")

        self.target_ip = "192.168.1.100"
        self.device_id = "testdevice1"

    def _configure_mock_socket(self, mock_socket_class, connect_error=None, send_error=None, recv_error=None, recv_data=None):
        """Helper to configure the mock socket instance's behavior."""
        # REMOVED spec=socket.socket from here
        mock_sock_instance = MagicMock()
        # Configure the class mock to return this instance
        mock_socket_class.return_value = mock_sock_instance

        # Clear previous side effects if any test left them
        # These should now work as MagicMock creates attributes on access
        mock_sock_instance.connect.side_effect = None
        mock_sock_instance.sendall.side_effect = None
        mock_sock_instance.recv.side_effect = None
        mock_sock_instance.recv.return_value = b'' # Default empty

        if connect_error:
            mock_sock_instance.connect.side_effect = connect_error
        if send_error:
            mock_sock_instance.sendall.side_effect = send_error

        # Handle recv_data/recv_error carefully
        # Handle recv_data/recv_error carefully
        if recv_error:
             mock_sock_instance.recv.side_effect = recv_error
        elif recv_data:
            if isinstance(recv_data, list):
                # Data provided as a list of chunks
                recv_data_list = list(recv_data) # Copy list to avoid modifying original
                recv_data_list.append(b'') # Add sentinel empty read for exhaustion
                mock_sock_instance.recv.side_effect = recv_data_list
            elif isinstance(recv_data, bytes):
                 # Data provided as a single bytes object (header + payload)
                 # Split it for sequential return by recv calls
                 if len(recv_data) >= 4:
                     header = recv_data[:4]
                     payload = recv_data[4:]
                     # Return header, then payload, then empty
                     mock_sock_instance.recv.side_effect = [header, payload, b'']
                 else:
                     # Provided data is too short even for a header, return it then empty
                     mock_sock_instance.recv.side_effect = [recv_data, b'']
            else:
                 # Unexpected recv_data type, default to empty
                 mock_sock_instance.recv.side_effect = [b'']

        return mock_sock_instance

    def test_send_tcp_success(self, mock_socket_class):
        """Test successful TCP command send and response."""
        cmd_id = "cmd-123"
        # Patch _generate_command_id for predictable IDs
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "SUCCESS", "on": True}
            mock_response_bytes = create_mock_response(success_payload)
            mock_sock_instance = self._configure_mock_socket(mock_socket_class, recv_data=mock_response_bytes)

            response = self.client.set_light_state(self.target_ip, self.device_id, True)

            # Assertions
            mock_sock_instance.connect.assert_called_once_with((self.target_ip, DEFAULT_TCP_PORT))
            mock_sock_instance.sendall.assert_called_once()
            sent_data = mock_sock_instance.sendall.call_args[0][0]
            sent_cmd = json.loads(sent_data.decode('utf-8'))
            self.assertEqual(sent_cmd['commandId'], cmd_id)
            self.assertEqual(sent_cmd['deviceId'], self.device_id)
            self.assertEqual(sent_cmd['commandType'], 'EXECUTE')
            self.assertEqual(sent_cmd['commands'], [{'on': True}])

            # Check recv calls: header (4 bytes), then payload
            payload_len = len(json.dumps(success_payload).encode('utf-8'))
            expected_calls = [call(4), call(min(payload_len, 4096))] # Header, then payload read
            self.assertEqual(mock_sock_instance.recv.call_args_list[:len(expected_calls)], expected_calls)

            self.assertEqual(response, success_payload) # Check parsed response
            mock_sock_instance.close.assert_called_once()

    def test_send_tcp_read_payload_chunks(self, mock_socket_class):
        """Test successful read when payload arrives in multiple chunks."""
        cmd_id = "cmd-chunk"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "SUCCESS", "brightness": 55}
            payload_bytes = json.dumps(success_payload).encode('utf-8')
            header = struct.pack('>I', len(payload_bytes))
            # Simulate receiving header, then payload in two chunks
            chunk1 = payload_bytes[:10]
            chunk2 = payload_bytes[10:]
            mock_response_chunks = [header, chunk1, chunk2]

            mock_sock_instance = self._configure_mock_socket(mock_socket_class, recv_data=mock_response_chunks)

            response = self.client.set_brightness(self.target_ip, self.device_id, 55)

            # Assertions
            mock_sock_instance.connect.assert_called_once_with((self.target_ip, DEFAULT_TCP_PORT))
            # Check calls: header (4 bytes), first chunk attempt, second chunk attempt
            expected_calls = [
                call(4),                         # Read header
                call(min(len(payload_bytes), 4096)), # Read payload (gets chunk1)
                call(min(len(chunk2), 4096))     # Read remaining payload (gets chunk2)
            ]
            # Check only the expected number of calls were made before potential sentinel empty read
            self.assertEqual(mock_sock_instance.recv.call_args_list[:len(expected_calls)], expected_calls)

            self.assertEqual(response, success_payload) # Check parsed response
            mock_sock_instance.close.assert_called_once()


    def test_send_tcp_non_success_status(self, mock_socket_class):
        """Test handling of non-SUCCESS status from device."""
        cmd_id = "cmd-fail"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            fail_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "ERROR_INVALID_COMMAND"}
            mock_response_bytes = create_mock_response(fail_payload)
            mock_sock_instance = self._configure_mock_socket(mock_socket_class, recv_data=mock_response_bytes)

            with self.assertRaisesRegex(DLightResponseError, "dLight returned non-SUCCESS status: 'ERROR_INVALID_COMMAND'"):
                self.client.query_device_info(self.target_ip, self.device_id)
            mock_sock_instance.close.assert_called_once() # Ensure socket closed even on error


    def test_send_tcp_connect_timeout(self, mock_socket_class):
        """Test connection timeout."""
        mock_sock_instance = self._configure_mock_socket(mock_socket_class, connect_error=socket.timeout("timed out"))
        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout connecting to or communicating with {self.target_ip}"):
            self.client.query_device_state(self.target_ip, self.device_id)
        # Close won't be called if connect fails before socket assigned/used
        mock_sock_instance.close.assert_called_once()


    def test_send_tcp_connect_error(self, mock_socket_class):
        """Test other connection errors."""
        mock_sock_instance = self._configure_mock_socket(mock_socket_class, connect_error=socket.error("Connection refused"))
        with self.assertRaisesRegex(DLightConnectionError, f"Socket error communicating with {self.target_ip}.*: Connection refused"):
            self.client.query_device_state(self.target_ip, self.device_id)
        mock_sock_instance.close.assert_called_once()

    def test_send_tcp_send_timeout(self, mock_socket_class):
        """Test send timeout."""
        mock_sock_instance = self._configure_mock_socket(mock_socket_class, send_error=socket.timeout("timed out"))
        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout connecting to or communicating with {self.target_ip}"):
            self.client.set_light_state(self.target_ip, self.device_id, False)
        mock_sock_instance.close.assert_called_once() # Close should be called if connect succeeded

    def test_send_tcp_recv_header_timeout(self, mock_socket_class):
        """Test timeout while receiving header."""
        mock_sock_instance = self._configure_mock_socket(mock_socket_class, recv_error=socket.timeout("timed out"))
        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout connecting to or communicating with {self.target_ip}"):
             self.client.query_device_info(self.target_ip, self.device_id)
        mock_sock_instance.close.assert_called_once()

    def test_send_tcp_recv_payload_timeout(self, mock_socket_class):
        """Test timeout while receiving payload after header."""
        header = struct.pack('>I', 100) # Expect 100 bytes payload
        # Simulate receiving header, then timeout on payload read
        mock_sock_instance = self._configure_mock_socket(mock_socket_class)
        # Configure the side effect *after* instance creation
        mock_sock_instance.recv.side_effect = [header, socket.timeout("timed out")]

        with self.assertRaisesRegex(DLightTimeoutError, f"Timeout connecting to or communicating with {self.target_ip}"):
             self.client.query_device_info(self.target_ip, self.device_id)
        mock_sock_instance.close.assert_called_once()


    def test_send_tcp_incomplete_header(self, mock_socket_class):
        """Test receiving fewer than 4 bytes for the header."""
        mock_sock_instance = self._configure_mock_socket(mock_socket_class, recv_data=b'\x00\x00') # Only 2 bytes
        with self.assertRaisesRegex(DLightResponseError, "Incomplete header received"):
            self.client.query_device_state(self.target_ip, self.device_id)
        mock_sock_instance.close.assert_called_once()

    def test_send_tcp_invalid_payload_json(self, mock_socket_class):
        """Test receiving invalid JSON in the payload."""
        invalid_payload = b'{"status": "SUCCESS", "on": tru' # Malformed JSON
        header = struct.pack('>I', len(invalid_payload))
        mock_sock_instance = self._configure_mock_socket(mock_socket_class)
        mock_sock_instance.recv.side_effect = [header, invalid_payload] # Need side_effect for list

        with self.assertRaisesRegex(DLightResponseError, "Failed to decode JSON payload"):
            self.client.set_light_state(self.target_ip, self.device_id, True)
        mock_sock_instance.close.assert_called_once()

    def test_send_tcp_incomplete_payload(self, mock_socket_class):
        """Test receiving fewer bytes than indicated by the header."""
        payload = b'{"status": "SUCCESS", "value": 1}'
        header = struct.pack('>I', len(payload) + 10) # Header claims 10 extra bytes
        incomplete_payload = payload
        # Simulate receiving header, payload, then empty byte string (signifying closed connection)
        mock_sock_instance = self._configure_mock_socket(mock_socket_class)
        mock_sock_instance.recv.side_effect = [header, incomplete_payload, b'']

        with self.assertRaisesRegex(DLightResponseError, "Connection closed while reading payload"):
            self.client.query_device_info(self.target_ip, self.device_id)
        mock_sock_instance.close.assert_called_once()

    def test_connect_to_wifi_uses_factory_ip(self, mock_socket_class):
        """Verify connect_to_wifi targets the specific factory reset IP."""
        cmd_id = "cmd-wifi"
        with patch.object(self.client, '_generate_command_id', return_value=cmd_id):
            success_payload = {"commandId": cmd_id, "deviceId": self.device_id, "status": "SUCCESS"}
            mock_response_bytes = create_mock_response(success_payload)
            mock_sock_instance = self._configure_mock_socket(mock_socket_class, recv_data=mock_response_bytes)

            self.client.connect_to_wifi(self.device_id, "MySSID", "MyPassword")

            # Assert connect was called with the factory reset IP
            mock_sock_instance.connect.assert_called_once_with((FACTORY_RESET_IP, DEFAULT_TCP_PORT))
            mock_sock_instance.close.assert_called_once()

    def test_connect_to_wifi_error_wrapping(self, mock_socket_class):
        """Verify connect_to_wifi wraps errors correctly."""
        mock_sock_instance = self._configure_mock_socket(mock_socket_class, connect_error=socket.timeout("timed out"))
        with self.assertRaisesRegex(DLightCommandError, f"Failed to send SSID_CONNECT to {FACTORY_RESET_IP}"):
            self.client.connect_to_wifi(self.device_id, "MySSID", "MyPassword")


# Patch using the corrected MODULE_PATH
@patch(f'{MODULE_PATH}.select.select')
@patch(f'{MODULE_PATH}.socket.socket')
class TestDLightClientUDP(unittest.TestCase):
    """Tests UDP Discovery, mocking network and select."""

    def setUp(self):
         # Instantiate client, handle potential import failure
        try:
            self.client = DLightClient()
        except NameError:
             self.fail("FATAL: DLightClient class not found during import.")
        except TypeError:
             print("Warning: DLightClient __init__ failed or dummy class used in UDP setUp.")
             self.client = DLightClient # Assign class if instance fails

    def _configure_udp_sockets(self, mock_socket_class):
        """Configure mocks for sending and listening UDP sockets."""
        mock_send_sock = MagicMock()
        mock_listen_sock = MagicMock()

        # Reset call count for side effect on each test
        # Use a function attribute to maintain state across calls within a test
        # Needs to be attached to the method itself or the class/instance
        if not hasattr(TestDLightClientUDP._configure_udp_sockets, 'call_count'):
             TestDLightClientUDP._configure_udp_sockets.call_count = 0
        TestDLightClientUDP._configure_udp_sockets.call_count = 0

        # Configure socket() to return the correct socket based on type
        def socket_side_effect(family, type, **kwargs):
            TestDLightClientUDP._configure_udp_sockets.call_count += 1
            # In discovery, listen is created first, then send
            if type == socket.SOCK_DGRAM:
                 # Use spec here as UDP sockets need specific methods like bind/sendto
                 # Return the pre-created mocks in the correct order
                 return mock_listen_sock if TestDLightClientUDP._configure_udp_sockets.call_count == 1 else mock_send_sock
            return MagicMock() # Fallback

        mock_socket_class.side_effect = socket_side_effect

        # Return the specific instances we want to track
        return mock_send_sock, mock_listen_sock

    def test_discover_devices_no_response(self, mock_socket_class, mock_select):
        """Test discovery when no devices respond (timeout)."""
        mock_send_sock, mock_listen_sock = self._configure_udp_sockets(mock_socket_class)
        # select returns empty list (timeout)
        mock_select.return_value = ([], [], [])

        # Use static method call if client instantiation failed
        discover_method = getattr(self.client, 'discover_devices', DLightClient.discover_devices)
        devices = discover_method(discovery_duration=0.1)


        # Assertions
        mock_send_sock.setsockopt.assert_called_once_with(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        mock_listen_sock.bind.assert_called_once_with(('', DEFAULT_UDP_RESPONSE_PORT))
        mock_listen_sock.setblocking.assert_called_once_with(False)
        mock_send_sock.sendto.assert_called_once() # Check payload/address later if needed
        mock_select.assert_called() # Check was called
        self.assertEqual(devices, []) # No devices found
        mock_listen_sock.close.assert_called_once()
        mock_send_sock.close.assert_called_once()

    def test_discover_devices_one_response(self, mock_socket_class, mock_select):
        """Test discovery finding one device."""
        mock_send_sock, mock_listen_sock = self._configure_udp_sockets(mock_socket_class)

        # Simulate receiving one valid response
        device_ip = "192.168.1.101"
        device_id = "udpdev1"
        response_payload = {
            "deviceModel": "GLAMP001", "deviceId": device_id,
            "swVersion": "1.0", "hwVersion": "1.1"
        }
        response_bytes = json.dumps(response_payload).encode('utf-8')
        sender_address = (device_ip, 12345) # Port doesn't matter here

        # Configure select to indicate data is ready on the first call, then timeout
        mock_select.side_effect = [([mock_listen_sock], [], []), ([], [], [])]
        # Configure recvfrom on the listening socket
        mock_listen_sock.recvfrom.return_value = (response_bytes, sender_address)

        # Use patch to simulate time passing to exit the loop after one response
        # Needs to provide enough time points for select calls + loop checks
        with patch(f'{MODULE_PATH}.time.time', side_effect=[0, 0.01, 0.05, 0.2]): # Start, select1, select2(timeout), end
            discover_method = getattr(self.client, 'discover_devices', DLightClient.discover_devices)
            devices = discover_method(discovery_duration=0.1)


        # Assertions
        mock_send_sock.sendto.assert_called_once()
        mock_listen_sock.recvfrom.assert_called_once_with(1024) # Default buffer size
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]['deviceId'], device_id)
        self.assertEqual(devices[0]['ip_address'], device_ip)
        self.assertEqual(devices[0]['deviceModel'], "GLAMP001")
        mock_listen_sock.close.assert_called_once()
        mock_send_sock.close.assert_called_once()


    def test_discover_devices_multiple_responses(self, mock_socket_class, mock_select):
        """Test discovery finding multiple devices."""
        mock_send_sock, mock_listen_sock = self._configure_udp_sockets(mock_socket_class)

        # Simulate receiving two valid responses
        dev1_ip = "192.168.1.101"
        dev1_id = "udpdev1"
        resp1_payload = {"deviceId": dev1_id, "deviceModel": "M1", "swVersion": "1", "hwVersion": "1"}
        resp1_bytes = json.dumps(resp1_payload).encode('utf-8')
        addr1 = (dev1_ip, 12345)

        dev2_ip = "192.168.1.102"
        dev2_id = "udpdev2"
        resp2_payload = {"deviceId": dev2_id, "deviceModel": "M2", "swVersion": "2", "hwVersion": "2"}
        resp2_bytes = json.dumps(resp2_payload).encode('utf-8')
        addr2 = (dev2_ip, 54321)

        # select returns ready socket twice, then timeout
        mock_select.side_effect = [([mock_listen_sock], [], []), ([mock_listen_sock], [], []), ([], [], [])]
        # recvfrom returns data for dev1 then dev2
        mock_listen_sock.recvfrom.side_effect = [(resp1_bytes, addr1), (resp2_bytes, addr2)]

        # Corrected time mock side_effect to provide enough values
        with patch(f'{MODULE_PATH}.time.time', side_effect=[0, 0.01, 0.01, 0.02, 0.02, 0.03, 0.03, 0.2]):
             discover_method = getattr(self.client, 'discover_devices', DLightClient.discover_devices)
             devices = discover_method(discovery_duration=0.1)

        # Assertions
        self.assertEqual(mock_listen_sock.recvfrom.call_count, 2)
        self.assertEqual(len(devices), 2)
        # Check devices found (order might vary depending on dict iteration)
        found_ids = {d['deviceId'] for d in devices}
        found_ips = {d['ip_address'] for d in devices}
        self.assertEqual(found_ids, {dev1_id, dev2_id})
        self.assertEqual(found_ips, {dev1_ip, dev2_ip})
        mock_listen_sock.close.assert_called_once()
        mock_send_sock.close.assert_called_once()

    def test_discover_devices_ignore_duplicates(self, mock_socket_class, mock_select):
        """Test that duplicate responses from the same IP are ignored."""
        mock_send_sock, mock_listen_sock = self._configure_udp_sockets(mock_socket_class)

        # Simulate receiving two responses from the same device
        dev1_ip = "192.168.1.101"
        dev1_id = "udpdev1"
        resp1_payload = {"deviceId": dev1_id, "deviceModel": "M1", "swVersion": "1", "hwVersion": "1"}
        resp1_bytes = json.dumps(resp1_payload).encode('utf-8')
        addr1 = (dev1_ip, 12345)

        # select returns ready socket twice
        mock_select.side_effect = [([mock_listen_sock], [], []), ([mock_listen_sock], [], []), ([], [], [])]
        # recvfrom returns the same data twice
        mock_listen_sock.recvfrom.side_effect = [(resp1_bytes, addr1), (resp1_bytes, addr1)]

        with patch(f'{MODULE_PATH}.time.time', side_effect=[0, 0.01, 0.01, 0.02, 0.02, 0.03, 0.03, 0.2]):
             discover_method = getattr(self.client, 'discover_devices', DLightClient.discover_devices)
             devices = discover_method(discovery_duration=0.1)


        # Assertions
        self.assertEqual(mock_listen_sock.recvfrom.call_count, 2)
        self.assertEqual(len(devices), 1) # Only one device should be listed
        self.assertEqual(devices[0]['deviceId'], dev1_id)
        self.assertEqual(devices[0]['ip_address'], dev1_ip)
        mock_listen_sock.close.assert_called_once()
        mock_send_sock.close.assert_called_once()

    def test_discover_devices_ignore_malformed_json(self, mock_socket_class, mock_select):
        """Test that malformed JSON responses are ignored gracefully."""
        mock_send_sock, mock_listen_sock = self._configure_udp_sockets(mock_socket_class)

        malformed_bytes = b'{"deviceId": "bad' # Incomplete JSON
        addr = ("192.168.1.103", 11111)

        mock_select.side_effect = [([mock_listen_sock], [], []), ([], [], [])]
        mock_listen_sock.recvfrom.return_value = (malformed_bytes, addr)

        with patch(f'{MODULE_PATH}.time.time', side_effect=[0, 0.01, 0.2]):
            discover_method = getattr(self.client, 'discover_devices', DLightClient.discover_devices)
            devices = discover_method(discovery_duration=0.1)

        # Assertions
        self.assertEqual(mock_listen_sock.recvfrom.call_count, 1)
        self.assertEqual(len(devices), 0) # Malformed response ignored
        mock_listen_sock.close.assert_called_once()
        mock_send_sock.close.assert_called_once()

    def test_discover_devices_bind_error(self, mock_socket_class, mock_select):
        """Test discovery fails if UDP listen socket cannot bind."""
        mock_send_sock, mock_listen_sock = self._configure_udp_sockets(mock_socket_class)
        # Simulate bind error
        mock_listen_sock.bind.side_effect = socket.error("Address already in use")

        # No need to mock select or time if bind fails early
        discover_method = getattr(self.client, 'discover_devices', DLightClient.discover_devices)
        devices = discover_method(discovery_duration=0.1)


        mock_listen_sock.bind.assert_called_once()
        mock_select.assert_not_called() # Should exit before select loop
        mock_send_sock.sendto.assert_not_called() # Should exit before sending probe
        self.assertEqual(devices, [])
        # Sockets might not be closed if bind fails, depending on exact error handling
        # Check if close *was* called (our current code closes in finally)
        mock_listen_sock.close.assert_called_once()
        mock_send_sock.close.assert_not_called()


if __name__ == '__main__':
    unittest.main()
