# python-dlight-client - Python Client for dLight API

- [![PyPI version](https://badge.fury.io/py/dlight-client.svg)](https://badge.fury.io/py/dlight-client) 
- [![Python Versions](https://img.shields.io/pypi/pyversions/dlight-client.svg)](https://pypi.org/project/dlight-client/) 

This Python package provides a client library for interacting with the dLight smart lamp API, based on the documentation dated 2023-01-04. It allows controlling dLight devices over a local Wi-Fi network using TCP commands and discovering devices using UDP broadcasts.


## Features

* Discover dLight devices on the local network via UDP broadcast (`discover_devices`).
* Control dLight state:
    * Turn On/Off (`set_light_state`)
    * Set Brightness (0-100%) (`set_brightness`)
    * Set Color Temperature (2600K-6000K) (`set_color_temperature`)
* Query current device state (`query_device_state`).
* Query device information (`query_device_info`).
* Support for direct Wi-Fi provisioning (`connect_to_wifi` - use with caution).
* Handles the specific dLight TCP response format (4-byte length prefix + JSON payload).
* Custom exceptions for error handling (e.g., `DLightError`, `DLightTimeoutError`).

## Prerequisites

* A dLight device connected to your local Wi-Fi network.
* Python 3.7+

## Installation

```bash
pip install dlight-client
```

## Usage
First, discover your dLight device(s) to get their IP address and Device ID. Then, use these details to send commands via a DLightClient instance.

```py
import time
import logging
from dlightclient.dlight import DLightClient, DLightError # Adjust import if needed

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

def main():
    log.info("--- dLight Python Client Example ---")
    client = DLightClient()

    log.info("\n--- Discovering Devices (3 seconds) ---")
    try:
        # Use the static method for discovery
        devices = DLightClient.discover_devices(discovery_duration=3.0)
    except Exception as e:
         log.exception(f"Discovery failed with an unexpected error: {e}")
         devices = []

    if not devices:
        log.warning("\nNo dLight devices found on the network.")
        log.warning("Ensure dLight is powered on and connected to the same network.")
        log.warning("If setting up for the first time, you might need to use")
        log.warning("`client.connect_to_wifi(...)` while connected to its SoftAP.")
        # Example placeholder for Wi-Fi connect (DO NOT RUN UNLESS NEEDED):
        # try:
        #     log.info("\nAttempting Wi-Fi connection (Example - REPLACE details)...")
        #     # You need the device ID from the SoftAP SSID (e.g., GLAMP_<DEVICE_ID>)
        #     wifi_resp = client.connect_to_wifi("YOUR_DEVICE_ID", "Your_WiFi_SSID", "Your_WiFi_Password")
        #     log.info(f"Wi-Fi connect response: {wifi_resp}")
        #     log.info("Wait for device to connect and try discovery again.")
        # except DLightError as e:
        #     log.error(f"Wi-Fi connect failed: {e}")
        return

    # --- Interact with the first discovered device ---
    target_device = devices[0]
    target_ip = target_device['ip_address']
    # Ensure key exists and handle potential case difference from discovery
    device_id = target_device.get('deviceId') or target_device.get('deviceid')
    if not device_id:
        log.error(f"Could not find 'deviceId' in discovered device info: {target_device}")
        return

    log.info(f"\n--- Interacting with: {device_id} at {target_ip} ---")

    try:
        # Query Info
        log.info("\nQuerying Device Info...")
        info = client.query_device_info(target_ip, device_id)
        log.info(f"  Info: {info}")

        # Query State
        log.info("\nQuerying Device State...")
        state_resp = client.query_device_state(target_ip, device_id)
        current_state = state_resp.get('states', {})
        log.info(f"  Current State: {current_state}")

        # Turn On
        log.info("\nTurning Light ON...")
        on_resp = client.set_light_state(target_ip, device_id, True)
        log.info(f"  Response: {on_resp}")
        time.sleep(0.5) # Give device time to react

        # Set Brightness
        log.info("\nSetting Brightness to 60%...")
        bright_resp = client.set_brightness(target_ip, device_id, 60)
        log.info(f"  Response: {bright_resp}")
        time.sleep(0.5)

        # Set Color Temperature
        log.info("\nSetting Color Temperature to 4500K...")
        temp_resp = client.set_color_temperature(target_ip, device_id, 4500)
        log.info(f"  Response: {temp_resp}")
        time.sleep(0.5)

        # Query State Again
        log.info("\nQuerying Device State Again...")
        state_resp = client.query_device_state(target_ip, device_id)
        current_state = state_resp.get('states', {})
        log.info(f"  New State: {current_state}")

        # Turn Off
        log.info("\nTurning Light OFF...")
        off_resp = client.set_light_state(target_ip, device_id, False)
        log.info(f"  Response: {off_resp}")

    except DLightError as e:
        log.error(f"\n--- An error occurred during interaction ---")
        log.error(e)
    except ValueError as e:
         log.error(f"\n--- Invalid value provided ---")
         log.error(e)
    except Exception as e:
         log.exception(f"\n--- An unexpected error occurred ---") # Log full traceback

if __name__ == "__main__":
    main()
```

## API Details

- TCP Commands: Sent to device IP on port `3333`.
- UDP Discovery: Broadcast sent to `255.255.255.255` (default) on port `9478`. Responses listened for on port `9487`.

## Development and Testing

```bash
python -m venv .venv
source .venv/bin/activate  # or .\.venv\Scripts\activate on Windows
pip install -r requirements-dev.txt # If you create one for build, twine, pytest etc.
pip install -e . # Install package in editable mode
```

## Testing

```sh
python -m unittest discover tests/
```
