# python-dlight-client - Async Python Client for dLight API

[![PyPI version](https://badge.fury.io/py/dlight-client.svg)](https://badge.fury.io/py/dlight-client)
[![Python Versions](https://img.shields.io/pypi/pyversions/dlight-client.svg)](https://pypi.org/project/dlight-client/)

This Python package provides an asynchronous client library (`asyncio`) for interacting with the dLight smart lamp API, based on the documentation dated 2023-01-04. It allows discovering dLight devices using UDP broadcasts and controlling them over a local Wi-Fi network using TCP commands.

The library has been refactored for better organization:
* `dlightclient.client`: Contains the `AsyncDLightClient` for TCP control.
* `dlightclient.discovery`: Provides the `discover_devices` function for UDP discovery.
* `dlightclient.exceptions`: Defines custom error types.
* `dlightclient.constants`: Holds shared constants.
* `dlightclient.cli`: Offers a basic command-line interface.

## Features

* **Asynchronous:** Built with `asyncio` for non-blocking network operations.
* **Discover Devices:** Find dLight devices on the local network via UDP broadcast (`discover_devices`).
* **Control Light State:**
    * Turn On/Off (`AsyncDLightClient.set_light_state`)
    * Set Brightness (0-100%) (`AsyncDLightClient.set_brightness`)
    * Set Color Temperature (2600K-6000K) (`AsyncDLightClient.set_color_temperature`)
* **Query Device:**
    * Get current state (`AsyncDLightClient.query_device_state`).
    * Get device information (`AsyncDLightClient.query_device_info`).
* **Wi-Fi Provisioning:** Support for sending Wi-Fi credentials (`AsyncDLightClient.connect_to_wifi` - typically used when device is in SoftAP mode).
* **Robust Communication:** Handles the specific dLight TCP response format (4-byte length prefix + JSON payload) and includes timeouts.
* **Error Handling:** Custom exceptions for specific error conditions (e.g., `DLightError`, `DLightTimeoutError`, `DLightConnectionError`).
* **Command-Line Tool:** A basic CLI (`cli.py`) for discovery and interaction.

## Prerequisites

* A dLight device connected to your local Wi-Fi network (or in SoftAP mode for initial setup).
* Python 3.9+ (due to `asyncio` features used)

## Installation

```bash
pip install dlight-client
```

## Usage

You can use this package as a library in your Python projects or via the included command-line tool.As a LibraryFirst, discover your dLight device(s) to get their IP address and Device ID. Then, use these details to send commands via an AsyncDLightClient instance within an async function.import asyncio

```py
import logging
import time # For delays in example

# Import the public interface
from dlightclient import (
    AsyncDLightClient,
    discover_devices,
    DLightError,
    DLightTimeoutError,
    DLightConnectionError
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

async def run_example():
    log.info("--- Async dLight Python Client Example ---")

    log.info("\n--- Discovering Devices (3 seconds) ---")
    try:
        # Use the discover_devices function directly
        devices = await discover_devices(discovery_duration=3.0)
    except Exception as e:
         log.exception(f"Discovery failed with an unexpected error: {e}")
         devices = []

    if not devices:
        log.warning("\nNo dLight devices found on the network.")
        log.warning("Ensure dLight is powered on and connected to the same network.")
        # Add Wi-Fi connect example if needed (see cli.py or client.py for details)
        return

    # --- Interact with the first discovered device ---
    target_device = devices[0]
    target_ip = target_device.get('ip_address')
    # Handle potential case difference for deviceId from discovery
    device_id = target_device.get('deviceId') or target_device.get('deviceid')

    if not target_ip or not device_id:
        log.error(f"Could not get IP address or Device ID from discovered device: {target_device}")
        return

    log.info(f"\n--- Interacting with: {device_id} at {target_ip} ---")
    client = AsyncDLightClient(default_timeout=5.0) # Adjust timeout if needed

    try:
        # Query Info
        log.info("\nQuerying Device Info...")
        info = await client.query_device_info(target_ip, device_id)
        log.info(f"  Info: {info}")

        # Query State
        log.info("\nQuerying Device State...")
        state_resp = await client.query_device_state(target_ip, device_id)
        current_state = state_resp.get('states', {})
        log.info(f"  Current State: {current_state}")

        # Turn On
        log.info("\nTurning Light ON...")
        await client.set_light_state(target_ip, device_id, True)
        await asyncio.sleep(0.5) # Give device time to react

        # Set Brightness
        log.info("\nSetting Brightness to 60%...")
        await client.set_brightness(target_ip, device_id, 60)
        await asyncio.sleep(0.5)

        # Set Color Temperature
        log.info("\nSetting Color Temperature to 4500K...")
        await client.set_color_temperature(target_ip, device_id, 4500)
        await asyncio.sleep(0.5)

        # Query State Again
        log.info("\nQuerying Device State Again...")
        state_resp = await client.query_device_state(target_ip, device_id)
        new_state = state_resp.get('states', {})
        log.info(f"  New State: {new_state}")

        # Turn Off
        log.info("\nTurning Light OFF...")
        await client.set_light_state(target_ip, device_id, False)

    except (DLightTimeoutError, DLightConnectionError) as e:
        log.error(f"\n--- Network Error during interaction ---")
        log.error(e)
    except DLightError as e:
        log.error(f"\n--- A dLight error occurred during interaction ---")
        log.error(e)
    except ValueError as e:
         log.error(f"\n--- Invalid value provided during interaction ---")
         log.error(e)
    except Exception as e:
         log.exception(f"\n--- An unexpected error occurred during interaction ---")


if __name__ == "__main__":
    try:
        asyncio.run(run_example())
    except KeyboardInterrupt:
        print("Example stopped.")
```

###  Using the Command-Line Tool (cli.py)

The package includes a basic command-line tool for common operations. You can run it as a module:

```py
python -m dlightclient.cli [OPTIONS]
```

### Common Commands:

- **Discover devices:**
    - `python -m dlightclient.cli --discover`
    - `python -m dlightclient.cli --discover --discover-duration <DURATION>`
- **Interact with a device (requires IP and ID):** 
    - *Replace <IP_ADDRESS> and <DEVICE_ID> with actual values*
    - `python -m dlightclient.cli --ip <IP_ADDRESS> --id <DEVICE_ID>`
- **Send Wi-Fi credentials (for setup):**
    - *Warning: Use this only when the device is in SoftAP mode and your computer is connected to its network.*
    - ```
        # Replace <DEVICE_ID>, <YOUR_WIFI_SSID>, <YOUR_WIFI_PASSWORD>
    	python -m dlightclient.cli --connect-wifi --id <DEVICE_ID> --ssid "<YOUR_WIFI_SSID>" --password "<YOUR_WIFI_PASSWORD>"
      ```
- **Get Help:**
    - python -m dlightclient.cli --help
- **Increase Verbosity:**
    - Use -v for INFO level logging, -vv for DEBUG level.# Discover with DEBUG logging
    - `python -m dlightclient.cli --discover -vv`

# Interact with DEBUG logging
`python -m dlightclient.cli --ip <IP_ADDRESS> --id <DEVICE_ID> -vv`

# API Details
- **TCP Commands:** Sent to device IP on port 3333 (default).  Handled by `AsyncDLightClient.`
- **UDP Discovery:** Broadcast sent to 255.255.255.255 (default) on port 9478. Responses listened for on port 9487. Handled by `discover_devices`.

# Development and Testing

1. Setup Virtual Environment:
```sh
python -m venv .venv
source .venv/bin/activate  # or .\.venv\Scripts\activate on Windows
```

2. Install Dependencies (if any beyond standard library):
```sh
# Add requirements-dev.txt if needed for linters, pytest, etc.
# pip install -r requirements-dev.txt
```

3. Install in Editable Mode:
```sh
pip install -e .
```

# Testing
Note: The test suite (tests/test_dlight.py) needs to be updated to reflect the refactored code structure (module paths for patching, imports, etc.).Once updated, you can run tests using:python -m unittest discover -s tests/ -p 'test_*.py'
# Or potentially targeting the specific test file if structure changed:
# python -m unittest tests.test_dlight
