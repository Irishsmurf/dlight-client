# API Reference

All public names are importable from the top-level `dlightclient` package:

```python
from dlightclient import (
    AsyncDLightClient,
    DLightDevice,
    discover_devices,
    DLightError,
    DLightConnectionError,
    DLightTimeoutError,
    DLightCommandError,
    DLightResponseError,
)
```

## Public surface

| Name | Kind | Description |
|---|---|---|
| [`AsyncDLightClient`](client.md) | class | Low-level TCP client. Handles connection pooling, framing, and retries. |
| [`DLightDevice`](device.md) | class | High-level per-device facade with state cache and optimistic updates. |
| [`discover_devices()`](discovery.md) | coroutine | UDP broadcast scan; returns a list of device dicts. |
| [`DLightError`](exceptions.md) | exception | Base class for all library exceptions. |
| [`DLightConnectionError`](exceptions.md) | exception | TCP connection failed. |
| [`DLightTimeoutError`](exceptions.md) | exception | Operation timed out (subclass of `DLightConnectionError`). |
| [`DLightCommandError`](exceptions.md) | exception | Device rejected the command. |
| [`DLightResponseError`](exceptions.md) | exception | Unexpected or malformed device response. |
| [`DeviceState`](models.md) | TypedDict | `{on, brightness, color}` — lamp state. |
| [`DeviceInfo`](models.md) | TypedDict | `{deviceId, deviceModel, swVersion, hwVersion, macAddress}` — hardware metadata. |
| [`CommandResult`](models.md) | TypedDict | Raw response from a command call. |
| [`ColorState`](models.md) | TypedDict | `{temperature}` — embedded in `DeviceState`. |

## Stability

Names that appear in `dlightclient.__all__` are part of the stable public API. Names prefixed with `_` (such as `_pool`, `_frame`) are private implementation details and may change without notice between minor versions.

Constants (`DEFAULT_TCP_PORT`, `DEFAULT_TIMEOUT`, etc.) are exported from `dlightclient.constants` and are stable.

## Version

```python
import dlightclient
print(dlightclient.__version__)   # e.g. "1.6.1"
```
