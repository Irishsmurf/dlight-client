# discover_devices

```python
from dlightclient import discover_devices
```

## Signature

```python
async def discover_devices(
    discovery_duration: float = 3.0,
    response_port: int = 9487,
    discovery_port: int = 9478,
    broadcast_address: str = "255.255.255.255",
) -> list[dict[str, Any]]
```

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `discovery_duration` | `float` | `3.0` | Seconds to listen for device responses after sending the probe. |
| `response_port` | `int` | `9487` | UDP port on which this machine listens for device replies. |
| `discovery_port` | `int` | `9478` | UDP port to which the discovery probe is broadcast. |
| `broadcast_address` | `str` | `"255.255.255.255"` | IPv4 broadcast address. Use a subnet-directed address (e.g. `"192.168.1.255"`) on multi-homed hosts. |

## Returns

A `list` of `dict` objects, one per discovered device. Each dict contains:

| Key | Type | Always present | Description |
|---|---|---|---|
| `ip_address` | `str` | Yes | Lamp's IP address (added by the discovery listener). |
| `deviceId` | `str` | Yes | Unique device identifier. |
| `deviceModel` | `str` | Usually | Hardware model string. |
| `swVersion` | `str` | Usually | Firmware version. |
| `hwVersion` | `str` | Usually | Hardware revision. |
| `macAddress` | `str` | Usually | MAC address. |

Results are deduplicated by `ip_address`. If the same lamp responds multiple times within the window, only the first response is included.

## Raises

| Exception | When |
|---|---|
| `OSError` | The UDP socket cannot be bound (e.g. port already in use). Not a `DLightError`. |

## Protocol note

The probe is a fixed hex-encoded magic payload broadcast to `discovery_port`. Lamps that recognise it respond with a JSON datagram to `response_port`. This is a proprietary protocol; `discover_devices` does not implement mDNS or DNS-SD.

## Example

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
