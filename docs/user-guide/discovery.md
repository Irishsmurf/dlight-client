# Discovering Devices

dlight-client locates lamps on your network using a UDP broadcast probe — the same mechanism used by the dLight mobile app and the dlight-hass Home Assistant integration.

## How it works

`discover_devices()` opens a UDP listener on a response port, then sends a broadcast magic packet to the discovery port. Lamps that receive it reply with a JSON datagram containing their identity information. After the discovery window closes, results are deduplicated by IP address and returned.

```
your machine  →  broadcast UDP:9478  →  [all devices]
your machine  ←  UDP:9487            ←  [each dLight lamp]
```

## Usage

```python
from dlightclient import discover_devices

devices = await discover_devices(
    discovery_duration=3.0,      # how long to listen (seconds)
    response_port=9487,          # port lamps reply to
    discovery_port=9478,         # port lamps listen on
    broadcast_address="255.255.255.255",
)
```

All parameters are optional — the defaults work on a typical home network.

| Parameter | Default | Description |
|---|---|---|
| `discovery_duration` | `3.0` | Seconds to wait for responses. Increase on slow networks. |
| `response_port` | `9487` | UDP port this machine listens on for device replies. |
| `discovery_port` | `9478` | UDP port the discovery probe is sent to. |
| `broadcast_address` | `"255.255.255.255"` | Limited broadcast; works on flat home networks. |

## Returned data

Each entry in the returned list is a `dict` with these keys:

| Key | Type | Description |
|---|---|---|
| `ip_address` | `str` | Assigned by the discovery listener — the lamp's IP. |
| `deviceId` | `str` | Unique device identifier (pass to `DLightDevice`). |
| `deviceModel` | `str` | Hardware model string. |
| `swVersion` | `str` | Firmware version. |
| `hwVersion` | `str` | Hardware revision. |
| `macAddress` | `str` | MAC address. |

Only `ip_address` and `deviceId` are required to control a lamp. The rest are useful for device management UIs.

## Example: quick scan

```python
import asyncio
from dlightclient import discover_devices

async def scan():
    found = await discover_devices(discovery_duration=5.0)
    if not found:
        print("No lamps found — are they on the same subnet?")
        return
    for d in found:
        print(f"  {d['deviceModel']} @ {d['ip_address']}  (id={d['deviceId']})")

asyncio.run(scan())
```

## Firewall and permissions

On Linux, binding a UDP socket to port 9487 may require that the port is not already in use by another process. If you get a `PermissionError`, check that no other instance of the client (or a Home Assistant integration) is already running a listener on that port.

!!! warning "Same subnet required"
    UDP broadcast does not cross router boundaries. Your machine and your lamps must be on the same Layer-2 segment. If you use VLANs or a guest Wi-Fi network, discovery will not find lamps on the other segment.

## mDNS / Zeroconf

UDP broadcast discovery is the current implementation. Support for mDNS / Zeroconf (industry-standard discovery) is tracked as **DL-004** on the [Roadmap](../roadmap.md) and will be additive — existing code using `discover_devices()` will not need changes.
