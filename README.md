# python-dlight-client - Async Python Client for dLight API

[![PyPI version](https://badge.fury.io/py/dlight-client.svg)](https://badge.fury.io/py/dlight-client)
[![Python Versions](https://img.shields.io/pypi/pyversions/dlight-client.svg)](https://pypi.org/project/dlight-client/)

This Python package provides an asynchronous (`asyncio`) client library for discovering and controlling dLight smart lamps over a local Wi-Fi network. It allows you to find dLight devices using UDP broadcasts and control them using TCP commands.

## Table of Contents

- [Features](#features)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Usage](#usage)
  - [As a Library](#as-a-library)
    - [1. Discovering Devices](#1-discovering-devices)
    - [2. Controlling a Device](#2-controlling-a-device)
  - [Using the Command-Line Tool (CLI)](#using-the-command-line-tool-cli)
- [API Overview](#api-overview)
- [Development and Testing](#development-and-testing)

## Features

*   **Asynchronous:** Built with `asyncio` for efficient, non-blocking network operations.
*   **Device Discovery:** Find dLight devices on your local network using UDP broadcast (`discover_devices`).
*   **High-Level Device Control:** An easy-to-use `DLightDevice` class for object-oriented control of a specific lamp.
*   **State Control:**
    *   Turn On/Off
    *   Set Brightness (0-100%)
    *   Set Color Temperature (2600K-6000K)
*   **Device Query:**
    *   Get the current state (power, brightness, color).
    *   Get device information (model, firmware version, etc.).
*   **Wi-Fi Provisioning:** Send Wi-Fi credentials to a device in SoftAP mode for initial setup.
*   **Robust Communication:** Handles the dLight TCP protocol (4-byte length prefix + JSON payload) and includes timeouts.
*   **Custom Error Handling:** Specific exceptions for network and device errors (e.g., `DLightTimeoutError`, `DLightResponseError`).
*   **Command-Line Tool:** A convenient CLI for quick discovery and interaction.

## Prerequisites

*   A dLight device connected to your local Wi-Fi network (or in SoftAP mode for initial setup).
*   Python 3.9+

## Installation

```bash
pip install dlight-client
```

## Usage

You can use this package as a library in your Python projects or via the included command-line tool.

### As a Library

Using the library typically involves two steps: discovering devices to get their IP address and ID, and then creating a `DLightDevice` instance to interact with a specific lamp.

#### 1. Discovering Devices

First, use the `discover_devices` function to find lamps on your network.

```python
import asyncio
import logging
from dlightclient import discover_devices

# Configure basic logging
logging.basicConfig(level=logging.INFO)

async def find_devices():
    print("--- Discovering Devices (listening for 3 seconds) ---")
    devices = await discover_devices(discovery_duration=3.0)

    if not devices:
        print("No dLight devices found.")
        return

    print(f"Found {len(devices)} device(s):")
    for i, device_info in enumerate(devices):
        ip = device_info.get('ip_address')
        dev_id = device_info.get('deviceId') or device_info.get('deviceid')
        model = device_info.get('deviceModel')
        print(f"  Device {i+1}: ID={dev_id}, IP={ip}, Model={model}")

if __name__ == "__main__":
    asyncio.run(find_devices())
```

#### 2. Controlling a Device

Once you have the `ip_address` and `deviceId`, you can use the high-level `DLightDevice` class for intuitive control. This is the recommended approach.

```python
import asyncio
import logging
from dlightclient import AsyncDLightClient, DLightDevice, DLightError

# Configure basic logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# --- Replace with your device's details ---
DEVICE_IP = "192.168.1.123"
DEVICE_ID = "DL12345678"
# -----------------------------------------

async def run_example():
    log.info(f"--- Interacting with: {DEVICE_ID} at {DEVICE_IP} ---")

    # The client handles the underlying TCP communication
    client = AsyncDLightClient(default_timeout=5.0)

    # The device object is the high-level interface
    device = DLightDevice(ip_address=DEVICE_IP, device_id=DEVICE_ID, client=client)

    try:
        # Get and print device info
        info = await device.get_info()
        log.info(f"  Device Info: Model={info.get('deviceModel')}, SW={info.get('swVersion')}")

        # Get current state
        state = await device.get_state()
        log.info(f"  Initial State: {state}")

        # Control the light
        log.info("\n-> Turning ON...")
        await device.turn_on()
        await asyncio.sleep(1)

        log.info("-> Setting Brightness to 60%...")
        await device.set_brightness(60)
        await asyncio.sleep(1)

        log.info("-> Setting Color Temperature to 4500K...")
        await device.set_color_temperature(4500)
        await asyncio.sleep(1)

        # Flash the light for notification
        log.info("-> Flashing the light...")
        await device.flash(flashes=2)
        await asyncio.sleep(1) # State is automatically restored

        log.info("-> Turning OFF...")
        await device.turn_off()

    except DLightError as e:
        log.error(f"An error occurred: {e}")
    except Exception as e:
        log.exception("An unexpected error occurred")

if __name__ == "__main__":
    # Ensure you have a running asyncio event loop
    # If using Python 3.7+, asyncio.run() is simplest
    try:
        asyncio.run(run_example())
    except KeyboardInterrupt:
        print("\nExample stopped by user.")
```

### Using the Command-Line Tool (CLI)

The package includes a basic CLI for common operations, which you can run as a module.

```bash
python -m dlightclient.cli [OPTIONS]
```

**Common Commands:**

*   **Discover devices:**
    ```bash
    python -m dlightclient.cli --discover
    ```

*   **Discover devices with a longer duration and verbose logging:**
    ```bash
    python -m dlightclient.cli --discover --discover-duration 5 -vv
    ```

*   **Interact with a specific device (runs a pre-defined sequence):**
    ```bash
    # Replace with your device's actual IP and ID
    python -m dlightclient.cli --ip <IP_ADDRESS> --id <DEVICE_ID>
    ```

*   **Send Wi-Fi credentials (for initial setup):**
    > **Warning:** Use this only when the device is in SoftAP mode (`192.168.4.1`) and your computer is connected to its Wi-Fi network.
    ```bash
    # Replace with your device's ID and your network credentials
    python -m dlightclient.cli --connect-wifi \
      --id <DEVICE_ID> \
      --ssid "YOUR_WIFI_SSID" \
      --password "YOUR_WIFI_PASSWORD"
    ```

*   **Get Help:**
    ```bash
    python -m dlightclient.cli --help
    ```

## API Overview

*   **`dlightclient.discovery.discover_devices`**: Uses UDP broadcast to find devices on the network.
*   **`dlightclient.client.AsyncDLightClient`**: The low-level TCP client that handles sending and receiving raw command data.
*   **`dlightclient.device.DLightDevice`**: The recommended high-level class for controlling a specific device. It wraps an `AsyncDLightClient` instance.
*   **`dlightclient.exceptions`**: Contains custom exceptions like `DLightConnectionError`, `DLightTimeoutError`, and `DLightResponseError` for robust error handling.

## Development and Testing

1.  **Set up a virtual environment:**
    ```sh
    python -m venv .venv
    source .venv/bin/activate  # or .\.venv\Scripts\activate on Windows
    ```

2.  **Install in editable mode:**
    This will install the package from the current directory, allowing you to modify the source code and have the changes immediately reflected.
    ```sh
    pip install -e .
    ```

3.  **Run tests:**
    ```sh
    python -m unittest discover tests/
    ```
