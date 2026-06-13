---
hide:
  - navigation
---

<div class="dlight-hero" markdown>
  <picture>
    <source srcset="assets/brand/dark_logo.svg" media="(prefers-color-scheme: dark)">
    <img src="assets/brand/logo.svg" alt="dlight-client" width="480">
  </picture>
</div>

<p class="dlight-tagline">Async Python for dLight smart lamps. Local Wi-Fi. Zero dependencies.</p>

[![PyPI version](https://badge.fury.io/py/dlight-client.svg)](https://badge.fury.io/py/dlight-client)
[![Python Versions](https://img.shields.io/pypi/pyversions/dlight-client.svg)](https://pypi.org/project/dlight-client/)
[![CI](https://github.com/irishsmurf/dlight-client/actions/workflows/python-package.yml/badge.svg)](https://github.com/irishsmurf/dlight-client/actions/workflows/python-package.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/irishsmurf/dlight-client/blob/main/LICENSE)

---

`dlight-client` is a pure-asyncio Python library for discovering and controlling dLight smart lamps entirely on your local network. No cloud relay, no vendor accounts, no third-party packages — just UDP discovery, persistent TCP connections, and a clean async API.

It is the Python layer powering the [dlight-hass](https://github.com/irishsmurf/dlight-hass) Home Assistant integration.

<hr class="dlight-rule"/>

## Why dlight-client?

<div class="grid cards" markdown>

- :material-lan-connect: **Purely local**

    UDP broadcast discovery + TCP control on your LAN. Your lamp data never leaves your network.

- :material-lightning-bolt: **Zero dependencies**

    Pure asyncio and stdlib. `pip install dlight-client` adds nothing else to your environment.

- :material-cached: **State caching**

    `DLightDevice` keeps an internal cache and applies optimistic updates — commands feel instant even on lossy Wi-Fi.

- :material-shield-check: **Robust by design**

    Per-device locking, idle connection eviction, configurable retries with exponential backoff, and optional TLS.

</div>

## Quick start

```python
import asyncio
from dlightclient import AsyncDLightClient, DLightDevice, discover_devices

async def main():
    devices = await discover_devices()           # UDP broadcast, 3 s window
    info = devices[0]

    async with AsyncDLightClient(persistent=True) as client:
        lamp = DLightDevice(info["ip_address"], info["deviceId"], client)
        await lamp.turn_on()
        await lamp.set_brightness(75)
        await lamp.set_color_temperature(3000)   # warm white

asyncio.run(main())
```

[Get started :material-arrow-right:](getting-started.md){ .md-button .md-button--primary }
[API Reference :material-arrow-right:](api/index.md){ .md-button }

<hr class="dlight-rule"/>

## Where to go next

| | |
|---|---|
| :material-rocket-launch: [Getting Started](getting-started.md) | Install, discover devices, send your first command. |
| :material-book-open: [User Guide](user-guide/discovery.md) | Deep dives: discovery, control, connections, error handling. |
| :material-code-tags: [API Reference](api/index.md) | Full reference for every class, method, and exception. |
| :material-wrench: [Architecture](architecture.md) | How the library is layered — for contributors and the curious. |
| :material-source-pull: [Contributing](contributing.md) | Set up a dev environment and send a PR. |
| :material-history: [Changelog](changelog.md) | What's changed in each release. |

!!! tip "dlight-hass users"
    If you use the Home Assistant integration, this is the library it depends on. You don't need to install or configure dlight-client separately — but understanding the API can be handy when troubleshooting.
