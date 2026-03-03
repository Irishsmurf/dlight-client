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
    - [3. Performance Optimization](#3-performance-optimization)
  - [Using the Command-Line Tool (CLI)](#using-the-command-line-tool-cli)
- [API Overview](#api-overview)
- [Development and Testing](#development-and-testing)

## Features

*   **Asynchronous:** Built with `asyncio` for efficient, non-blocking network operations.
*   **Device Discovery:** Find dLight devices on your local network using UDP broadcast (`discover_devices`).
*   **High-Level Device Control:** An easy-to-use `DLightDevice` class for object-oriented control of a specific lamp.
*   **Performance Optimized (New):**
    *   **Persistent TCP Connections:** Reuse connections for sequential commands to reduce latency.
    *   **State Caching:** Internal cache in `DLightDevice` reduces redundant network queries.
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
*   Python 3.9 through 3.13 (officially supported).

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
from dlightclient import discover_devices

async def find_devices():
    print("--- Discovering Devices ---")
    devices = await discover_devices(discovery_duration=3.0)

    for i, device_info in enumerate(devices):
        ip = device_info.get('ip_address')
        dev_id = device_info.get('deviceId')
        print(f"  Device {i+1}: ID={dev_id}, IP={ip}")

if __name__ == "__main__":
    asyncio.run(find_devices())
```

#### 2. Controlling a Device

Once you have the `ip_address` and `deviceId`, you can use the high-level `DLightDevice` class for intuitive control.

```python
import asyncio
from dlightclient import AsyncDLightClient, DLightDevice

async def run_example():
    # The client handles the underlying TCP communication
    client = AsyncDLightClient()

    # The device object is the high-level interface
    device = DLightDevice(ip_address="192.168.1.123", device_id="DL12345", client=client)

    # Simple control commands
    await device.turn_on()
    await device.set_brightness(75)
    
    # State caching: get_state() returns cached value by default
    state = await device.get_state() 
    print(f"Current Brightness (cached): {state.get('brightness')}%")

if __name__ == "__main__":
    asyncio.run(run_example())
```

#### 3. Performance Optimization

For applications that need to send many commands in a row, use **Persistent Connections** to eliminate connection setup overhead.

**Option A: Scoped Persistence (Context Manager)**
```python
from dlightclient import AsyncDLightClient, DLightDevice

async with AsyncDLightClient() as client:
    device = DLightDevice(ip_address="192.168.1.123", device_id="DL12345", client=client)
    # Both commands will use the SAME TCP connection
    await device.turn_on()
    await device.set_brightness(50)
```

**Option B: Global Persistence**
```python
client = AsyncDLightClient(persistent=True)
# ... perform operations ...
await client.close() # Explicitly close when finished
```

### Using the Command-Line Tool (CLI)

The package includes a basic CLI for common operations.

```bash
# Discover all devices on the network
python -m dlightclient.cli --discover

# Interact with a specific device using a test sequence
python -m dlightclient.cli --ip 192.168.1.100 --id DL12345
```

## API Overview

*   `dlightclient.discovery.discover_devices`: Uses UDP broadcast to find devices on the network.
*   `dlightclient.client.AsyncDLightClient`: The low-level TCP client. Supports `persistent=True`.
*   `dlightclient.device.DLightDevice`: High-level class. Includes state caching automatically.
*   `dlightclient.exceptions`: Custom exceptions hierarchy rooted in `DLightError`.

## Development and Testing

1.  **Set up a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```

2.  **Install in editable mode:**
    ```bash
    pip install -e .
    ```

3.  **Run tests:**
    ```bash
    python -m unittest discover tests/
    ```
