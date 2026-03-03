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
    """An asynchronous client for dLight device communication.

    This class handles the TCP communication with dLight devices, allowing for
    sending commands and receiving responses. It provides methods for controlling
    the light's state, querying its status, and configuring its Wi-Fi connection.

    Args:
        default_timeout (float): The default timeout in seconds for network
            operations.
        persistent (bool): If True, TCP connections are kept open for reuse.
    """

    def __init__(self, default_timeout: float = DEFAULT_TIMEOUT, persistent: bool = False):
        """Initializes the AsyncDLightClient."""
        self.default_timeout = default_timeout
        self.persistent = persistent
        # Key: "ip:port", Value: (reader, writer, last_activity_time)
        self._connections: Dict[str, Tuple[asyncio.StreamReader, asyncio.StreamWriter, float]] = {}
        _LOGGER.debug(f"AsyncDLightClient initialized with timeout: {default_timeout}s, persistent: {persistent}")

    async def __aenter__(self):
        """Enable persistence when used as a context manager."""
        self.persistent = True
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Close all connections when exiting the context manager."""
        await self.close()

    async def close(self):
        """Closes all open persistent connections."""
        _LOGGER.debug(f"Closing {len(self._connections)} persistent connections")
        keys = list(self._connections.keys())
        for key in keys:
            _, writer, _ = self._connections.pop(key)
            if writer and not writer.is_closing():
                try:
                    writer.close()
                    await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
                except Exception as e:
                    _LOGGER.debug(f"Error closing persistent connection {key}: {e}")

    def _generate_command_id(self) -> str:
        """Generates a unique command ID.

        Returns:
            A unique string to be used as a command ID.
        """
        # Combines timestamp with a short UUID part for uniqueness
        return f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

    async def _async_send_tcp_command(
        self,
        target_ip: str,
        command: Dict[str, Any],
        port: int = DEFAULT_TCP_PORT
    ) -> Dict[str, Any]:
        """Sends a command to a dLight device and returns the response.

        This method establishes a TCP connection (or reuses an existing one),
        sends a JSON-serialized command, and waits for a response.
        The dLight protocol uses a 4-byte, big-endian length prefix followed
        by a JSON payload for responses.

        Args:
            target_ip: The IP address of the dLight device.
            command: The command to send, as a dictionary.
            port: The TCP port to connect to.

        Returns:
            The JSON response from the device as a dictionary.

        Raises:
            DLightTimeoutError: If a network operation times out.
            DLightConnectionError: If a connection error occurs.
            DLightCommandError: If the command cannot be serialized to JSON.
            DLightResponseError: If the response is invalid or indicates an error.
            DLightError: For any other unexpected errors.
        """
        reader: Optional[asyncio.StreamReader] = None
        writer: Optional[asyncio.StreamWriter] = None
        operation = f"command {command.get('commandType', 'UNKNOWN')} to {target_ip}:{port}"
        _LOGGER.debug(f"Preparing {operation}")
        json_data: bytes = b'' # Store serialized command for echo check
        key = f"{target_ip}:{port}"

        try:
            # 1. Serialize command to JSON bytes
            try:
                json_data = json.dumps(command).encode('utf-8')
                _LOGGER.debug(f"Serialized command ({len(json_data)} bytes): {json_data!r}")
            except TypeError as e:
                raise DLightCommandError(f"Failed to serialize command to JSON: {e}\nCommand: {command}") from e

            # 2. Get or open connection
            if key in self._connections:
                reader, writer, last_activity = self._connections[key]
                if writer.is_closing():
                    _LOGGER.debug(f"Cached connection for {key} is closing, removing.")
                    del self._connections[key]
                    reader, writer = None, None
                else:
                    _LOGGER.debug(f"Reusing persistent connection for {key}")
                    # Update activity time
                    self._connections[key] = (reader, writer, time.time())

            if not reader or not writer:
                _LOGGER.debug(f"Opening new connection for {operation}")
                try:
                    connect_future = asyncio.open_connection(target_ip, port)
                    reader, writer = await asyncio.wait_for(connect_future, timeout=self.default_timeout)
                    peername = writer.get_extra_info('peername')
                    _LOGGER.debug(f"Connection established to {peername}")
                    if self.persistent:
                        self._connections[key] = (reader, writer, time.time())
                except asyncio.TimeoutError:
                     raise DLightTimeoutError(f"Timeout connecting to {target_ip}:{port}") from None
                except ConnectionRefusedError as e:
                     raise DLightConnectionError(f"Connection refused by {target_ip}:{port}") from e
                except OSError as e:
                     raise DLightConnectionError(f"Network error connecting to {target_ip}:{port}: {e}") from e

            # 3. Send command data with timeout
            _LOGGER.debug(f"Sending {len(json_data)} bytes for {operation}")
            writer.write(json_data)
            try:
                await asyncio.wait_for(writer.drain(), timeout=self.default_timeout)
                _LOGGER.debug("Data sent and drained.")
            except asyncio.TimeoutError:
                 raise DLightTimeoutError(f"Timeout sending data for {operation}") from None
            except OSError as e:
                 if key in self._connections: del self._connections[key]
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
                if key in self._connections: del self._connections[key]
                raise DLightResponseError(
                    f"Connection closed unexpectedly while reading header for {operation}. "
                    f"Expected 4 bytes, got {len(e.partial)}: {e.partial!r}"
                ) from e
            except OSError as e:
                 if key in self._connections: del self._connections[key]
                 raise DLightConnectionError(f"Network error reading header for {operation}: {e}") from e

            # 5. Decode header to get payload length
            payload_length = struct.unpack('>I', header)[0]
            _LOGGER.debug(f"Decoded header, expected payload length: {payload_length}")

            # 6. Validate payload length
            if payload_length > MAX_PAYLOAD_SIZE:
                 raise DLightResponseError(
                     f"Payload length {payload_length} exceeds maximum limit {MAX_PAYLOAD_SIZE}"
                 )

            # 7. Read response payload with timeout
            payload_bytes = b''
            if payload_length > 0:
                _LOGGER.debug(f"Reading payload ({payload_length} bytes) for {operation}")
                try:
                    payload_bytes = await asyncio.wait_for(
                        reader.readexactly(payload_length),
                        timeout=self.default_timeout
                    )
                except asyncio.TimeoutError:
                     raise DLightTimeoutError(f"Timeout reading payload ({payload_length} bytes) for {operation}") from None
                except asyncio.IncompleteReadError as e:
                     if key in self._connections: del self._connections[key]
                     raise DLightResponseError(
                         f"Connection closed unexpectedly while reading payload for {operation}."
                     ) from e
                except OSError as e:
                    if key in self._connections: del self._connections[key]
                    raise DLightConnectionError(f"Network error reading payload for {operation}: {e}") from e

            # 8. Deserialize JSON payload
            response: Dict[str, Any] = {}
            if payload_length == 0:
                 response = {"status": STATUS_SUCCESS, "_payload_length": 0}
            else:
                 try:
                    response = json.loads(payload_bytes.decode('utf-8'))
                 except json.JSONDecodeError as e:
                    raise DLightResponseError(f"Failed to decode JSON payload: {e}\nRaw Payload: {payload_bytes!r}") from e
                 except UnicodeDecodeError as e:
                    raise DLightResponseError(f"Failed to decode payload as UTF-8: {e}\nRaw Payload: {payload_bytes!r}") from e
                 except Exception as e:
                    raise DLightResponseError(f"Failed to decode response: {e}") from e

            # Check for echoed command
            if payload_length > 0 and response == command:
                raise DLightResponseError(f"Device echoed back the command (unrecognized?).")

            # 9. Check response status
            if response.get("_payload_length") != 0:
                status = response.get("status")
                if status != STATUS_SUCCESS:
                    raise DLightResponseError(f"dLight returned non-SUCCESS status: '{status}'")

            return response

        except DLightError:
            raise
        except Exception as e:
             _LOGGER.exception(f"An unexpected error occurred during {operation}")
             raise DLightError(f"An unexpected error occurred during {operation}: {e}") from e
        finally:
            # 10. Close connection if NOT persistent
            if not self.persistent and writer and not writer.is_closing():
                try:
                    writer.close()
                    await asyncio.wait_for(writer.wait_closed(), timeout=2.0)
                except Exception:
                    pass


    # --- Public API Methods (No changes needed below this line) ---

    async def set_light_state(self, target_ip: str, device_id: str, on: bool) -> Dict[str, Any]:
        """Sets the power state of the dLight.

        Args:
            target_ip: The IP address of the dLight device.
            device_id: The ID of the dLight device.
            on: True to turn the light on, False to turn it off.

        Returns:
            The response from the device.
        """
        _LOGGER.info(f"Setting light state for {device_id} at {target_ip} to {'ON' if on else 'OFF'}")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": COMMAND_TYPE_EXECUTE,
            "commands": [{"on": bool(on)}] # Ensure boolean
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def set_brightness(self, target_ip: str, device_id: str, brightness: int) -> Dict[str, Any]:
        """Sets the brightness of the dLight.

        Args:
            target_ip: The IP address of the dLight device.
            device_id: The ID of the dLight device.
            brightness: The desired brightness level, from 0 to 100.

        Returns:
            The response from the device.

        Raises:
            ValueError: If the brightness is not in the range [0, 100].
        """
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
        """Sets the color temperature of the dLight.

        Args:
            target_ip: The IP address of the dLight device.
            device_id: The ID of the dLight device.
            temperature: The desired color temperature in Kelvin, from 2600 to
                6000.

        Returns:
            The response from the device.

        Raises:
            ValueError: If the temperature is not in the range [2600, 6000].
        """
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
        """Queries the current state of the dLight.

        Args:
            target_ip: The IP address of the dLight device.
            device_id: The ID of the dLight device.

        Returns:
            The response from the device, containing its current state.
        """
        _LOGGER.info(f"Querying state for {device_id} at {target_ip}")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": COMMAND_TYPE_QUERY_DEVICE_STATES,
            "commands": [] # No specific commands needed for query
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def query_device_info(self, target_ip: str, device_id: str) -> Dict[str, Any]:
        """Queries the device information of the dLight.

        Args:
            target_ip: The IP address of the dLight device.
            device_id: The ID of the dLight device.

        Returns:
            The response from the device, containing its information.
        """
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
        """Sends Wi-Fi credentials to a dLight device.

        This method is used to provision a dLight device with Wi-Fi credentials,
        typically when the device is in SoftAP mode.

        Args:
            device_id: The ID of the dLight device.
            ssid: The SSID of the target Wi-Fi network.
            password: The password of the target Wi-Fi network.
            target_ip: The IP address of the device in SoftAP mode.
            port: The TCP port to use.

        Returns:
            The response from the device.

        Raises:
            DLightCommandError: If the command fails during this operation.
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

