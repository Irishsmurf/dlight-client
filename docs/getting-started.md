# Getting Started

## Installation

```bash
pip install dlight-client
```

**Python 3.9 through 3.13** are officially supported. No other packages are required.

??? note "Install extras for development or docs"
    ```bash
    pip install "dlight-client[dev]"   # pytest, ruff, flake8
    pip install "dlight-client[docs]"  # mkdocs-material
    ```

---

## Discover devices

`discover_devices()` sends a UDP broadcast and listens for responses for a configurable window (default 3 seconds). It returns a list of dicts — one per discovered lamp.

```python
import asyncio
from dlightclient import discover_devices

async def main():
    devices = await discover_devices(discovery_duration=3.0)
    for d in devices:
        print(d["ip_address"], d["deviceId"], d["deviceModel"])

asyncio.run(main())
```

Each dict contains at minimum `ip_address` and `deviceId` — the two values you need to control a lamp. See [Discovering Devices](user-guide/discovery.md) for the full field reference.

---

## Control a device

Once you have an IP and device ID, use `DLightDevice` for high-level control.

```python
import asyncio
from dlightclient import AsyncDLightClient, DLightDevice

async def main():
    client = AsyncDLightClient()
    lamp = DLightDevice(
        ip_address="192.168.1.123",
        device_id="DL12345",
        client=client,
    )

    await lamp.turn_on()
    await lamp.set_brightness(75)           # 0–100
    await lamp.set_color_temperature(3000)  # 2600–6000 K

    state = await lamp.get_state()
    print(state)  # {'on': True, 'brightness': 75, 'color': {'temperature': 3000}}

asyncio.run(main())
```

`DLightDevice` caches state locally, so `get_state()` doesn't make a network call after the first command. Pass `force_update=True` to bypass the cache.

---

## Persistent connections

By default each command opens a fresh TCP connection. For applications that send many commands in sequence, enable **persistent connections** to reuse the same socket:

=== "Context manager (recommended)"

    ```python
    async with AsyncDLightClient(persistent=True) as client:
        lamp = DLightDevice("192.168.1.123", "DL12345", client)
        await lamp.turn_on()
        await lamp.set_brightness(50)
    # all connections closed automatically on exit
    ```

=== "Manual lifecycle"

    ```python
    client = AsyncDLightClient(persistent=True)
    try:
        lamp = DLightDevice("192.168.1.123", "DL12345", client)
        await lamp.turn_on()
    finally:
        await client.close()
    ```

!!! note "Changed in 1.6.0"
    `async with AsyncDLightClient()` no longer enables persistence automatically.
    Pass `persistent=True` explicitly when you want connection reuse.

---

## Retries on lossy Wi-Fi

For unreliable networks, enable automatic retries. Only transient errors (timeouts and connection failures) are retried — protocol errors never are.

```python
client = AsyncDLightClient(max_retries=2, retry_backoff=0.5)
# first retry after 0.5 s, second after 1.0 s
```

---

## TLS

To encrypt the TCP channel:

```python
import ssl
# trust the server's certificate via the system CA store
client = AsyncDLightClient(ssl=True)

# or supply a custom context (e.g. self-signed certs)
ctx = ssl.create_default_context(cafile="/path/to/ca.pem")
client = AsyncDLightClient(ssl=ctx)
```

---

## What next?

- [Discovering Devices](user-guide/discovery.md) — discovery parameters, returned fields, firewall notes
- [Controlling Devices](user-guide/device-control.md) — all `DLightDevice` methods, state caching, the `flash()` sequence
- [Connection Management](user-guide/connections.md) — pool behaviour, idle timeout, concurrency
- [Error Handling](user-guide/error-handling.md) — exception hierarchy and logging
- [CLI Reference](user-guide/cli.md) — command-line tool usage
