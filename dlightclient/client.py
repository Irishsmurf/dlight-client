# dlightclient/client.py
"""Core AsyncDLightClient for TCP communication with dLight devices."""

import asyncio
import json
import logging
import secrets
import ssl
import time
from typing import Any, Dict, Optional, Union

from ._frame import encode_command, mask_command, read_response
from ._pool import ConnectionPool

# Import constants and exceptions from within the package
from .constants import (
    COMMAND_TYPE_EXECUTE,
    COMMAND_TYPE_QUERY_DEVICE_INFO,
    COMMAND_TYPE_QUERY_DEVICE_STATES,
    COMMAND_TYPE_SSID_CONNECT,
    DEFAULT_TCP_PORT,
    DEFAULT_TIMEOUT,
    FACTORY_RESET_IP,
)
from .exceptions import (
    DLightCommandError,
    DLightConnectionError,
    DLightError,
    DLightTimeoutError,
)
from .models import CommandResult

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
        max_retries (int): Number of times to retry a command on network failure.
        retry_backoff (float): Initial backoff duration in seconds for retries.
        idle_timeout (float): Max time in seconds to reuse an idle connection.
        ssl (bool | ssl.SSLContext): If True, use default SSL context. If an
            SSLContext is provided, use it. If False or None, use plaintext.
    """

    def __init__(
        self,
        default_timeout: float = DEFAULT_TIMEOUT,
        persistent: bool = False,
        max_retries: int = 0,
        retry_backoff: float = 0.5,
        idle_timeout: float = 60.0,
        ssl: Optional[Union[bool, ssl.SSLContext]] = None,
    ):
        """Initializes the AsyncDLightClient."""
        self.default_timeout = default_timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self.ssl = ssl
        self._pool = ConnectionPool(persistent=persistent, idle_timeout=idle_timeout)
        _LOGGER.debug(
            f"AsyncDLightClient initialized (timeout: {default_timeout}s, "
            f"persistent: {persistent}, max_retries: {max_retries}, idle_timeout: {idle_timeout}s)"
        )

    @property
    def persistent(self) -> bool:
        """Whether TCP connections are kept open for reuse."""
        return self._pool.persistent

    @persistent.setter
    def persistent(self, value: bool) -> None:
        self._pool.persistent = value

    @property
    def idle_timeout(self) -> float:
        """Max time in seconds to reuse an idle connection."""
        return self._pool.idle_timeout

    @idle_timeout.setter
    def idle_timeout(self, value: float) -> None:
        self._pool.idle_timeout = value

    async def __aenter__(self) -> "AsyncDLightClient":
        """Enter the context manager.

        Persistence is controlled solely by the ``persistent`` constructor
        argument; the context manager only guarantees that ``close()`` is
        called on exit.
        """
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Close all connections when exiting the context manager."""
        await self.close()

    async def close(self) -> None:
        """Closes all open persistent connections."""
        await self._pool.close_all()

    def _generate_command_id(self) -> str:
        """Generates a unique command ID.

        Returns:
            A unique string to be used as a command ID.
        """
        # Combines timestamp with a short random part for uniqueness
        return f"{int(time.time() * 1000)}_{secrets.token_hex(4)}"

    async def _async_send_tcp_command(
        self,
        target_ip: str,
        command: Dict[str, Any],
        port: int = DEFAULT_TCP_PORT,
        ssl: Optional[Union[bool, ssl.SSLContext]] = None,
        timeout: Optional[float] = None,
    ) -> CommandResult:
        """Sends a command to a dLight device and returns the response.

        Serializes the command, acquires a connection from the pool (reusing
        a persistent one when possible), performs one request/response
        exchange, and retries on transient network failures with exponential
        backoff. Framing and response validation live in ``_frame.py``;
        connection lifecycle and eviction live in ``_pool.py``.

        Args:
            target_ip: The IP address of the dLight device.
            command: The command to send, as a dictionary.
            port: The TCP port to connect to.
            ssl: Optional SSL setting overriding the client's default.

        Returns:
            The JSON response from the device as a dictionary.

        Raises:
            DLightTimeoutError: If a network operation times out.
            DLightConnectionError: If a connection error occurs.
            DLightCommandError: If the command cannot be serialized to JSON.
            DLightResponseError: If the response is invalid or indicates an error.
            DLightError: For any other unexpected errors.
        """
        # If ssl is not provided to the command, use the client's default
        if ssl is None:
            ssl = self.ssl

        effective_timeout = timeout if timeout is not None else self.default_timeout

        operation = f"command {command.get('commandType', 'UNKNOWN')} to {target_ip}:{port}"
        json_data = encode_command(command)
        _LOGGER.debug(f"Prepared {operation} ({len(json_data)} bytes, SSL: {bool(ssl)}): "
                      f"{json.dumps(mask_command(command))!r}")

        for attempt in range(self.max_retries + 1):
            try:
                async with self._pool.connection(target_ip, port, ssl, effective_timeout) as (reader, writer):
                    writer.write(json_data)
                    try:
                        await asyncio.wait_for(writer.drain(), timeout=effective_timeout)
                    except asyncio.TimeoutError:
                        raise DLightTimeoutError(f"Timeout sending data for {operation}") from None
                    except OSError as e:
                        raise DLightConnectionError(f"Network error sending data for {operation}: {e}") from e

                    return await read_response(reader, effective_timeout, operation, command=command)

            except (DLightTimeoutError, DLightConnectionError) as e:
                if attempt < self.max_retries:
                    backoff = self.retry_backoff * (2**attempt)
                    _LOGGER.warning(f"Transient error during {operation}: {e}. Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
                    continue
                _LOGGER.error(f"Failed {operation} after {attempt + 1} attempts: {e}")
                raise
            except DLightError:
                raise
            except Exception as e:
                _LOGGER.exception(f"An unexpected error occurred during {operation}")
                raise DLightError(f"An unexpected error occurred during {operation}: {e}") from e
        raise DLightError(f"Failed {operation}: loop terminated without returning or raising.")

    # --- Public API Methods ---

    async def set_light_state(self, target_ip: str, device_id: str, on: bool) -> CommandResult:
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
            "commands": [{"on": bool(on)}],  # Ensure boolean
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def set_brightness(self, target_ip: str, device_id: str, brightness: int) -> CommandResult:
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
            "commands": [{"brightness": int(brightness)}],  # Ensure integer
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def set_color_temperature(self, target_ip: str, device_id: str, temperature: int) -> CommandResult:
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
            "commands": [{"color": {"temperature": int(temperature)}}],  # Ensure integer
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def query_device_state(self, target_ip: str, device_id: str) -> CommandResult:
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
            "commands": [],  # No specific commands needed for query
        }
        return await self._async_send_tcp_command(target_ip, command)

    async def query_device_info(
        self,
        target_ip: str,
        device_id: str,
        timeout: Optional[float] = None,
    ) -> CommandResult:
        """Queries the device information of the dLight.

        Args:
            target_ip: The IP address of the dLight device.
            device_id: The ID of the dLight device.
            timeout: Optional timeout override in seconds for this call only.

        Returns:
            The response from the device, containing its information.
        """
        _LOGGER.info(f"Querying info for {device_id} at {target_ip}")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": COMMAND_TYPE_QUERY_DEVICE_INFO,
            "commands": [],  # No specific commands needed for query
        }
        return await self._async_send_tcp_command(target_ip, command, timeout=timeout)

    async def connect_to_wifi(
        self,
        device_id: str,
        ssid: str,
        password: str,
        target_ip: str = FACTORY_RESET_IP,
        port: int = DEFAULT_TCP_PORT,
        ssl: Optional[Union[bool, ssl.SSLContext]] = None,
    ) -> CommandResult:
        """Sends Wi-Fi credentials to a dLight device.

        This method is used to provision a dLight device with Wi-Fi credentials,
        typically when the device is in SoftAP mode.

        Args:
            device_id: The ID of the dLight device.
            ssid: The SSID of the target Wi-Fi network.
            password: The password of the target Wi-Fi network.
            target_ip: The IP address of the device in SoftAP mode.
            port: The TCP port to use.
            ssl: Optional SSL context to use for this command.

        Returns:
            The response from the device.

        Raises:
            DLightCommandError: If the command fails during this operation.
        """
        _LOGGER.info(f"Sending Wi-Fi credentials to device {device_id} at {target_ip}:{port}")
        command = {
            "commandId": self._generate_command_id(),
            "deviceId": device_id,
            "commandType": COMMAND_TYPE_SSID_CONNECT,
            "ssid": ssid,
            "password": password,
        }
        try:
            # Use the specific SoftAP IP and port
            return await self._async_send_tcp_command(target_ip, command, port=port, ssl=ssl)
        except DLightError as e:
            # Wrap error with specific context for this operation
            raise DLightCommandError(f"Failed to send SSID_CONNECT command to {target_ip}:{port}: {e}") from e
