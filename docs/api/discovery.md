# discover_devices / discover_devices_stream

```python
from dlightclient import discover_devices, discover_devices_stream
```

## Signatures

```python
async def discover_devices(
    discovery_duration: float = 3.0,
    response_port: int = 9487,
    discovery_port: int = 9478,
    broadcast_address: str = "255.255.255.255",
) -> list[dict[str, Any]]

async def discover_devices_stream(
    timeout: float = 3.0,
    response_port: int = 9487,
    discovery_port: int = 9478,
    broadcast_address: str = "255.255.255.255",
) -> AsyncGenerator[dict[str, Any], None]
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `discovery_duration` / `timeout` | `float` | `3.0` | Seconds to listen for device responses after sending the probe. |
| `response_port` | `int` | `9487` | UDP port on which this machine listens for device replies. |
| `discovery_port` | `int` | `9478` | UDP port to which the discovery probe is broadcast. |
| `broadcast_address` | `str` | `"255.255.255.255"` | IPv4 broadcast address. Use a subnet-directed address (e.g. `"192.168.1.255"`) on multi-homed hosts. |

## Returns / Yields

*   `discover_devices` returns a `list` of `dict` objects, one per discovered device.
*   `discover_devices_stream` yields `dict` objects as they respond.

Each dict contains:

| Key | Type | Always present | Description |
|---|---|---|---|
| `ip_address` | `str` | Yes | Lamp's IP address (added by the discovery listener). |
| `deviceId` | `str` | Yes | Unique device identifier. |
| `deviceModel` | `str` | Usually | Hardware model string. |
| `swVersion` | `str` | Usually | Firmware version. |
| `hwVersion` | `str` | Usually | Hardware revision. |
| `macAddress` | `str` | Usually | MAC address. |

Results are deduplicated by `ip_address`. If the same lamp responds multiple times within the window, only the first response is processed.

## Errors

Neither function raises for network failures. If a socket cannot be bound (e.g. `response_port` already in use) or broadcast is refused, the error is logged on the `dlightclient.discovery` logger and `discover_devices` returns an empty list / `discover_devices_stream` yields nothing.

## Cleanup

Both functions close their sockets before finishing and wait for the listener to release `response_port`, so a new discovery can start as soon as the previous one returns.

For `discover_devices_stream`, that only happens once the generator finishes or is closed. If you leave the loop early (`break`, `return`, an exception) the generator is not closed — its sockets stay open until it is garbage-collected. Close it explicitly:

```python
from contextlib import aclosing  # Python 3.10+

async with aclosing(discover_devices_stream()) as stream:
    async for d in stream:
        if d["deviceId"] == wanted:
            break
```

On Python 3.9, call `await stream.aclose()` in a `finally` block instead.

## Protocol note

The probe is the fixed ASCII text `476f6f676c654e50455f457269635f5761796e65` (`UDP_DISCOVERY_PAYLOAD`), broadcast to `discovery_port` as-is. It is not hex-decoded: lamps match the 40 characters literally. See [On the wire](../user-guide/discovery.md#on-the-wire). Lamps that recognise it respond with a JSON datagram to `response_port`. This is a proprietary protocol; discovery does not implement mDNS or DNS-SD.

## Examples

### Using `discover_devices` (waits for full duration)

```python
import asyncio
from dlightclient import discover_devices

async def main():
    print("Scanning… (3 s)")
    devices = await discover_devices()
    if not devices:
        print("No lamps found.")
        return
    for d in devices:
        print(f"  {d['deviceModel']:20s} {d['ip_address']:16s} {d['deviceId']}")

asyncio.run(main())
```

### Using `discover_devices_stream` (handles devices incrementally)

```python
import asyncio
from dlightclient import discover_devices_stream

async def main():
    print("Streaming scan…")
    async for d in discover_devices_stream(timeout=5.0):
        print(f"Found: {d['deviceModel']:20s} {d['ip_address']:16s} {d['deviceId']}")

asyncio.run(main())
```
