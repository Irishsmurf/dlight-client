# dlightclient/device.py
"""Provides a DLightDevice class for object-oriented interaction."""

import asyncio
import logging
from typing import Dict, Any, Optional

# Import necessary components from the library
from .client import AsyncDLightClient
from .exceptions import DLightError, DLightTimeoutError, DLightResponseError

_LOGGER = logging.getLogger(__name__)

class DLightDevice:
    """
    Represents and interacts with a single dLight device.

    This class wraps an AsyncDLightClient instance and manages the IP address
    and device ID, providing simpler methods for controlling and querying
    a specific device.
    """

    def __init__(self, ip_address: str, device_id: str, client: AsyncDLightClient):
        """
        Initializes a DLightDevice instance.

        Args:
            ip_address: The IP address of the dLight device.
            device_id: The unique device ID of the dLight device.
            client: An initialized AsyncDLightClient instance to use for communication.
        """
        if not ip_address:
            raise ValueError("IP address cannot be empty")
        if not device_id:
            raise ValueError("Device ID cannot be empty")
        if client is None:
            raise ValueError("AsyncDLightClient instance is required")

        self._ip = ip_address
        self._id = device_id
        self._client = client
        # Potential future enhancement: store basic info/state fetched on init?
        # self.info: Optional[Dict[str, Any]] = None
        # self.state: Optional[Dict[str, Any]] = None
        _LOGGER.debug(f"DLightDevice initialized: ID='{self._id}', IP='{self._ip}'")

    @property
    def ip(self) -> str:
        """Returns the IP address of the device."""
        return self._ip

    @property
    def id(self) -> str:
        """Returns the device ID of the device."""
        return self._id

    async def turn_on(self) -> Dict[str, Any]:
        """Turns the light on."""
        _LOGGER.info(f"Device {self.id}: Turning ON")
        return await self._client.set_light_state(self.ip, self.id, True)

    async def turn_off(self) -> Dict[str, Any]:
        """Turns the light off."""
        _LOGGER.info(f"Device {self.id}: Turning OFF")
        return await self._client.set_light_state(self.ip, self.id, False)

    async def set_brightness(self, brightness: int) -> Dict[str, Any]:
        """
        Sets the light brightness.

        Args:
            brightness: Brightness level (0-100).

        Raises:
            ValueError: If brightness is outside the valid range.
            DLightError subclasses: On communication errors.
        """
        _LOGGER.info(f"Device {self.id}: Setting brightness to {brightness}%")
        # Validation is handled by the client method, but could be duplicated here if desired
        return await self._client.set_brightness(self.ip, self.id, brightness)

    async def set_color_temperature(self, temperature: int) -> Dict[str, Any]:
        """
        Sets the light color temperature.

        Args:
            temperature: Color temperature in Kelvin (2600-6000).

        Raises:
            ValueError: If temperature is outside the valid range.
            DLightError subclasses: On communication errors.
        """
        _LOGGER.info(f"Device {self.id}: Setting color temperature to {temperature}K")
        # Validation is handled by the client method
        return await self._client.set_color_temperature(self.ip, self.id, temperature)

    async def get_state(self) -> Dict[str, Any]:
        """
        Queries and returns the current state of the light.

        Returns:
            A dictionary representing the device's state (e.g.,
            {'on': True, 'brightness': 50, 'color': {'temperature': 4000}}).
            Returns an empty dict if state cannot be retrieved or is missing.

        Raises:
            DLightError subclasses: On communication errors.
        """
        _LOGGER.debug(f"Device {self.id}: Querying state")
        response = await self._client.query_device_state(self.ip, self.id)
        # Extract the nested 'states' dictionary for convenience
        state_data = response.get('states', {})
        _LOGGER.debug(f"Device {self.id}: Received state: {state_data}")
        return state_data

    async def get_info(self) -> Dict[str, Any]:
        """
        Queries and returns device information (model, versions, etc.).

        Returns:
            A dictionary containing device information.

        Raises:
            DLightError subclasses: On communication errors.
        """
        _LOGGER.debug(f"Device {self.id}: Querying info")
        info = await self._client.query_device_info(self.ip, self.id)
        # Return the whole response payload as it directly contains info fields
        _LOGGER.debug(f"Device {self.id}: Received info: {info}")
        return info

    async def flash(
        self,
        flashes: int = 3,
        on_duration: float = 0.3,
        off_duration: float = 0.3,
    ) -> bool:
        """
        Flashes the light on/off for notification and restores its original state.

        Args:
            flashes: Number of times to flash (one flash = off then on).
            on_duration: Duration the light stays ON in each flash cycle (seconds).
            off_duration: Duration the light stays OFF in each flash cycle (seconds).

        Returns:
            True if the flashing sequence completed successfully, False otherwise.

        Raises:
            DLightError subclasses: On communication errors during the process.
        """
        original_state: Optional[Dict[str, Any]] = None
        original_on: Optional[bool] = None
        original_brightness: Optional[int] = None
        original_temperature: Optional[int] = None
        success = False

        _LOGGER.info(f"Device {self.id}: Starting flash sequence ({flashes} flashes)")

        try:
            # 1. Get the current state to restore later
            _LOGGER.debug(f"Device {self.id}: Querying original state for flash...")
            original_state = await self.get_state() # Use own method

            if original_state:
                original_on = original_state.get('on')
                original_brightness = original_state.get('brightness')
                original_temperature = original_state.get('color', {}).get('temperature')
                _LOGGER.debug(f"Device {self.id}: Original state for flash: on={original_on}, brightness={original_brightness}, temp={original_temperature}")
            else:
                _LOGGER.warning(f"Device {self.id}: Could not retrieve detailed original state for flash. Will attempt basic restore.")
                original_on = False # Default assumption if state is missing

            # 2. Perform the flashing sequence
            _LOGGER.info(f"Device {self.id}: Flashing...")
            for i in range(flashes):
                _LOGGER.debug(f"Device {self.id}: Flash {i+1}/{flashes}: OFF")
                await self.turn_off()
                await asyncio.sleep(off_duration)

                _LOGGER.debug(f"Device {self.id}: Flash {i+1}/{flashes}: ON")
                await self.turn_on()
                await asyncio.sleep(on_duration)

            _LOGGER.info(f"Device {self.id}: Flashing sequence complete.")
            success = True # Mark flashing as successful

        except (DLightTimeoutError, DLightResponseError, DLightError) as e:
            # Log specific errors from client calls
            _LOGGER.error(f"Device {self.id}: A dLight error occurred during flashing: {e}")
            # Restore will still be attempted in finally block
        except Exception as e:
            _LOGGER.exception(f"Device {self.id}: An unexpected error occurred during flashing")
            # Restore will still be attempted
        finally:
            # 3. Restore the original state (attempt even if flashing failed)
            if original_state is not None or original_on is not None:
                _LOGGER.info(f"Device {self.id}: Attempting to restore original state...")
                try:
                    # Restore brightness and temperature first if they were set
                    if original_brightness is not None:
                        _LOGGER.debug(f"Device {self.id}: Restoring brightness to {original_brightness}")
                        await self.set_brightness(original_brightness)
                        await asyncio.sleep(0.1)

                    if original_temperature is not None:
                        _LOGGER.debug(f"Device {self.id}: Restoring color temp to {original_temperature}")
                        await self.set_color_temperature(original_temperature)
                        await asyncio.sleep(0.1)

                    # Finally, set the original on/off state
                    if original_on is not None:
                        _LOGGER.debug(f"Device {self.id}: Restoring ON state to: {original_on}")
                        if original_on:
                            await self.turn_on()
                        else:
                            await self.turn_off()
                    else:
                        # Fallback if 'on' state was unknown
                        _LOGGER.warning(f"Device {self.id}: Original ON/OFF state unknown, leaving light ON after flash.")
                        await self.turn_on()

                    _LOGGER.info(f"Device {self.id}: Original state restoration attempted.")

                except DLightError as e_restore:
                    _LOGGER.error(f"Device {self.id}: Error restoring original state after flash: {e_restore}")
                    success = False # Mark overall operation as failed if restore fails
                except Exception as e_restore:
                    _LOGGER.exception(f"Device {self.id}: Unexpected error during state restoration after flash")
                    success = False
            else:
                _LOGGER.warning(f"Device {self.id}: No original state captured, cannot restore.")
                success = False # Cannot guarantee original state

        return success

    def __repr__(self) -> str:
        """Return a developer-friendly representation of the device."""
        return f"<DLightDevice id='{self.id}' ip='{self.ip}'>"

    def __str__(self) -> str:
        """Return a user-friendly representation of the device."""
        return f"dLight Device (ID: {self.id}, IP: {self.ip})"

