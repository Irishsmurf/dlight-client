import unittest
import logging
import sys
from unittest.mock import patch, AsyncMock, MagicMock, call

# --- Import components needed for testing ---
try:
    # Import the main function from the cli module
    from dlightclient import cli

    # Import classes/functions/exceptions that cli.py uses, for mocking specs/assertions
    from dlightclient import (
        AsyncDLightClient,
        DLightDevice,
        discover_devices,
        DLightError,
        DLightTimeoutError,
        DLightConnectionError,
        DLightResponseError,
        DLightCommandError,
        constants,  # Import the constants module
    )

    _IMPORT_SUCCESS = True
    # Define path for patching items *within* the cli module
    CLI_MODULE_PATH = "dlightclient.cli"

except ImportError as e:
    _IMPORT_SUCCESS = False
    print("Could not import from dlightclient package. Ensure it's installed or accessible.")
    print(f"Import Error: {e}")
    # Define dummy classes/variables if import fails
    CLI_MODULE_PATH = "dlightclient.cli"

    class DLightError(Exception):
        pass

    class DLightTimeoutError(DLightError):
        pass

    class DLightConnectionError(DLightError):
        pass

    class DLightResponseError(DLightError):
        pass

    class DLightCommandError(DLightError):
        pass

    class AsyncDLightClient:
        pass

    class DLightDevice:
        pass

    async def discover_devices(*args, **kwargs):
        return []

    class constants:  # Dummy constants class
        FACTORY_RESET_IP = "192.168.4.1"
        STATUS_SUCCESS = "SUCCESS"  # Add dummy constant

    # --- Corrected Dummy CLI ---

    class _DummyCliModule:  # Use a class to act as a module placeholder
        async def main(self, *args, **kwargs):  # Define main as an async method
            print("WARNING: Using dummy cli.main")
            pass

    cli = _DummyCliModule()  # Instantiate the dummy class to provide the 'cli' object
    # --- End Correction ---


@unittest.skipIf(not _IMPORT_SUCCESS, "Skipping CLI tests due to import failure.")
class TestDLightCLI(unittest.IsolatedAsyncioTestCase):
    """Tests for the command-line interface (cli.py)."""

    def setUp(self):
        """Prevent argparse from exiting the test."""
        # Patch ArgumentParser.error to raise exception instead of exiting
        self.patcher_error = patch("argparse.ArgumentParser.error", side_effect=ValueError)
        self.mock_error = self.patcher_error.start()
        self.addCleanup(self.patcher_error.stop)

        # It's often useful to also patch print to check output
        self.patcher_print = patch("builtins.print")
        self.mock_print = self.patcher_print.start()
        self.addCleanup(self.patcher_print.stop)

        # Patch logging to check levels and messages
        self.patcher_log_config = patch(f"{CLI_MODULE_PATH}.logging.basicConfig")
        self.mock_log_config = self.patcher_log_config.start()
        self.patcher_log_get = patch(f"{CLI_MODULE_PATH}.logging.getLogger")
        self.mock_log_get = self.patcher_log_get.start()
        self.mock_lib_logger = MagicMock(name="LibLogger")  # Add names for clarity
        self.mock_script_logger = MagicMock(name="ScriptLogger")

        # Configure getLogger to return specific mocks for library and script
        def get_logger_side_effect(name):
            # --- Debug Print (Keep commented) ---
            # print(f"\nDEBUG [Test Setup]: getLogger called with name='{name}'")
            if name == "dlightclient":
                # print("DEBUG [Test Setup]: Returning mock_lib_logger")
                return self.mock_lib_logger
            # --- Explicitly check for the expected name ---
            elif name == "dlightclient.cli":
                # print("DEBUG [Test Setup]: Returning mock_script_logger")
                return self.mock_script_logger
            else:
                # Return a distinct default mock for any other unexpected logger names
                # print(f"DEBUG [Test Setup]: Returning default MagicMock for name='{name}'")
                return MagicMock(name=f"DefaultMock_{name}")

        self.mock_log_get.side_effect = get_logger_side_effect

        self.addCleanup(self.patcher_log_config.stop)
        self.addCleanup(self.patcher_log_get.stop)

    # --- Test Discovery ---

    @patch(f"{CLI_MODULE_PATH}.discover_devices", new_callable=AsyncMock)
    async def test_cli_discover_default_duration(self, mock_discover):
        """Test `cli.py --discover` calls discover_devices with default duration."""
        mock_discover.return_value = []  # Simulate no devices found
        test_argv = ["cli.py", "--discover"]
        with patch.object(sys, "argv", test_argv):
            await cli.main()
        mock_discover.assert_awaited_once_with(discovery_duration=3.0)  # Check default duration

    @patch(f"{CLI_MODULE_PATH}.discover_devices", new_callable=AsyncMock)
    async def test_cli_discover_custom_duration(self, mock_discover):
        """Test `cli.py --discover --discover-duration` uses specified duration."""
        mock_discover.return_value = []
        test_argv = ["cli.py", "--discover", "--discover-duration", "5.5"]
        with patch.object(sys, "argv", test_argv):
            await cli.main()
        mock_discover.assert_awaited_once_with(discovery_duration=5.5)

    @patch(f"{CLI_MODULE_PATH}.discover_devices", new_callable=AsyncMock)
    async def test_cli_discover_output(self, mock_discover):
        """Test `cli.py --discover` output format."""
        dev1_info = {"ip_address": "1.1.1.1", "deviceId": "dev1", "deviceModel": "M1"}
        dev2_info = {"ip_address": "2.2.2.2", "deviceid": "dev2", "deviceModel": "M2"}  # Test case variation
        mock_discover.return_value = [dev1_info, dev2_info]
        test_argv = ["cli.py", "--discover"]
        with patch.object(sys, "argv", test_argv):
            await cli.main()

        # Check print calls for output formatting
        # Note: This depends heavily on the exact print statements in cli.py
        self.mock_print.assert_any_call("  Device 1: ID=dev1, IP=1.1.1.1, Model=M1")
        self.mock_print.assert_any_call("  Device 2: ID=dev2, IP=2.2.2.2, Model=M2")

    # --- Test Interaction ---

    # Mock the class used in run_interaction
    @patch(f"{CLI_MODULE_PATH}.DLightDevice", spec=DLightDevice)
    # Mock the client class
    @patch(f"{CLI_MODULE_PATH}.AsyncDLightClient", spec=AsyncDLightClient)
    async def test_cli_interaction(self, MockAsyncClient, MockDevice):
        """Test `cli.py --ip --id` calls interaction logic."""
        test_ip = "1.2.3.4"
        test_id = "device-abc"
        test_timeout = 7.0
        test_argv = ["cli.py", "--ip", test_ip, "--id", test_id, "--timeout", str(test_timeout)]

        # Mock the client instance returned
        mock_client_instance = AsyncMock(spec=AsyncDLightClient)
        MockAsyncClient.return_value = mock_client_instance

        # Mock the device instance returned and its methods
        mock_device_instance = AsyncMock(spec=DLightDevice)
        mock_device_instance.ip = test_ip  # Set properties for checks if needed
        mock_device_instance.id = test_id
        MockDevice.return_value = mock_device_instance
        # Mock methods called by run_interaction
        mock_device_instance.get_info.return_value = {"deviceModel": "TestM"}
        mock_device_instance.get_state.return_value = {"on": False}
        mock_device_instance.flash.return_value = True

        with patch.object(sys, "argv", test_argv):
            await cli.main()

        # Assert Client was instantiated correctly
        MockAsyncClient.assert_called_once_with(default_timeout=test_timeout, ssl=None)
        # Assert Device was instantiated correctly
        MockDevice.assert_called_once_with(ip_address=test_ip, device_id=test_id, client=mock_client_instance)
        # Assert methods on the device instance were called
        mock_device_instance.get_info.assert_awaited_once()
        mock_device_instance.get_state.assert_awaited()  # Called multiple times
        mock_device_instance.turn_on.assert_awaited_once()
        mock_device_instance.set_brightness.assert_awaited_once_with(30)
        mock_device_instance.set_color_temperature.assert_awaited_once_with(5000)
        mock_device_instance.flash.assert_awaited_once()
        mock_device_instance.turn_off.assert_awaited_once()

    # Mock higher level function
    @patch(f"{CLI_MODULE_PATH}.run_interaction", new_callable=AsyncMock)
    @patch(f"{CLI_MODULE_PATH}.discover_devices", new_callable=AsyncMock)
    @patch(f"{CLI_MODULE_PATH}.AsyncDLightClient", spec=AsyncDLightClient)
    async def test_cli_discover_first(self, MockAsyncClient, mock_discover, mock_run_interaction):
        """Test `cli.py --discover --first` interacts with the first device."""
        dev1_ip = "1.1.1.1"
        dev1_id = "dev1"
        dev1_info = {"ip_address": dev1_ip, "deviceId": dev1_id, "deviceModel": "M1"}
        mock_discover.return_value = [dev1_info]  # Simulate one device found
        mock_client_instance = AsyncMock()
        MockAsyncClient.return_value = mock_client_instance

        test_argv = ["cli.py", "--discover", "--first"]
        with patch.object(sys, "argv", test_argv):
            await cli.main()

        mock_discover.assert_awaited_once()
        MockAsyncClient.assert_called_once_with(default_timeout=5.0, ssl=None)  # Default timeout
        # Assert run_interaction was called with the correct client and details
        mock_run_interaction.assert_awaited_once_with(mock_client_instance, dev1_ip, dev1_id)

    # Mock higher level function
    @patch(f"{CLI_MODULE_PATH}.run_interaction", new_callable=AsyncMock)
    @patch(f"{CLI_MODULE_PATH}.discover_devices", new_callable=AsyncMock)
    async def test_cli_discover_first_no_devices(self, mock_discover, mock_run_interaction):
        """Test `cli.py --discover --first` does nothing if no devices found."""
        mock_discover.return_value = []  # Simulate no devices found

        test_argv = ["cli.py", "--discover", "--first"]
        with patch.object(sys, "argv", test_argv):
            await cli.main()

        mock_discover.assert_awaited_once()
        mock_run_interaction.assert_not_awaited()  # Interaction should be skipped

    async def test_cli_interaction_missing_arg(self):
        """Test interaction fails if only --ip or --id is provided."""
        test_argv_ip = ["cli.py", "--ip", "1.2.3.4"]
        test_argv_id = ["cli.py", "--id", "device-abc"]

        with patch.object(sys, "argv", test_argv_ip):
            # Check for argparse error we patched
            with self.assertRaises(ValueError):
                await cli.main()
            self.mock_error.assert_called_with(
                "Both --ip and --id are required for interaction (unless using --discover --first)."
            )

        self.mock_error.reset_mock()
        with patch.object(sys, "argv", test_argv_id):
            with self.assertRaises(ValueError):
                await cli.main()
            self.mock_error.assert_called_with(
                "Both --ip and --id are required for interaction (unless using --discover --first)."
            )

    # --- Test Wifi Connect ---

    @patch(f"{CLI_MODULE_PATH}.AsyncDLightClient", spec=AsyncDLightClient)
    async def test_cli_wifi_connect(self, MockAsyncClient):
        """Test `cli.py --connect-wifi` calls client method."""
        test_id = "wifi-dev"
        test_ssid = "MyNetwork"
        test_pw = "S3cr3t"
        test_argv = ["cli.py", "--connect-wifi", "--id", test_id, "--ssid", test_ssid, "--password", test_pw]

        mock_client_instance = AsyncMock(spec=AsyncDLightClient)
        # Corrected line: Use constants.STATUS_SUCCESS
        mock_client_instance.connect_to_wifi.return_value = {"status": constants.STATUS_SUCCESS}
        MockAsyncClient.return_value = mock_client_instance

        with patch.object(sys, "argv", test_argv):
            await cli.main()

        MockAsyncClient.assert_called_once_with(default_timeout=5.0, ssl=None)  # Default timeout
        mock_client_instance.connect_to_wifi.assert_awaited_once_with(test_id, test_ssid, test_pw)

    async def test_cli_wifi_connect_missing_args(self):
        """Test wifi connect fails if args are missing."""
        base_argv = ["cli.py", "--connect-wifi"]
        missing_id = base_argv + ["--ssid", "a", "--password", "b"]
        missing_ssid = base_argv + ["--id", "a", "--password", "b"]
        missing_pw = base_argv + ["--id", "a", "--ssid", "b"]

        expected_error_msg = "--connect-wifi requires --id, --ssid, and --password."

        for argv in [missing_id, missing_ssid, missing_pw]:
            self.mock_error.reset_mock()
            with patch.object(sys, "argv", argv):
                with self.assertRaises(ValueError):
                    await cli.main()
                self.mock_error.assert_called_with(expected_error_msg)

    async def test_cli_verbose_default(self):
        """Test default verbosity sets WARNING level on library."""
        test_argv = ["cli.py"]  # No action needed
        with patch.object(sys, "argv", test_argv):
            await cli.main()

        # Check setLevel was called with WARNING on library logger
        self.mock_lib_logger.setLevel.assert_any_call(logging.WARNING)
        # Script logger might default to INFO or WARNING depending on basicConfig, check that DEBUG wasn't set
        self.assertNotIn(call(logging.DEBUG), self.mock_script_logger.setLevel.call_args_list)

    # --- Test No Action ---


if __name__ == "__main__":
    unittest.main()
