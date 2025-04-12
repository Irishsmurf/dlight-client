import unittest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock, call

# --- Import necessary components ---
try:
    # Import from the package structure
    from dlightclient import (
        AsyncDLightClient,
        DLightDevice,
        DLightError,
        DLightTimeoutError,
        DLightResponseError,
        # Import constants if needed for expected values
        STATUS_SUCCESS,
    )
    _IMPORT_SUCCESS = True
    # Define path for patching asyncio.sleep where it's used in device.py
    DEVICE_MODULE_PATH = 'dlightclient.device'

except ImportError as e:
    _IMPORT_SUCCESS = False
    print(f"Could not import from dlightclient package. Ensure it's installed or accessible.")
    print(f"Import Error: {e}")
    # Define dummy classes/variables if import fails
    DEVICE_MODULE_PATH = 'dlightclient.device'
    class DLightError(Exception): pass
    class DLightTimeoutError(DLightError): pass
    class DLightResponseError(DLightError): pass
    class AsyncDLightClient: pass # Dummy needed for type hint
    class DLightDevice: pass # Dummy needed for tests that might run
    STATUS_SUCCESS = "SUCCESS"


@unittest.skipIf(not _IMPORT_SUCCESS, "Skipping device tests due to import failure.")
class TestDLightDevice(unittest.IsolatedAsyncioTestCase):
    """Tests for the DLightDevice abstraction class."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_ip = "192.168.1.55"
        self.test_id = "test-device-id-123"
        # Create a mock AsyncDLightClient instance
        # We use spec=AsyncDLightClient to ensure mocked methods match the real ones
        self.mock_client = AsyncMock(spec=AsyncDLightClient)
        # Instantiate the DLightDevice with the mock client
        self.device = DLightDevice(self.test_ip, self.test_id, self.mock_client)

    # --- Initialization and Property Tests ---

    def test_init_success(self):
        """Test successful initialization."""
        self.assertEqual(self.device.ip, self.test_ip)
        self.assertEqual(self.device.id, self.test_id)
        self.assertIs(self.device._client, self.mock_client)

    def test_init_invalid_ip(self):
        """Test ValueError on empty IP."""
        with self.assertRaisesRegex(ValueError, "IP address cannot be empty"):
            DLightDevice("", self.test_id, self.mock_client)

    def test_init_invalid_id(self):
        """Test ValueError on empty ID."""
        with self.assertRaisesRegex(ValueError, "Device ID cannot be empty"):
            DLightDevice(self.test_ip, "", self.mock_client)

    def test_init_invalid_client(self):
        """Test ValueError on missing client."""
        with self.assertRaisesRegex(ValueError, "AsyncDLightClient instance is required"):
            DLightDevice(self.test_ip, self.test_id, None) # type: ignore

    def test_repr(self):
        """Test the __repr__ method."""
        expected_repr = f"<DLightDevice id='{self.test_id}' ip='{self.test_ip}'>"
        self.assertEqual(repr(self.device), expected_repr)

    def test_str(self):
        """Test the __str__ method."""
        expected_str = f"dLight Device (ID: {self.test_id}, IP: {self.test_ip})"
        self.assertEqual(str(self.device), expected_str)

    # --- Simple Wrapper Method Tests ---

    async def test_turn_on(self):
        """Test the turn_on method."""
        expected_response = {"status": STATUS_SUCCESS}
        self.mock_client.set_light_state.return_value = expected_response

        response = await self.device.turn_on()

        self.mock_client.set_light_state.assert_awaited_once_with(
            self.test_ip, self.test_id, True
        )
        self.assertEqual(response, expected_response)

    async def test_turn_off(self):
        """Test the turn_off method."""
        expected_response = {"status": STATUS_SUCCESS}
        self.mock_client.set_light_state.return_value = expected_response

        response = await self.device.turn_off()

        self.mock_client.set_light_state.assert_awaited_once_with(
            self.test_ip, self.test_id, False
        )
        self.assertEqual(response, expected_response)

    async def test_set_brightness(self):
        """Test the set_brightness method."""
        test_brightness = 75
        expected_response = {"status": STATUS_SUCCESS}
        self.mock_client.set_brightness.return_value = expected_response

        response = await self.device.set_brightness(test_brightness)

        self.mock_client.set_brightness.assert_awaited_once_with(
            self.test_ip, self.test_id, test_brightness
        )
        self.assertEqual(response, expected_response)

    async def test_set_brightness_error_propagates(self):
        """Test that client errors propagate from set_brightness."""
        self.mock_client.set_brightness.side_effect = DLightTimeoutError("Timeout setting brightness")
        with self.assertRaises(DLightTimeoutError):
            await self.device.set_brightness(50)

    async def test_set_color_temperature(self):
        """Test the set_color_temperature method."""
        test_temp = 3500
        expected_response = {"status": STATUS_SUCCESS}
        self.mock_client.set_color_temperature.return_value = expected_response

        response = await self.device.set_color_temperature(test_temp)

        self.mock_client.set_color_temperature.assert_awaited_once_with(
            self.test_ip, self.test_id, test_temp
        )
        self.assertEqual(response, expected_response)

    async def test_get_info(self):
        """Test the get_info method."""
        expected_info = {"status": STATUS_SUCCESS, "deviceModel": "M-Test", "swVersion": "1.2.3"}
        self.mock_client.query_device_info.return_value = expected_info

        response = await self.device.get_info()

        self.mock_client.query_device_info.assert_awaited_once_with(
            self.test_ip, self.test_id
        )
        # get_info should return the full response dict from the client
        self.assertEqual(response, expected_info)

    async def test_get_state(self):
        """Test the get_state method extracts the 'states' dict."""
        state_dict = {"on": True, "brightness": 60, "color": {"temperature": 4500}}
        client_response = {"status": STATUS_SUCCESS, "states": state_dict}
        self.mock_client.query_device_state.return_value = client_response

        response = await self.device.get_state()

        self.mock_client.query_device_state.assert_awaited_once_with(
            self.test_ip, self.test_id
        )
        # get_state should return only the nested 'states' dictionary
        self.assertEqual(response, state_dict)

    async def test_get_state_missing_key(self):
        """Test get_state returns empty dict if 'states' key is missing."""
        client_response = {"status": STATUS_SUCCESS, "other_key": "value"} # Missing 'states'
        self.mock_client.query_device_state.return_value = client_response

        response = await self.device.get_state()

        self.mock_client.query_device_state.assert_awaited_once_with(
            self.test_ip, self.test_id
        )
        self.assertEqual(response, {}) # Expect empty dict

    # --- Flash Method Tests ---

    # Patch asyncio.sleep where it's used inside device.py
    @patch(f'{DEVICE_MODULE_PATH}.asyncio.sleep', new_callable=AsyncMock)
    async def test_flash_success_full_restore(self, mock_sleep):
        """Test flash success with full state restoration."""
        # 1. Setup initial state mock response
        initial_state = {"on": True, "brightness": 80, "color": {"temperature": 3000}}
        state_response = {"status": STATUS_SUCCESS, "states": initial_state}
        self.mock_client.query_device_state.return_value = state_response
        # Mock set commands to just return success
        self.mock_client.set_light_state.return_value = {"status": STATUS_SUCCESS}
        self.mock_client.set_brightness.return_value = {"status": STATUS_SUCCESS}
        self.mock_client.set_color_temperature.return_value = {"status": STATUS_SUCCESS}

        # 2. Call flash
        num_flashes = 2
        on_dur = 0.1
        off_dur = 0.2
        result = await self.device.flash(flashes=num_flashes, on_duration=on_dur, off_duration=off_dur)

        # 3. Assertions
        self.assertTrue(result) # Should return True on success

        # Check initial state query
        self.mock_client.query_device_state.assert_awaited_once_with(self.test_ip, self.test_id)

        # Check flashing calls (off, then on, num_flashes times)
        flash_calls = [
            call(self.test_ip, self.test_id, False), # Flash 1 Off
            call(self.test_ip, self.test_id, True),  # Flash 1 On
            call(self.test_ip, self.test_id, False), # Flash 2 Off
            call(self.test_ip, self.test_id, True),  # Flash 2 On
        ]
        # Filter set_light_state calls *during* flashing (before restore)
        set_state_calls = [c for c in self.mock_client.set_light_state.await_args_list if len(c[0]) == 3]
        # Exclude the final restore call for this check
        self.assertEqual(set_state_calls[:num_flashes*2], flash_calls)

        # Check sleep calls during flashing
        sleep_calls = [call(off_dur), call(on_dur)] * num_flashes
        self.assertEqual(mock_sleep.await_args_list[:num_flashes*2], sleep_calls)

        # Check restoration calls (brightness, temp, then final state)
        self.mock_client.set_brightness.assert_awaited_once_with(self.test_ip, self.test_id, 80)
        self.mock_client.set_color_temperature.assert_awaited_once_with(self.test_ip, self.test_id, 3000)
        # Final set_light_state call should restore original 'on' state (True)
        self.mock_client.set_light_state.assert_awaited_with(self.test_ip, self.test_id, True)
        # Total set_light_state calls = (flashes * 2) + 1 (restore)
        self.assertEqual(self.mock_client.set_light_state.await_count, num_flashes * 2 + 1)


    @patch(f'{DEVICE_MODULE_PATH}.asyncio.sleep', new_callable=AsyncMock)
    async def test_flash_restore_only_on_off(self, mock_sleep):
        """Test flash restoration when only on/off state is available."""
        # Simulate state response missing brightness/color
        initial_state = {"on": False}
        state_response = {"status": STATUS_SUCCESS, "states": initial_state}
        self.mock_client.query_device_state.return_value = state_response
        self.mock_client.set_light_state.return_value = {"status": STATUS_SUCCESS}

        num_flashes = 1
        result = await self.device.flash(flashes=num_flashes)
        self.assertTrue(result)

        # Check initial query
        self.mock_client.query_device_state.assert_awaited_once()
        # Check flashing calls
        self.assertEqual(self.mock_client.set_light_state.await_args_list[0], call(self.test_ip, self.test_id, False)) # Flash Off
        self.assertEqual(self.mock_client.set_light_state.await_args_list[1], call(self.test_ip, self.test_id, True))  # Flash On

        # Check restoration: brightness/temp should NOT be called
        self.mock_client.set_brightness.assert_not_awaited()
        self.mock_client.set_color_temperature.assert_not_awaited()
        # Final state restore should set 'on' to False
        self.mock_client.set_light_state.assert_awaited_with(self.test_ip, self.test_id, False)
        self.assertEqual(self.mock_client.set_light_state.await_count, num_flashes * 2 + 1)

    @patch(f'{DEVICE_MODULE_PATH}.asyncio.sleep', new_callable=AsyncMock)
    async def test_flash_state_query_fails(self, mock_sleep):
        """Test flash behavior when the initial state query fails."""
        # Simulate state query raising an error
        self.mock_client.query_device_state.side_effect = DLightTimeoutError("Timeout getting state")
        # Mock set_light_state just in case the finally block tries a fallback
        self.mock_client.set_light_state.return_value = {"status": STATUS_SUCCESS}

        num_flashes = 1
        # The flash method should catch the error, skip flashing, skip restore, return False
        result = await self.device.flash(flashes=num_flashes)

        # Assertions
        self.assertFalse(result) # Should return False as state couldn't be restored/captured
        self.mock_client.query_device_state.assert_awaited_once() # Query was attempted

        # --- Assert that flashing and restoration calls were SKIPPED ---
        self.mock_client.set_light_state.assert_not_awaited()
        self.mock_client.set_brightness.assert_not_awaited()
        self.mock_client.set_color_temperature.assert_not_awaited()
        mock_sleep.assert_not_awaited()


    @patch(f'{DEVICE_MODULE_PATH}.asyncio.sleep', new_callable=AsyncMock)
    async def test_flash_restore_fails(self, mock_sleep):
        """Test flash returns False if restoration fails."""
        initial_state = {"on": True, "brightness": 50}
        state_response = {"status": STATUS_SUCCESS, "states": initial_state}
        self.mock_client.query_device_state.return_value = state_response
        self.mock_client.set_light_state.return_value = {"status": STATUS_SUCCESS}
        # Simulate brightness restore failing
        self.mock_client.set_brightness.side_effect = DLightResponseError("Failed to set brightness")

        result = await self.device.flash()

        self.assertFalse(result) # Should return False because restore failed
        # Check restore was attempted
        self.mock_client.set_brightness.assert_awaited_once_with(self.test_ip, self.test_id, 50)
        # Other restore steps might or might not run depending on exact finally logic


if __name__ == '__main__':
    unittest.main()

