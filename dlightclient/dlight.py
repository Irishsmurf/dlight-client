import asyncio
import socket # Still needed for socket errors, constants
import json
import struct
import time
import uuid
import binascii
import logging
from typing import List, Dict, Any, Optional, Tuple, Union, Set

# --- Constants ---
DEFAULT_TCP_PORT = 3333
DEFAULT_UDP_DISCOVERY_PORT = 9478
DEFAULT_UDP_RESPONSE_PORT = 9487
UDP_DISCOVERY_PAYLOAD_HEX = "476f6f676c654e50455f457269635f5761796e65"
DEFAULT_TIMEOUT = 5.0  # seconds
BROADCAST_ADDRESS = "255.255.255.255" # Use specific broadcast if known, else default
FACTORY_RESET_IP = "192.168.4.1"
MAX_PAYLOAD_SIZE = 10 * 1024 # 10 KB sanity limit

_LOGGER = logging.getLogger(__name__)

# --- Custom Exceptions (can remain the same) ---
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


class AsyncDLightClient:
    """
    An asynchronous client for interacting with dLight devices using asyncio.

    Provides async methods for discovering devices, querying status, and
    controlling the light's state (on/off, brightness, color temperature).

    Remember the confidential nature of the dLight API as per original docs.
    """

    def __init__(self, default_timeout: float = DEFAULT_TIMEOUT):
        """
        Initializes the AsyncDLightClient.

        Args:
            default_timeout: Default network operation timeout in seconds.
        """
        self.default_timeout = default_timeout

    def _generate_command_id(self) -> str:
        """Generates a unique command ID (remains synchronous)."""
        return f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

    async def _async_send_tcp_command(self, target_ip: str, command: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sends a command via TCP using asyncio streams and receives the response.

        Handles the 4-byte length prefix header in the response asynchronously.

        Args:
            target_ip: The IP address of the dLight device.
            command: The command dictionary to send (will be JSON serialized).

        Returns:
            The JSON response payload as a dictionary.

        Raises:
            DLightTimeoutError: If the connection or read/write times out.
            DLightConnectionError: If any other connection/socket error occurs.
            DLightCommandError: If the command cannot be serialized.
            DLightResponseError: If the response header/payload is invalid,
                                 or the device returns a non-SUCCESS status.
        """
        reader = None
        writer = None
        try:
            # Serialize command to JSON bytes (synchronous part)
            try:
                json_data = json.dumps(command).encode('utf-8')
            except TypeError as e:
                raise DLightCommandError(f"Failed to serialize command to JSON: {e}") from e

            # Open connection with timeout
            async with asyncio.timeout(self.default_timeout):
                _LOGGER.debug("Opening connection to %s:%d", target_ip, DEFAULT_TCP_PORT)
                reader, writer = await asyncio.open_connection(target_ip, DEFAULT_TCP_PORT)

                # Send the command
                _LOGGER.debug("Sending command: %s", json_data)
                writer.write(json_data)
                await writer.drain()

                # --- Read the response ---
                # 1. Read the 4-byte header (payload length)
                _LOGGER.debug("Reading header (4 bytes)")
                header = await reader.readexactly(4)

            # Decode the header (Big Endian unsigned integer) - synchronous
            try:
                payload_length = struct.unpack('>I', header)[0]
                _LOGGER.debug("Received header, payload length: %d", payload_length)
            except struct.error as e:
                 raise DLightResponseError(f"Failed to unpack header bytes: {e}") from e

            if payload_length == 0:
                raise DLightResponseError("Received zero payload length in header")
            if payload_length > MAX_PAYLOAD_SIZE:
                 raise DLightResponseError(f"Payload length {payload_length} exceeds maximum limit {MAX_PAYLOAD_SIZE}")

            # Read the JSON payload with timeout
            async with asyncio.timeout(self.default_timeout):
                _LOGGER.debug("Reading payload (%d bytes)", payload_length)
                payload_bytes = await reader.readexactly(payload_length)

            # Deserialize the JSON payload - synchronous
            try:
                response = json.loads(payload_bytes.decode('utf-8'))
                _LOGGER.debug("Received response: %s", response)
            except json.JSONDecodeError as e:
                raise DLightResponseError(f"Failed to decode JSON payload: {e}\nRaw Payload: {payload_bytes!r}") from e
            except UnicodeDecodeError as e:
                 raise DLightResponseError(f"Failed to decode payload as UTF-8: {e}\nRaw Payload: {payload_bytes!r}") from e

            # Check status - synchronous
            status = response.get("status")
            if status != "SUCCESS":
                raise DLightResponseError(f"dLight returned non-SUCCESS status: '{status}'. Full response: {response}")

            return response

        except asyncio.TimeoutError:
            raise DLightTimeoutError(f"Timeout communicating with {target_ip}:{DEFAULT_TCP_PORT}") from None
        except ConnectionRefusedError as e:
             raise DLightConnectionError(f"Connection refused by {target_ip}:{DEFAULT_TCP_PORT}") from e
        except OSError as e: # Catch other potential socket/network errors
            raise DLightConnectionError(f"Network error communicating with {target_ip}:{DEFAULT_TCP_PORT}: {e}") from e
        except asyncio.IncompleteReadError as e:
             raise DLightResponseError(f"Connection closed unexpectedly while reading. Expected {e.expected} bytes, got {len(e.partial)}.") from e
        except Exception as e:
             # Catch any other unexpected errors during the process
             _LOGGER.exception("Unexpected error during TCP command")
             raise DLightError(f"An unexpected error occurred: {e}") from e
        finally:
            if writer:
                try:
                    writer.close()
                    await writer.wait_closed()
                    _LOGGER.debug("Connection closed")
                except Exception:
                    _LOGGER.debug("Error closing writer (may already be closed)")


    # --- Public API Methods (Async) ---

    async def set_light_state(self, target_ip: str, device_id: str, on: bool) -> Dict[str, Any]:
        """Turns the dLight on or off (asynchronously)."""
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": "EXECUTE",
            "commands": [{"on": bool(on)}]
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def set_brightness(self, target_ip: str, device_id: str, brightness: int) -> Dict[str, Any]:
        """Sets the brightness of the dLight (asynchronously)."""
        if not 0 <= brightness <= 100:
            raise ValueError("Brightness must be between 0 and 100")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": "EXECUTE",
            "commands": [{"brightness": int(brightness)}]
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def set_color_temperature(self, target_ip: str, device_id: str, temperature: int) -> Dict[str, Any]:
        """Sets the color temperature of the dLight (asynchronously)."""
        if not 2600 <= temperature <= 6000:
            raise ValueError("Color temperature must be between 2600 and 6000 Kelvin")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": "EXECUTE",
            "commands": [{"color": {"temperature": int(temperature)}}]
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def query_device_state(self, target_ip: str, device_id: str) -> Dict[str, Any]:
        """Queries the current state of the dLight (asynchronously)."""
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": "QUERY_DEVICE_STATES",
            "commands": []
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def query_device_info(self, target_ip: str, device_id: str) -> Dict[str, Any]:
        """Queries the device information of the dLight (asynchronously)."""
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": "QUERY_DEVICE_INFO",
            "commands": []
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def connect_to_wifi(self, device_id: str, ssid: str, password: str) -> Dict[str, Any]:
        """Sends the SSID_CONNECT command for direct Wi-Fi provisioning (asynchronously)."""
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": "SSID_CONNECT",
            "ssid": ssid,
            "password": password
        }
        try:
             return await self._async_send_tcp_command(FACTORY_RESET_IP, command)
        except DLightError as e:
             raise DLightCommandError(f"Failed to send SSID_CONNECT to {FACTORY_RESET_IP}: {e}") from e

    # --- UDP Discovery (Async) ---

    class _DiscoveryProtocol(asyncio.DatagramProtocol):
        """Asyncio Protocol to handle incoming discovery responses."""
        def __init__(self, discovered_devices_set: Set[str], results_list: List[Dict]):
            self.transport = None
            self.discovered_devices_set = discovered_devices_set
            self.results_list = results_list
            super().__init__()

        def connection_made(self, transport: asyncio.DatagramTransport):
            _LOGGER.debug("Discovery listener connection made (transport ready)")
            self.transport = transport

        def datagram_received(self, data: bytes, addr: Tuple[str, int]):
            ip_address = addr[0]
            _LOGGER.debug("Received %d bytes from %s", len(data), ip_address)

            # Avoid processing duplicates immediately
            if ip_address in self.discovered_devices_set:
                _LOGGER.debug("Ignoring duplicate discovery response from %s", ip_address)
                return

            try:
                device_info = json.loads(data.decode('utf-8'))
                device_info['ip_address'] = ip_address
                _LOGGER.info("Discovered dLight: %s", device_info)
                self.discovered_devices_set.add(ip_address)
                self.results_list.append(device_info)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                _LOGGER.warning("Error decoding discovery response from %s: %s", ip_address, e)
            except Exception as e:
                 _LOGGER.exception("Unexpected error processing datagram from %s", ip_address)


        def error_received(self, exc: Exception):
            _LOGGER.error(f"Discovery listener error: {exc}")

        def connection_lost(self, exc: Optional[Exception]):
            _LOGGER.debug(f"Discovery listener connection lost: {exc}")
            # Optionally handle cleanup or reconnection logic if needed


    @staticmethod
    async def discover_devices(discovery_duration: float = 3.0,
                               response_port: int = DEFAULT_UDP_RESPONSE_PORT,
                               discovery_port: int = DEFAULT_UDP_DISCOVERY_PORT,
                               broadcast_address: str = BROADCAST_ADDRESS) -> List[Dict[str, Any]]:
        """
        Discovers dLight devices on the network using asyncio UDP.

        Args:
            discovery_duration: How long to listen for responses (in seconds).
            response_port: The local UDP port to listen on for responses.
            discovery_port: The UDP port dLights listen on for discovery probes.
            broadcast_address: The broadcast address to send the probe to.

        Returns:
            A list of dictionaries, each representing a discovered device
            including its 'ip_address'. Returns an empty list if none found or on error.
        """
        loop = asyncio.get_running_loop()
        discovered_devices_set = set()
        results_list = []
        transport = None
        protocol = None

        try:
            # Decode the hex payload (synchronous)
            try:
                probe_payload = binascii.unhexlify(UDP_DISCOVERY_PAYLOAD_HEX)
            except binascii.Error as e:
                 _LOGGER.error(f"Internal error: failed to decode UDP probe payload hex: {e}")
                 return []

            # Create the listening endpoint
            # Pass the shared set and list to the protocol instance
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: AsyncDLightClient._DiscoveryProtocol(discovered_devices_set, results_list),
                local_addr=('0.0.0.0', response_port),
                allow_broadcast=False # Listener doesn't need broadcast
            )
            _LOGGER.debug(f"Listening for discovery responses on port {response_port}")

            # Create a separate sending socket/transport for broadcast
            # Using a separate one avoids potential issues with reusing the listener
            send_transport, _ = await loop.create_datagram_endpoint(
                lambda: asyncio.DatagramProtocol(), # Simple protocol for sending
                remote_addr=(broadcast_address, discovery_port) # Set remote for easy sendto
            )
            # Enable broadcasting on the sending socket if possible (may require privileges)
            sending_socket = send_transport.get_extra_info('socket')
            if sending_socket:
                 sending_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                 _LOGGER.debug("Broadcast enabled for sending socket")
            else:
                 _LOGGER.warning("Could not get underlying socket to enable broadcast.")


            # Send the broadcast probe
            _LOGGER.info(f"Sending discovery probe to {broadcast_address}:{discovery_port}")
            send_transport.sendto(probe_payload) # No need for address if remote_addr was set

            # Wait for responses
            await asyncio.sleep(discovery_duration)

            _LOGGER.info(f"Discovery finished. Found {len(results_list)} device(s).")

        except PermissionError as e:
            _LOGGER.error(f"Permission denied for UDP broadcast or binding to port {response_port}. Try running with higher privileges if necessary. Error: {e}")
            return []
        except OSError as e:
             _LOGGER.error(f"Network error during discovery (e.g., port {response_port} in use?): {e}")
             return []
        except Exception as e:
            _LOGGER.exception(f"An unexpected error occurred during async discovery: {e}")
            return []
        finally:
            if transport:
                transport.close()
                _LOGGER.debug("Discovery listener transport closed.")
            if 'send_transport' in locals() and send_transport:
                 send_transport.close()
                 _LOGGER.debug("Discovery sender transport closed.")

        return results_list


# --- Example Usage (Async) ---
async def main():
    """Example of using the async client."""
    logging.basicConfig(level=logging.DEBUG) # Enable debug logging for example
    print("--- Async dLight Python Client Example ---")
    client = AsyncDLightClient()

    print("\n--- Discovering Devices (3 seconds) ---")
    try:
        devices = await AsyncDLightClient.discover_devices(discovery_duration=3.0)
    except Exception as e:
         print(f"Discovery failed with an unexpected error: {e}")
         devices = []

    if not devices:
        print("\nNo dLight devices found on the network.")
        # Add connect_to_wifi example if needed, remembering it's async now
        # print("Attempting Wi-Fi connection (Example - REPLACE details)...")
        # try:
        #     wifi_resp = await client.connect_to_wifi("YOUR_DEVICE_ID", "Your_WiFi_SSID", "Your_WiFi_Password")
        #     print(f"Wi-Fi connect response: {wifi_resp}")
        # except DLightError as e:
        #     print(f"Wi-Fi connect failed: {e}")
    else:
        target_device = devices[0]
        target_ip = target_device['ip_address']
        device_id = target_device.get('deviceId') or target_device.get('deviceid')

        if not device_id:
             print(f"Error: Could not get deviceId from discovery: {target_device}")
             return

        print(f"\n--- Interacting with: {device_id} at {target_ip} ---")
        try:
            print("\nQuerying Device Info...")
            info = await client.query_device_info(target_ip, device_id)
            print(f"  Info: {info}")

            print("\nQuerying Device State...")
            state_resp = await client.query_device_state(target_ip, device_id)
            print(f"  Current State: {state_resp.get('states')}")

            print("\nTurning Light ON...")
            await client.set_light_state(target_ip, device_id, True)
            await asyncio.sleep(0.5)

            print("\nSetting Brightness to 30%...")
            await client.set_brightness(target_ip, device_id, 30)
            await asyncio.sleep(0.5)

            print("\nSetting Color Temperature to 5000K...")
            await client.set_color_temperature(target_ip, device_id, 5000)
            await asyncio.sleep(0.5)

            print("\nQuerying Device State Again...")
            state_resp = await client.query_device_state(target_ip, device_id)
            print(f"  New State: {state_resp.get('states')}")

            print("\nTurning Light OFF...")
            await client.set_light_state(target_ip, device_id, False)

        except DLightError as e:
            print(f"\n--- An error occurred during interaction ---")
            print(e)
        except ValueError as e:
             print(f"\n--- Invalid value provided ---")
             print(e)
        except Exception as e:
             _LOGGER.exception("Unexpected error during interaction example")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Example stopped.")
