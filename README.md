<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/dark_logo.svg">
  <img alt="dlight-client" src="docs/assets/brand/logo.svg" height="72">
</picture>

> Async Python library for discovering and controlling dLight smart lamps over local Wi-Fi.
> Pure asyncio. Zero dependencies.

[![PyPI version](https://badge.fury.io/py/dlight-client.svg)](https://badge.fury.io/py/dlight-client)
[![Python Versions](https://img.shields.io/pypi/pyversions/dlight-client.svg)](https://pypi.org/project/dlight-client/)
[![CI](https://github.com/irishsmurf/dlight-client/actions/workflows/python-package.yml/badge.svg)](https://github.com/irishsmurf/dlight-client/actions/workflows/python-package.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## Install

```bash
pip install dlight-client
```

Python 3.9 – 3.13. No other packages required.

## Quick start

```python
import asyncio
from dlightclient import AsyncDLightClient, DLightDevice, discover_devices

async def main():
    devices = await discover_devices()        # UDP broadcast, 3 s window
    info = devices[0]

    async with AsyncDLightClient(persistent=True) as client:
        lamp = DLightDevice(info["ip_address"], info["deviceId"], client)
        await lamp.turn_on()
        await lamp.set_brightness(75)
        await lamp.set_color_temperature(3000) # warm white

asyncio.run(main())
```

## Features

- **Device discovery** — UDP broadcast scan; finds all lamps on the local network
- **Persistent connections** — connection pool with per-device locking and idle eviction
- **State caching** — optimistic updates with automatic rollback on failure
- **Automatic retries** — exponential backoff on transient errors (`max_retries`, `retry_backoff`)
- **Optional TLS** — pass `ssl=True` or a custom `ssl.SSLContext`
- **Typed models** — `TypedDict` classes for `DeviceState`, `DeviceInfo`, `CommandResult`
- **CLI** — `python -m dlightclient.cli --discover` for quick exploration
- **Wi-Fi provisioning** — send credentials to a lamp in SoftAP mode

## CLI

```bash
# Discover all lamps
python -m dlightclient.cli --discover

# Interact with a specific lamp
python -m dlightclient.cli --ip 192.168.1.123 --id DL12345

# Debug with verbose output
python -m dlightclient.cli --ip 192.168.1.123 --id DL12345 -vv
```

## Documentation

Full documentation at **https://irishsmurf.github.io/dlight-client/**

| | |
|---|---|
| [Getting Started](https://irishsmurf.github.io/dlight-client/getting-started/) | Install, discover, first commands |
| [User Guide](https://irishsmurf.github.io/dlight-client/user-guide/discovery/) | Discovery, control, connections, error handling |
| [API Reference](https://irishsmurf.github.io/dlight-client/api/) | Full class and method reference |
| [Architecture](https://irishsmurf.github.io/dlight-client/architecture/) | Internals for contributors |
| [Contributing](CONTRIBUTING.md) | Dev setup, testing, PR conventions |
| [Changelog](CHANGELOG.md) | What's changed in each release |

## Upgrade cadence

Patch releases (`1.x.Y`) are made as needed for bug fixes and security patches.
Minor releases (`1.X.0`) ship new features and are backwards compatible.
Major releases (`X.0.0`) may include breaking changes and are announced in advance via GitHub Issues.

## License

MIT — see [LICENSE](LICENSE).
