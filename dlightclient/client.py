# dlightclient/client.py
"""Core AsyncDLightClient for TCP communication with dLight devices."""

import asyncio
import socket # For specific error types like ConnectionRefusedError
import json
import struct
import time
import uuid
import logging
from typing import Dict, Any, Optional

# Import constants and exceptions from within the package
from .constants import (
    DEFAULT_TCP_PORT,
    DEFAULT_TIMEOUT,
    MAX_PAYLOAD_SIZE,
    FACTORY_RESET_IP,
    COMMAND_TYPE_EXECUTE,
    COMMAND_TYPE_QUERY_DEVICE_STATES,
    COMMAND_TYPE_QUERY_DEVICE_INFO,
    COMMAND_TYPE_SSID_CONNECT,
    STATUS_SUCCESS,
    _LOGGER, # Use the logger defined in constants or define one here
)
from .exceptions import (
    DLightError,
    DLightConnectionError,
    DLightTimeoutError,
    DLightCommandError,
    DLightResponseError,
)

# Logger specific to the client, inheriting from the base logger if needed
_LOGGER = logging.getLogger(__name__)


class AsyncDLightClient:
    """
    An asynchronous client for interacting with dLight devices using asyncio TCP.

    Provides async methods for querying status and controlling the light's state
    (on/off, brightness, color temperature) and initiating Wi-Fi connection.

    Discovery is handled separately by the `discover_devices` function in the
    `dlightclient.discovery` module.
    """

    def __init__(self, default_timeout: float = DEFAULT_TIMEOUT):
        """
        Initializes the AsyncDLightClient.

        Args:
            default_timeout: Default network operation timeout in seconds.
        """
        self.default_timeout = default_timeout
        _LOGGER.debug(f"AsyncDLightClient initialized with timeout: {default_timeout}s")

    def _generate_command_id(self) -> str:
        """Generates a unique command ID (synchronous)."""
        # Combines timestamp with a short UUID part for uniqueness
        return f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

    async def _async_send_tcp_command(
        self,
        target_ip: str,
        command: Dict[str, Any],
        port: int = DEFAULT_TCP_PORT
    ) -> Dict[str, Any]:
        """
        Sends a command via TCP using asyncio streams and receives the response.

        Handles connection, sending the JSON command, reading the 4-byte length
        prefix header, reading the JSON payload, and basic validation including
        checking for echoed commands.

        Args:
            target_ip: The IP address of the dLight device.
            command: The command dictionary to send (will be JSON serialized).
            port: The TCP port to connect to (defaults to DEFAULT_TCP_PORT).

        Returns:
            The JSON response payload as a dictionary.

        Raises:
            DLightTimeoutError: If any network operation times out.
            DLightConnectionError: If any other connection/socket error occurs.
            DLightCommandError: If the command cannot be serialized to JSON.
            DLightResponseError: If the response header/payload is invalid,
                                 malformed, the device returns a non-SUCCESS status,
                                 or the device echoes the command back.
            DLightError: For other unexpected errors during the process.
        """
        reader: Optional[asyncio.StreamReader] = None
        writer: Optional[asyncio.StreamWriter] = None
        operation = f"command {command.get('commandType', 'UNKNOWN')} to {target_ip}:{port}"
        _LOGGER.debug(f"Preparing {operation}")
        json_data: bytes = b'' # Store serialized command for echo check

        try:
            # 1. Serialize command to JSON bytes
            try:
                json_data = json.dumps(command).encode('utf-8') # Store for later comparison
                _LOGGER.debug(f"Serialized command ({len(json_data)} bytes): {json_data!r}")
            except TypeError as e:
                raise DLightCommandError(f"Failed to serialize command to JSON: {e}\nCommand: {command}") from e

            # 2. Open connection with timeout
            _LOGGER.debug(f"Opening connection for {operation}")
            try:
                connect_future = asyncio.open_connection(target_ip, port)
                reader, writer = await asyncio.wait_for(connect_future, timeout=self.default_timeout)
                peername = writer.get_extra_info('peername')
                _LOGGER.debug(f"Connection established to {peername}")
            except asyncio.TimeoutError:
                 raise DLightTimeoutError(f"Timeout connecting to {target_ip}:{port}") from None
            except ConnectionRefusedError as e:
                 raise DLightConnectionError(f"Connection refused by {target_ip}:{port}") from e
            except OSError as e: # Catch other potential connect errors (e.g., network unreachable)
                 raise DLightConnectionError(f"Network error connecting to {target_ip}:{port}: {e}") from e

            # 3. Send command data with timeout
            _LOGGER.debug(f"Sending {len(json_data)} bytes for {operation}")
            writer.write(json_data)
            try:
                # Ensure all data is sent from the buffer
                await asyncio.wait_for(writer.drain(), timeout=self.default_timeout)
                _LOGGER.debug("Data sent and drained.")
            except asyncio.TimeoutError:
                 raise DLightTimeoutError(f"Timeout sending data for {operation}") from None
            except OSError as e: # Catch errors during drain/send (e.g., connection reset)
                 raise DLightConnectionError(f"Network error sending data for {operation}: {e}") from e

            # 4. Read response header (4 bytes) with timeout
            _LOGGER.debug(f"Reading header (4 bytes) for {operation}")
            header = b''
            try:
                header = await asyncio.wait_for(reader.readexactly(4), timeout=self.default_timeout)
                _LOGGER.debug(f"Received header: {header!r} (Hex: {header.hex()})")
            except asyncio.TimeoutError:
                 raise DLightTimeoutError(f"Timeout reading header for {operation}") from None
            except asyncio.IncompleteReadError as e:
                # Connection closed before 4 bytes were received
                raise DLightResponseError(
                    f"Connection closed unexpectedly while reading header for {operation}. "
                    f"Expected 4 bytes, got {len(e.partial)}: {e.partial!r}"
                ) from e
            except OSError as e: # Catch errors during read
                 raise DLightConnectionError(f"Network error reading header for {operation}: {e}") from e

            # 5. Decode header to get payload length
            payload_length = -1
            try:
                payload_length = struct.unpack('>I', header)[0] # Big-endian unsigned integer
                _LOGGER.debug(f"Decoded header, expected payload length: {payload_length}")
            except struct.error as e:
                 raise DLightResponseError(f"Failed to unpack header bytes ({header!r}): {e}") from e

            # 6. Validate payload length
            if payload_length < 0: # Should not happen with '>I' unpack
                 raise DLightResponseError(f"Invalid negative payload length decoded: {payload_length}")
            if payload_length > MAX_PAYLOAD_SIZE:
                 raise DLightResponseError(
                     f"Payload length {payload_length} from header ({header!r}) "
                     f"exceeds maximum limit {MAX_PAYLOAD_SIZE}"
                 )

            # 7. Read response payload with timeout
            payload_bytes = b''
            if payload_length == 0:
                _LOGGER.debug("Payload length is 0, expecting no payload data.")
                # No need to read, payload_bytes remains empty
            else:
                _LOGGER.debug(f"Reading payload ({payload_length} bytes) for {operation}")
                try:
                    payload_bytes = await asyncio.wait_for(
                        reader.readexactly(payload_length),
                        timeout=self.default_timeout
                    )
                    _LOGGER.debug(f"Received payload ({len(payload_bytes)} bytes)")
                    _LOGGER.log(logging.DEBUG - 1, f"Raw payload data: {payload_bytes!r}") # Very verbose log level
                except asyncio.TimeoutError:
                     raise DLightTimeoutError(f"Timeout reading payload ({payload_length} bytes) for {operation}") from None
                except asyncio.IncompleteReadError as e:
                     # Connection closed before full payload received
                     raise DLightResponseError(
                         f"Connection closed unexpectedly while reading payload for {operation}. "
                         f"Expected {payload_length} bytes, got {len(e.partial)}. Partial data: {e.partial!r}"
                     ) from e
                except OSError as e: # Catch errors during read
                    raise DLightConnectionError(f"Network error reading payload for {operation}: {e}") from e

            # 8. Deserialize JSON payload
            response: Dict[str, Any] = {}
            if payload_length == 0 and not payload_bytes:
                 # Handle the zero payload case - Assume success
                 response = {"status": STATUS_SUCCESS, "_payload_length": 0} # Synthesize response
                 _LOGGER.debug("Interpreting zero-length payload as implicit success.")
            elif payload_bytes:
                 try:
                    response = json.loads(payload_bytes.decode('utf-8'))
                    _LOGGER.debug(f"Decoded JSON response: {response}")
                 except json.JSONDecodeError as e:
                    raise DLightResponseError(f"Failed to decode JSON payload: {e}\nRaw Payload: {payload_bytes!r}") from e
                 except UnicodeDecodeError as e:
                    raise DLightResponseError(f"Failed to decode payload as UTF-8: {e}\nRaw Payload: {payload_bytes!r}") from e
            else:
                # This case (payload_length > 0 but payload_bytes is empty)
                # should be caught by readexactly errors, but check just in case.
                raise DLightResponseError("Payload length > 0 but no payload bytes received.")

            # --- NEW: Check for echoed command ---
            if payload_length > 0 and response == command:
                _LOGGER.error(f"Device echoed back the command, indicating it was not recognized. Command: {command}")
                raise DLightResponseError(
                    f"Device echoed back the command (unrecognized command?). "
                    f"Sent: {command}, Received: {response}"
                )
            # --- End NEW ---

            # 9. Check response status (unless synthesized for zero-payload)
            if response.get("_payload_length") != 0: # Check if it's not the synthesized response
                status = response.get("status")
                if status != STATUS_SUCCESS:
                    # Include full response in error message for better debugging
                    raise DLightResponseError(
                        f"dLight returned non-SUCCESS status: '{status}'. "
                        f"Full response: {response}"
                    )
                _LOGGER.debug(f"Command successful with status: {status}")

            return response

        except DLightError:
            # Re-raise specific DLight errors directly
            raise
        except asyncio.TimeoutError:
            # Catch any general timeout not caught by specific wait_for blocks
             _LOGGER.warning(f"General timeout encountered during {operation}", exc_info=True)
             raise DLightTimeoutError(f"General timeout during {operation}") from None
        except Exception as e:
             # Wrap unexpected errors in DLightError for consistent API
             _LOGGER.exception(f"An unexpected error occurred during {operation}")
             raise DLightError(f"An unexpected error occurred during {operation}: {e}") from e
        finally:
            # 10. Close connection gracefully
            if writer and not writer.is_closing():
                peername = writer.get_extra_info('peername', 'unknown peer')
                _LOGGER.debug(f"Closing connection to {peername}")
                try:
                    writer.close()
                    # Wait briefly for close to complete, but don't hang forever
                    await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
                    _LOGGER.debug(f"Connection to {peername} closed.")
                except (asyncio.TimeoutError, OSError, BrokenPipeError) as e_close:
                    # Log errors during close but don't raise, as main operation might have succeeded/failed already
                    _LOGGER.debug(f"Error during writer close/wait_closed for {peername}: {e_close}")
            elif writer:
                 _LOGGER.debug("Writer already closing or closed.")


    # --- Public API Methods (No changes needed below this line) ---

    async def set_light_state(self, target_ip: str, device_id: str, on: bool) -> Dict[str, Any]:
        """Turns the dLight on or off asynchronously."""
        _LOGGER.info(f"Setting light state for {device_id} at {target_ip} to {'ON' if on else 'OFF'}")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": COMMAND_TYPE_EXECUTE,
            "commands": [{"on": bool(on)}] # Ensure boolean
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def set_brightness(self, target_ip: str, device_id: str, brightness: int) -> Dict[str, Any]:
        """Sets the brightness of the dLight asynchronously (0-100)."""
        if not 0 <= brightness <= 100:
            raise ValueError("Brightness must be between 0 and 100")
        _LOGGER.info(f"Setting brightness for {device_id} at {target_ip} to {brightness}%")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": COMMAND_TYPE_EXECUTE,
            "commands": [{"brightness": int(brightness)}] # Ensure integer
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def set_color_temperature(self, target_ip: str, device_id: str, temperature: int) -> Dict[str, Any]:
        """Sets the color temperature of the dLight asynchronously (2600-6000K)."""
        if not 2600 <= temperature <= 6000:
            raise ValueError("Color temperature must be between 2600 and 6000 Kelvin")
        _LOGGER.info(f"Setting color temp for {device_id} at {target_ip} to {temperature}K")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": COMMAND_TYPE_EXECUTE,
            "commands": [{"color": {"temperature": int(temperature)}}] # Ensure integer
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def query_device_state(self, target_ip: str, device_id: str) -> Dict[str, Any]:
        """Queries the current state of the dLight asynchronously."""
        _LOGGER.info(f"Querying state for {device_id} at {target_ip}")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": COMMAND_TYPE_QUERY_DEVICE_STATES,
            "commands": [] # No specific commands needed for query
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def query_device_info(self, target_ip: str, device_id: str) -> Dict[str, Any]:
        """Queries the device information of the dLight asynchronously."""
        _LOGGER.info(f"Querying info for {device_id} at {target_ip}")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": COMMAND_TYPE_QUERY_DEVICE_INFO,
            "commands": [] # No specific commands needed for query
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def connect_to_wifi(
        self,
        device_id: str,
        ssid: str,
        password: str,
        target_ip: str = FACTORY_RESET_IP,
        port: int = DEFAULT_TCP_PORT
    ) -> Dict[str, Any]:
        """
        Sends the SSID_CONNECT command for direct Wi-Fi provisioning.

        This typically requires the device to be in SoftAP mode (factory reset state)
        and the client machine to be connected to that SoftAP network.

        Args:
            device_id: The ID of the device (often part of the SoftAP SSID).
            ssid: The SSID of the target Wi-Fi network to connect to.
            password: The password for the target Wi-Fi network.
            target_ip: The IP address of the device in SoftAP mode (defaults to FACTORY_RESET_IP).
            port: The TCP port to use (defaults to DEFAULT_TCP_PORT).

        Returns:
            The response dictionary from the device.

        Raises:
            DLightCommandError: If the command fails specifically during this operation.
            Other DLight errors (Connection, Timeout, Response) via _async_send_tcp_command.
        """
        _LOGGER.info(f"Sending Wi-Fi credentials (SSID: {ssid}) to device {device_id} at {target_ip}:{port}")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": COMMAND_TYPE_SSID_CONNECT,
            "ssid": ssid,
            "password": password
        }
        try:
             # Use the specific SoftAP IP and port
             return await self._async_send_tcp_command(target_ip, command, port=port)
        except DLightError as e:
             # Wrap error with specific context for this operation
             raise DLightCommandError(f"Failed to send SSID_CONNECT command to {target_ip}:{port}: {e}") from e

