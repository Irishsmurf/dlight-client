import socket
import json
import time
import struct
import uuid
import select
import binascii
from typing import List, Dict, Any, Optional, Tuple, Union

# --- Constants ---
DEFAULT_TCP_PORT = 3333
DEFAULT_UDP_DISCOVERY_PORT = 9478
DEFAULT_UDP_RESPONSE_PORT = 9487
UDP_DISCOVERY_PAYLOAD_HEX = "476f6f676c654e50455f457269635f5761796e65"
DEFAULT_TIMEOUT = 5.0  # seconds
BROADCAST_ADDRESS = "255.255.255.255"
FACTORY_RESET_IP = "192.168.4.1"
MAX_PAYLOAD_SIZE = 10 * 1024 # 10 KB sanity limit

# --- Custom Exceptions ---
class DLightError(Exception):
    """Base exception for dlightclient errors."""
    pass

class DLightConnectionError(DLightError):
    """Error connecting to the dLight device."""
    pass

class DLightTimeoutError(DLightConnectionError):
    """Timeout during communication with the dLight device."""
    pass

class DLightCommandError(DLightError):
    """Error related to command formatting or execution."""
    pass

class DLightResponseError(DLightError):
    """Error parsing or interpreting the response from the dLight device."""
    pass


class DLightClient:
    """
    A client for interacting with dLight devices over the local network.

    Provides methods for discovering devices, querying status, and controlling
    the light's state (on/off, brightness, color temperature).

    Remember the confidential nature of the dLight API as per original docs.
    """

    def __init__(self, default_timeout: float = DEFAULT_TIMEOUT):
        """
        Initializes the DLightClient.

        Args:
            default_timeout: Default network operation timeout in seconds.
        """
        self.default_timeout = default_timeout

    def _generate_command_id(self) -> str:
        """Generates a unique command ID."""
        # Using timestamp + part of uuid for simplicity and uniqueness likelihood
        return f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

    def _send_tcp_command(self, target_ip: str, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends a command via TCP and receives the response.

        Handles the 4-byte length prefix header in the response.

        Args:
            target_ip: The IP address of the dLight device.
            command: The command dictionary to send (will be JSON serialized).

        Returns:
            The JSON response payload as a dictionary.

        Raises:
            DLightTimeoutError: If the connection or read/write times out.
            DLightConnectionError: If any other socket error occurs.
            DLightCommandError: If the command cannot be serialized.
            DLightResponseError: If the response header/payload is invalid,
                                 or the device returns a non-SUCCESS status.
        """
        sock = None
        try:
            # Create and connect the socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(self.default_timeout)
            sock.connect((target_ip, DEFAULT_TCP_PORT))

            # Serialize command to JSON bytes
            try:
                json_data = json.dumps(command).encode('utf-8')
            except TypeError as e:
                raise DLightCommandError(f"Failed to serialize command to JSON: {e}") from e

            # Send the command
            sock.sendall(json_data)

            # --- Read the response ---
            # 1. Read the 4-byte header (payload length)
            header = sock.recv(4)
            if len(header) < 4:
                raise DLightResponseError(f"Incomplete header received (got {len(header)} bytes, expected 4)")

            # 2. Decode the header (Big Endian unsigned integer)
            try:
                payload_length = struct.unpack('>I', header)[0]
            except struct.error as e:
                 raise DLightResponseError(f"Failed to unpack header bytes: {e}") from e

            if payload_length == 0:
                raise DLightResponseError("Received zero payload length in header")
            if payload_length > MAX_PAYLOAD_SIZE:
                 raise DLightResponseError(f"Payload length {payload_length} exceeds maximum limit {MAX_PAYLOAD_SIZE}")

            # 3. Read the JSON payload
            payload_bytes = b""
            bytes_remaining = payload_length
            while bytes_remaining > 0:
                chunk = sock.recv(min(bytes_remaining, 4096)) # Read in chunks
                if not chunk:
                    raise DLightResponseError(f"Connection closed while reading payload (read {len(payload_bytes)}/{payload_length} bytes)")
                payload_bytes += chunk
                bytes_remaining -= len(chunk)

            # 4. Deserialize the JSON payload
            try:
                response = json.loads(payload_bytes.decode('utf-8'))
            except json.JSONDecodeError as e:
                raise DLightResponseError(f"Failed to decode JSON payload: {e}\nRaw Payload: {payload_bytes!r}") from e
            except UnicodeDecodeError as e:
                 raise DLightResponseError(f"Failed to decode payload as UTF-8: {e}\nRaw Payload: {payload_bytes!r}") from e

            # 5. Check status
            status = response.get("status")
            if status != "SUCCESS":
                raise DLightResponseError(f"dLight returned non-SUCCESS status: '{status}'. Full response: {response}")

            return response

        except socket.timeout:
            raise DLightTimeoutError(f"Timeout connecting to or communicating with {target_ip}:{DEFAULT_TCP_PORT}") from None
        except socket.error as e:
            raise DLightConnectionError(f"Socket error communicating with {target_ip}:{DEFAULT_TCP_PORT}: {e}") from e
        finally:
            if sock:
                sock.close()

    # --- Public API Methods ---

    def set_light_state(self, target_ip: str, device_id: str, on: bool) -> Dict[str, Any]:
        """
        Turns the dLight on or off.

        Args:
            target_ip: IP address of the dLight.
            device_id: Unique device ID of the dLight.
            on: True to turn on, False to turn off.

        Returns:
            The response dictionary from the device.
        """
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": "EXECUTE",
            "commands": [{"on": bool(on)}] # Ensure it's a proper boolean
        }
        return self._send_tcp_command(target_ip, command)

    def set_brightness(self, target_ip: str, device_id: str, brightness: int) -> Dict[str, Any]:
        """
        Sets the brightness of the dLight.

        Args:
            target_ip: IP address of the dLight.
            device_id: Unique device ID of the dLight.
            brightness: Brightness percentage (0-100). 0 turns the light off.

        Returns:
            The response dictionary from the device.

        Raises:
            ValueError: If brightness is outside the 0-100 range.
        """
        if not 0 <= brightness <= 100:
            raise ValueError("Brightness must be between 0 and 100")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": "EXECUTE",
            "commands": [{"brightness": int(brightness)}]
        }
        return self._send_tcp_command(target_ip, command)

    def set_color_temperature(self, target_ip: str, device_id: str, temperature: int) -> Dict[str, Any]:
        """
        Sets the color temperature of the dLight.

        Args:
            target_ip: IP address of the dLight.
            device_id: Unique device ID of the dLight.
            temperature: Color temperature in Kelvin (2600-6000).

        Returns:
            The response dictionary from the device.

        Raises:
            ValueError: If temperature is outside the 2600-6000 range.
        """
        if not 2600 <= temperature <= 6000:
            raise ValueError("Color temperature must be between 2600 and 6000 Kelvin")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": "EXECUTE",
            "commands": [{"color": {"temperature": int(temperature)}}]
        }
        return self._send_tcp_command(target_ip, command)

    def query_device_state(self, target_ip: str, device_id: str) -> Dict[str, Any]:
        """
        Queries the current state (on/off, brightness, color) of the dLight.

        Args:
            target_ip: IP address of the dLight.
            device_id: Unique device ID of the dLight.

        Returns:
            The response dictionary containing the device state under the 'states' key.
        """
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": "QUERY_DEVICE_STATES",
            "commands": [] # Empty for query
        }
        return self._send_tcp_command(target_ip, command)

    def query_device_info(self, target_ip: str, device_id: str) -> Dict[str, Any]:
        """
        Queries the device information (versions, model) of the dLight.

        Args:
            target_ip: IP address of the dLight.
            device_id: Unique device ID of the dLight.

        Returns:
            The response dictionary containing the device info.
        """
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": "QUERY_DEVICE_INFO",
            "commands": [] # Empty for query
        }
        return self._send_tcp_command(target_ip, command)

    def connect_to_wifi(self, device_id: str, ssid: str, password: str) -> Dict[str, Any]:
        """
        Sends the SSID_CONNECT command for direct Wi-Fi provisioning.

        IMPORTANT: This should only be sent to the dLight when it's in its
        initial SoftAP mode (IP address 192.168.4.1). Sends credentials
        in clear text. Use with caution.

        Args:
            device_id: Unique device ID of the dLight (often found in SoftAP SSID).
            ssid: The SSID (name) of the Wi-Fi network to connect to.
            password: The password for the Wi-Fi network.

        Returns:
            The response dictionary from the device.
        """
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": "SSID_CONNECT", # Matches example in docs
            "ssid": ssid,
            "password": password
        }
        # This command specifically targets the factory reset IP
        try:
             return self._send_tcp_command(FACTORY_RESET_IP, command)
        except DLightError as e:
             # Add context for this specific operation
             raise DLightCommandError(f"Failed to send SSID_CONNECT to {FACTORY_RESET_IP}: {e}") from e


    @staticmethod
    def discover_devices(discovery_duration: float = 3.0,
                         response_port: int = DEFAULT_UDP_RESPONSE_PORT,
                         discovery_port: int = DEFAULT_UDP_DISCOVERY_PORT,
                         broadcast_address: str = BROADCAST_ADDRESS) -> List[Dict[str, Any]]:
        """
        Discovers dLight devices on the network using UDP broadcast.

        Args:
            discovery_duration: How long to listen for responses (in seconds).
            response_port: The local UDP port to listen on for responses.
            discovery_port: The UDP port dLights listen on for discovery probes.
            broadcast_address: The broadcast address to send the probe to.

        Returns:
            A list of dictionaries, each representing a discovered device
            including its 'ip_address'. Returns an empty list if none found.
        """
        discovered_devices = {} # Use dict to avoid duplicates based on IP
        listen_sock = None
        send_sock = None

        try:
            # Decode the hex payload
            try:
                probe_payload = binascii.unhexlify(UDP_DISCOVERY_PAYLOAD_HEX)
            except binascii.Error as e:
                 # This should not happen with a fixed hex string
                 print(f"[Error] Failed to decode internal discovery payload: {e}")
                 return []

            # Setup listening socket
            listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                 # Bind to all interfaces on the specified response port
                 listen_sock.bind(('', response_port))
            except socket.error as e:
                 print(f"[Error] Could not bind UDP listening socket to port {response_port}: {e}. Check if port is in use.")
                 return []
            listen_sock.setblocking(False) # Use select for non-blocking reads

            # Setup sending socket
            send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            send_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            print(f"Broadcasting dLight discovery probe to {broadcast_address}:{discovery_port}...")
            print(f"Listening for responses on port {response_port} for {discovery_duration} seconds...")

            # Send the broadcast probe
            try:
                send_sock.sendto(probe_payload, (broadcast_address, discovery_port))
            except socket.error as e:
                 print(f"[Error] Failed to send UDP broadcast: {e}. Check network permissions.")
                 return [] # Cannot proceed without sending probe

            # Listen for responses using select
            end_time = time.time() + discovery_duration
            while time.time() < end_time:
                # Calculate remaining time for select timeout
                remaining_time = max(0, end_time - time.time())
                readable, _, _ = select.select([listen_sock], [], [], remaining_time)

                if not readable:
                    continue # Timeout for this select call, continue loop if time remains

                # Socket has data
                try:
                    data, addr = listen_sock.recvfrom(1024) # Buffer size
                    ip_address = addr[0]

                    if ip_address in discovered_devices:
                        continue # Already found this one

                    print(f"Received response from {ip_address}")
                    try:
                        device_info = json.loads(data.decode('utf-8'))
                        device_info['ip_address'] = ip_address # Add IP to the info
                        discovered_devices[ip_address] = device_info
                        print(f"  -> Discovered: {device_info}")
                    except (json.JSONDecodeError, UnicodeDecodeError) as e:
                        print(f"  -> Error decoding response from {ip_address}: {e}")

                except socket.error as e:
                    # Errors during recvfrom might occur, log and continue
                    print(f"[Warning] Socket error receiving UDP data: {e}")
                    time.sleep(0.1) # Avoid busy-looping on error

        except Exception as e:
             # Catch broader exceptions during setup/loop
             print(f"[Error] An unexpected error occurred during discovery: {e}")
        finally:
            if listen_sock:
                listen_sock.close()
            if send_sock:
                send_sock.close()

        print(f"Discovery finished. Found {len(discovered_devices)} device(s).")
        return list(discovered_devices.values())


# --- Example Usage ---
if __name__ == "__main__":
    print("--- dLight Python Client Example ---")
    client = DLightClient()

    print("\n--- Discovering Devices (3 seconds) ---")
    try:
        devices = DLightClient.discover_devices(discovery_duration=3.0)
    except Exception as e:
         print(f"Discovery failed with an unexpected error: {e}")
         devices = []

    if not devices:
        print("\nNo dLight devices found on the network.")
        print("Ensure dLight is powered on and connected to the same network.")
        print("If setting up for the first time, you might need to use")
        print("`client.connect_to_wifi(...)` while connected to its SoftAP.")
        # Example placeholder for Wi-Fi connect (DO NOT RUN UNLESS NEEDED):
        # try:
        #     print("\nAttempting Wi-Fi connection (Example - REPLACE details)...")
        #     # You need the device ID from the SoftAP SSID (e.g., GLAMP_<DEVICE_ID>)
        #     wifi_resp = client.connect_to_wifi("YOUR_DEVICE_ID", "Your_WiFi_SSID", "Your_WiFi_Password")
        #     print(f"Wi-Fi connect response: {wifi_resp}")
        #     print("Wait for device to connect and try discovery again.")
        # except DLightError as e:
        #     print(f"Wi-Fi connect failed: {e}")
    else:
        # --- Interact with the first discovered device ---
        target_device = devices[0]
        target_ip = target_device['ip_address']
        device_id = target_device['deviceId'] # Case sensitive based on discovery response
        print(f"\n--- Interacting with: {device_id} at {target_ip} ---")

        try:
            # Query Info
            print("\nQuerying Device Info...")
            info = client.query_device_info(target_ip, device_id)
            print(f"  Info: {info}")

            # Query State
            print("\nQuerying Device State...")
            state_resp = client.query_device_state(target_ip, device_id)
            current_state = state_resp.get('states', {})
            print(f"  Current State: {current_state}")

            # Turn On
            print("\nTurning Light ON...")
            on_resp = client.set_light_state(target_ip, device_id, True)
            print(f"  Response: {on_resp}")
            time.sleep(0.5) # Give device time to react

            # Set Brightness
            print("\nSetting Brightness to 60%...")
            bright_resp = client.set_brightness(target_ip, device_id, 60)
            print(f"  Response: {bright_resp}")
            time.sleep(0.5)

            # Set Color Temperature
            print("\nSetting Color Temperature to 4500K...")
            temp_resp = client.set_color_temperature(target_ip, device_id, 4500)
            print(f"  Response: {temp_resp}")
            time.sleep(0.5)

            # Query State Again
            print("\nQuerying Device State Again...")
            state_resp = client.query_device_state(target_ip, device_id)
            current_state = state_resp.get('states', {})
            print(f"  New State: {current_state}")

            # Turn Off
            print("\nTurning Light OFF...")
            off_resp = client.set_light_state(target_ip, device_id, False)
            print(f"  Response: {off_resp}")

        except DLightError as e:
            print(f"\n--- An error occurred during interaction ---")
            print(e)
        except ValueError as e:
             print(f"\n--- Invalid value provided ---")
             print(e)

    print("\n--- Example Finished ---")
