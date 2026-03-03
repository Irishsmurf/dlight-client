# GEMINI.md - Project Context: dlight-client

This project is an asynchronous Python client library for discovering and controlling dLight smart lamps over a local Wi-Fi network.

## Project Overview

- **Purpose:** Provides both a high-level Python API (`DLightDevice`) and a low-level TCP client (`AsyncDLightClient`) for interacting with dLight smart lamps.
- **Core Technologies:**
  - **Language:** Python 3.7+ (modern `asyncio` patterns used).
  - **Concurrency:** `asyncio` for non-blocking network I/O (UDP discovery and TCP control).
  - **Protocol:** Custom JSON-based protocol. TCP commands are preceded by a 4-byte big-endian length prefix.
  - **Testing:** `unittest` with extensive use of `unittest.mock` (including `AsyncMock` and `IsolatedAsyncioTestCase`).

## Project Architecture

- **`dlightclient/`**: The core package.
  - `client.py`: Implements `AsyncDLightClient`, which manages raw TCP connections, command serialization/deserialization, and length-prefix handling.
  - `device.py`: Implements `DLightDevice`, providing an object-oriented interface for a single lamp (e.g., `turn_on()`, `set_brightness()`, `flash()`).
  - `discovery.py`: Handles UDP broadcast discovery to find devices on the local network.
  - `constants.py`: Centralized configuration for ports (TCP: 3333, UDP Discovery: 9478/9487), default timeouts, and protocol command strings.
  - `exceptions.py`: Defines a custom exception hierarchy rooted in `DLightError`.
  - `cli.py`: A command-line entry point for device discovery, control, and Wi-Fi provisioning.
- **`tests/`**: Contains comprehensive unit tests for all components, mocking network interactions.

## Building and Running

### Development Setup
```bash
# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\activate

# Install in editable mode with development dependencies
pip install -e .
```

### Running Tests
```bash
# Run all tests
python -m unittest discover tests/

# Run a specific test file
python -m unittest tests/test_dlight.py
```

### Using the CLI
```bash
# Discover devices
python -m dlightclient.cli --discover

# Get help
python -m dlightclient.cli --help
```

## Development Conventions

- **Async Everywhere:** All network-related methods in `AsyncDLightClient` and `DLightDevice` are `async` and must be awaited.
- **Error Handling:**
  - Catch `DLightError` for general library errors.
  - Use specific subclasses like `DLightTimeoutError` or `DLightResponseError` for more granular control.
- **Logging:**
  - The library uses a logger named `dlightclient`.
  - In `constants.py`, a base `_LOGGER` is defined.
  - In other modules, loggers are typically initialized as `_LOGGER = logging.getLogger(__name__)`.
- **Protocol Details:**
  - **TCP:** Commands are JSON. Responses are `[4-byte Length][JSON Payload]`.
  - **UDP Discovery:** Send a broadcast hex payload `476f6f676c654e50455f457269635f5761796e65` to port 9478 and listen for JSON responses on 9487.
- **Coding Style:**
  - Strictly follows PEP 8.
  - Comprehensive type hinting is expected for all new functions and methods.
  - Documentation strings (Docstrings) should follow the Google Style.

## Key Constants
- `DEFAULT_TCP_PORT`: 3333
- `DEFAULT_UDP_DISCOVERY_PORT`: 9478
- `DEFAULT_UDP_RESPONSE_PORT`: 9487
- `FACTORY_RESET_IP`: 192.168.4.1 (used for Wi-Fi provisioning in SoftAP mode)
