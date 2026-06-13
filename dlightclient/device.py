# dlightclient/device.py
"""Provides a DLightDevice class for object-oriented interaction."""

import asyncio
import logging
from typing import Any, Callable, Optional

# Import necessary components from the library
from .client import AsyncDLightClient
from .exceptions import DLightError, DLightResponseError, DLightTimeoutError
from .models import CommandResult, DeviceInfo, DeviceState, LightScene

_LOGGER = logging.getLogger(__name__)


class DLightDevice:
    """Represents and interacts with a single dLight device.

    This class provides a high-level, object-oriented interface for interacting
    with a specific dLight device. It simplifies control and state management by
    encapsulating the device's IP address, ID, and an `AsyncDLightClient` instance.
    """

    def __init__(self, ip_address: str, device_id: str, client: AsyncDLightClient):
        """Initializes a DLightDevice instance.

        Args:
            ip_address: The IP address of the dLight device.
            device_id: The unique device ID of the dLight device.
            client: An initialized AsyncDLightClient instance to use for communication.

        Raises:
            ValueError: If ip_address, device_id, or client are invalid.
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
        self._state: DeviceState = {}
        self._state_listeners: list[Callable[["DLightDevice", DeviceState, DeviceState], Any]] = []
        self._background_tasks: set[asyncio.Task[Any]] = set()
        _LOGGER.debug(f"DLightDevice initialized: ID='{self._id}', IP='{self._ip}'")

    @property
    def ip(self) -> str:
        """The IP address of the device."""
        return self._ip

    @property
    def id(self) -> str:
        """The unique device ID."""
        return self._id

    async def turn_on(self) -> CommandResult:
        """Turns the light on.

        Returns:
            The response from the device.
        """
        _LOGGER.info(f"Device {self.id}: Turning ON (optimistic)")
        _old = self._clone_state(self._state)
        old_on = self._state.get("on")
        self._state["on"] = True
        try:
            return await self._client.set_light_state(self.ip, self.id, True)
        except Exception:
            if old_on is not None:
                self._state["on"] = old_on
            else:
                del self._state["on"]
            raise
        finally:
            self._emit_state_change(_old, self._clone_state(self._state))

    async def turn_off(self) -> CommandResult:
        """Turns the light off.

        Returns:
            The response from the device.
        """
        _LOGGER.info(f"Device {self.id}: Turning OFF (optimistic)")
        _old = self._clone_state(self._state)
        old_on = self._state.get("on")
        self._state["on"] = False
        try:
            return await self._client.set_light_state(self.ip, self.id, False)
        except Exception:
            if old_on is not None:
                self._state["on"] = old_on
            else:
                del self._state["on"]
            raise
        finally:
            self._emit_state_change(_old, self._clone_state(self._state))

    async def toggle(self) -> CommandResult:
        """Toggles the light on or off.

        Uses the cached state where available to avoid a network round-trip.
        Falls back to get_state() if the cache is empty.

        Returns:
            The response from the device.
        """
        _LOGGER.info(f"Device {self.id}: Toggling")
        if "on" not in self._state:
            await self.get_state()
        if self._state.get("on"):
            return await self.turn_off()
        return await self.turn_on()

    async def set_brightness(self, brightness: int) -> CommandResult:
        """Sets the brightness of the light.

        Args:
            brightness: The desired brightness level, from 0 to 100.

        Returns:
            The response from the device.

        Raises:
            ValueError: If brightness is outside the valid range [0, 100].
        """
        _LOGGER.info(f"Device {self.id}: Setting brightness to {brightness}% (optimistic)")
        _old = self._clone_state(self._state)
        old_brightness = self._state.get("brightness")
        self._state["brightness"] = brightness
        try:
            return await self._client.set_brightness(self.ip, self.id, brightness)
        except Exception:
            if old_brightness is not None:
                self._state["brightness"] = old_brightness
            else:
                del self._state["brightness"]
            raise
        finally:
            self._emit_state_change(_old, self._clone_state(self._state))

    async def set_color_temperature(self, temperature: int) -> CommandResult:
        """Sets the color temperature of the light.

        Args:
            temperature: The desired color temperature in Kelvin, from 2600 to 6000.

        Returns:
            The response from the device.

        Raises:
            ValueError: If temperature is outside the valid range [2600, 6000].
        """
        _LOGGER.info(f"Device {self.id}: Setting color temperature to {temperature}K (optimistic)")

        _old = self._clone_state(self._state)

        # Save old color state for rollback
        old_color = self._state.get("color")
        if old_color:
            # Shallow copy of the dict is enough since temperature is an int
            old_color = old_color.copy()

        # Optimistic update
        if "color" not in self._state or not isinstance(self._state["color"], dict):
            self._state["color"] = {"temperature": temperature}
        else:
            self._state["color"]["temperature"] = temperature

        try:
            return await self._client.set_color_temperature(self.ip, self.id, temperature)
        except Exception:
            if old_color is not None:
                self._state["color"] = old_color
            else:
                del self._state["color"]
            raise
        finally:
            self._emit_state_change(_old, self._clone_state(self._state))

    async def get_state(self, force_update: bool = False) -> DeviceState:
        """Queries and returns the current state of the light.

        Args:
            force_update: If True, bypasses the local cache and queries the device.

        Returns:
            A dictionary representing the device's state (e.g.,
            `{'on': True, 'brightness': 50}`). Returns an empty dict if the
            state cannot be retrieved or is missing from the response.
        """
        if not force_update and self._state:
            _LOGGER.debug(f"Device {self.id}: Returning cached state")
            return self._state

        _old = self._clone_state(self._state)
        _LOGGER.debug(f"Device {self.id}: Querying state")
        response = await self._client.query_device_state(self.ip, self.id)
        self._state = response.get("states", {})
        _LOGGER.debug(f"Device {self.id}: Received state: {self._state}")
        self._emit_state_change(_old, self._clone_state(self._state))
        return self._state

    async def get_info(self) -> DeviceInfo:
        """Queries and returns device information.

        Returns:
            A dictionary containing device information, such as model and firmware
            version.
        """
        _LOGGER.debug(f"Device {self.id}: Querying info")
        info = await self._client.query_device_info(self.ip, self.id)
        # Casting to DeviceInfo for type safety
        return DeviceInfo(**info)  # type: ignore

    async def ping(self, timeout: float = 2.0) -> bool:
        """Checks whether the device is reachable.

        Args:
            timeout: Seconds to wait for a response. Overrides the client's
                default timeout for this call only.

        Returns:
            True if the device responded, False if it timed out or the
            connection was refused. Never raises.
        """
        _LOGGER.debug(f"Device {self.id}: Pinging (timeout={timeout}s)")
        try:
            await self._client.query_device_info(self.ip, self.id, timeout=timeout)
            return True
        except DLightError:
            return False

    async def apply_scene(
        self,
        scene: Optional[LightScene] = None,
        *,
        brightness: Optional[int] = None,
        temperature: Optional[int] = None,
    ) -> tuple[CommandResult, CommandResult]:
        """Applies a lighting scene (brightness + colour temperature) in one call.

        Accepts either a :class:`LightScene` object or explicit keyword args::

            await device.apply_scene(LightScene.READING)
            await device.apply_scene(brightness=90, temperature=5000)

        Both fields are updated in the state cache atomically before the network
        calls, and rolled back together if either command fails.

        Args:
            scene: A :class:`LightScene` preset. When provided, ``brightness``
                and ``temperature`` keyword args are ignored.
            brightness: Brightness percentage (0–100). Required when ``scene``
                is not given.
            temperature: Colour temperature in Kelvin (2600–6000). Required
                when ``scene`` is not given.

        Returns:
            A ``(brightness_result, temperature_result)`` tuple of
            :class:`CommandResult` dicts from the device.

        Raises:
            ValueError: If ``scene`` is ``None`` and either ``brightness`` or
                ``temperature`` is not provided.
        """
        if scene is not None:
            brightness = scene.brightness
            temperature = scene.temperature
        else:
            if brightness is None or temperature is None:
                raise ValueError(
                    "Provide a LightScene object or both brightness and temperature keyword args"
                )

        _LOGGER.info(
            f"Device {self.id}: Applying scene (brightness={brightness}%, temperature={temperature}K)"
        )

        _old = self._clone_state(self._state)

        # Save current values for rollback
        old_brightness = self._state.get("brightness")
        old_color = self._state.get("color")
        if old_color is not None:
            old_color = old_color.copy()

        # Optimistic update — both fields in one step before any network call
        self._state["brightness"] = brightness
        if "color" not in self._state or not isinstance(self._state["color"], dict):
            self._state["color"] = {"temperature": temperature}
        else:
            self._state["color"]["temperature"] = temperature

        try:
            results = await asyncio.gather(
                self._client.set_brightness(self.ip, self.id, brightness),
                self._client.set_color_temperature(self.ip, self.id, temperature),
                return_exceptions=True,
            )

            exc_brightness = results[0] if isinstance(results[0], Exception) else None
            exc_temperature = results[1] if isinstance(results[1], Exception) else None

            if exc_brightness is not None:
                # Roll back only the field(s) that actually failed so the cache
                # stays in sync with the physical device state.
                if old_brightness is not None:
                    self._state["brightness"] = old_brightness
                elif "brightness" in self._state:
                    del self._state["brightness"]
                if exc_temperature is not None:
                    if old_color is not None:
                        self._state["color"] = old_color
                    elif "color" in self._state:
                        del self._state["color"]
                raise exc_brightness

            if exc_temperature is not None:
                if old_color is not None:
                    self._state["color"] = old_color
                elif "color" in self._state:
                    del self._state["color"]
                raise exc_temperature

            return (results[0], results[1])  # type: ignore[return-value]
        finally:
            self._emit_state_change(_old, self._clone_state(self._state))

    async def flash(
        self,
        flashes: int = 3,
        on_duration: float = 0.3,
        off_duration: float = 0.3,
    ) -> bool:
        """Flashes the light to provide a visual notification.

        This method saves the light's current state, flashes it a specified number
        of times, and then restores the original state.

        Args:
            flashes: The number of times to flash.
            on_duration: The duration in seconds to keep the light on during a flash.
            off_duration: The duration in seconds to keep the light off during a flash.

        Returns:
            True if the sequence completed and the original state was restored
            successfully, False otherwise.
        """
        original_state: Optional[DeviceState] = None
        original_on: Optional[bool] = None
        original_brightness: Optional[int] = None
        original_temperature: Optional[int] = None
        success = False

        _LOGGER.info(f"Device {self.id}: Starting flash sequence ({flashes} flashes)")

        try:
            # 1. Get the current state to restore later
            _LOGGER.debug(f"Device {self.id}: Querying original state for flash...")
            original_state = await self.get_state()  # Use own method

            if original_state:
                original_on = original_state.get("on")
                original_brightness = original_state.get("brightness")
                original_temperature = original_state.get("color", {}).get("temperature")
                _LOGGER.debug(
                    f"Device {self.id}: Original state for flash: "
                    f"on={original_on}, brightness={original_brightness}, temp={original_temperature}"
                )
            else:
                _LOGGER.warning(
                    f"Device {self.id}: Could not retrieve detailed original state for flash. "
                    "Will attempt basic restore."
                )
                original_on = False  # Default assumption if state is missing

            # 2. Perform the flashing sequence
            _LOGGER.info(f"Device {self.id}: Flashing...")
            for i in range(flashes):
                _LOGGER.debug(f"Device {self.id}: Flash {i + 1}/{flashes}: OFF")
                await self.turn_off()
                await asyncio.sleep(off_duration)

                _LOGGER.debug(f"Device {self.id}: Flash {i + 1}/{flashes}: ON")
                await self.turn_on()
                await asyncio.sleep(on_duration)

            _LOGGER.info(f"Device {self.id}: Flashing sequence complete.")
            success = True  # Mark flashing as successful

        except (DLightTimeoutError, DLightResponseError, DLightError) as e:
            # Log specific errors from client calls
            _LOGGER.error(f"Device {self.id}: A dLight error occurred during flashing: {e}")
            # Restore will still be attempted in finally block
        except Exception:
            _LOGGER.exception(f"Device {self.id}: An unexpected error occurred during flashing")
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
                        _LOGGER.warning(
                            f"Device {self.id}: Original ON/OFF state unknown, leaving light ON after flash."
                        )
                        await self.turn_on()

                    _LOGGER.info(f"Device {self.id}: Original state restoration attempted.")

                except DLightError as e_restore:
                    _LOGGER.error(f"Device {self.id}: Error restoring original state after flash: {e_restore}")
                    success = False  # Mark overall operation as failed if restore fails
                except Exception:
                    _LOGGER.exception(f"Device {self.id}: Unexpected error during state restoration after flash")
                    success = False
            else:
                _LOGGER.warning(f"Device {self.id}: No original state captured, cannot restore.")
                success = False  # Cannot guarantee original state

        return success

    def on_state_change(self, callback: Callable[["DLightDevice", DeviceState, DeviceState], Any]) -> None:
        """Register a listener called whenever device state settles to a new value.

        The callback signature must be::

            def cb(device: DLightDevice, old_state: DeviceState, new_state: DeviceState) -> None: ...

        Both sync and async callables are accepted. Async callbacks are scheduled
        with ``asyncio.ensure_future`` and do not block the caller.

        Callbacks only fire for changes made through **this client instance**.
        Physical button presses or changes from another client are not visible
        unless you poll with ``get_state(force_update=True)``.

        Args:
            callback: The callable to register. Registering the same callable
                twice has no effect.
        """
        if callback not in self._state_listeners:
            self._state_listeners.append(callback)

    def remove_state_listener(self, callback: Callable[["DLightDevice", DeviceState, DeviceState], Any]) -> None:
        """Remove a previously registered state change listener.

        Args:
            callback: The callable to remove. Silently ignored if not registered.
        """
        try:
            self._state_listeners.remove(callback)
        except ValueError:
            pass

    def _clone_state(self, state: DeviceState) -> DeviceState:
        """Shallow-clone state; deep-copies the nested color dict if present."""
        cloned = state.copy()
        if "color" in cloned and isinstance(cloned["color"], dict):
            cloned["color"] = cloned["color"].copy()
        return cloned

    def _emit_state_change(self, old: DeviceState, new: DeviceState) -> None:
        """Fire all registered listeners if state actually changed."""
        if not self._state_listeners or old == new:
            return
        for cb in list(self._state_listeners):
            try:
                res = cb(self, old, new)
                if asyncio.iscoroutine(res):
                    task = asyncio.ensure_future(res)
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)
                    task.add_done_callback(self._handle_listener_task_error)
            except Exception:
                _LOGGER.exception("Device %s: error in state listener %r", self.id, cb)

    def _handle_listener_task_error(self, task: "asyncio.Task[None]") -> None:
        """Log unhandled exceptions from async state listeners."""
        if not task.cancelled() and task.exception():
            _LOGGER.error(
                "Device %s: async state listener raised an exception",
                self.id,
                exc_info=task.exception(),
            )

    def __repr__(self) -> str:
        """Return a developer-friendly representation of the device."""
        return f"<DLightDevice id='{self.id}' ip='{self.ip}'>"

    def __str__(self) -> str:
        """Return a user-friendly representation of the device."""
        return f"dLight Device (ID: {self.id}, IP: {self.ip})"
