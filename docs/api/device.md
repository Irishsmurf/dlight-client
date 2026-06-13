# DLightDevice

```python
from dlightclient import DLightDevice
```

A stateful, per-device facade over `AsyncDLightClient`. Maintains an internal state cache, applies optimistic updates before network calls, and rolls back on failure. This is the recommended way to control a lamp.

## Constructor

```python
DLightDevice(
    ip_address: str,
    device_id: str,
    client: AsyncDLightClient,
)
```

| Parameter | Type | Description |
|---|---|---|
| `ip_address` | `str` | Lamp's IP address. |
| `device_id` | `str` | Lamp's device identifier. |
| `client` | `AsyncDLightClient` | Shared client. One client can back many `DLightDevice` instances. |

## Properties

| Property | Type | Description |
|---|---|---|
| `ip` | `str` (read-only) | The lamp's IP address. |
| `id` | `str` (read-only) | The lamp's device ID. |

## Methods

### `turn_on`

```python
async def turn_on() -> CommandResult
```

Powers the lamp on. Updates the cache optimistically.

### `turn_off`

```python
async def turn_off() -> CommandResult
```

Powers the lamp off. Updates the cache optimistically.

### `set_brightness`

```python
async def set_brightness(brightness: int) -> CommandResult
```

Sets brightness as a percentage (0–100). Updates the cache optimistically.

**Raises:** `DLightCommandError` if `brightness` is out of range; cache is rolled back.

### `set_color_temperature`

```python
async def set_color_temperature(temperature: int) -> CommandResult
```

Sets colour temperature in Kelvin (2600–6000). Updates the cache optimistically.

**Raises:** `DLightCommandError` if `temperature` is out of range; cache is rolled back.

### `get_state`

```python
async def get_state(force_update: bool = False) -> DeviceState
```

Returns the lamp's current state as a `DeviceState` dict.

- If the cache is populated and `force_update=False`, returns the cached value without a network call.
- If the cache is empty (no command has been sent yet), or `force_update=True`, queries the device.

```python
state = await lamp.get_state()
# {'on': True, 'brightness': 75, 'color': {'temperature': 3000}}
```

### `get_info`

```python
async def get_info() -> DeviceInfo
```

Queries the device for hardware metadata. Always makes a network call (not cached).

```python
info = await lamp.get_info()
# {'deviceId': '...', 'deviceModel': '...', 'swVersion': '...', 'hwVersion': '...', 'macAddress': '...'}
```

### `flash`

```python
async def flash(
    flashes: int = 3,
    on_duration: float = 0.3,
    off_duration: float = 0.3,
) -> bool
```

Blink the lamp `flashes` times, then restore the previous state (power, brightness, colour temperature).

| Parameter | Default | Description |
|---|---|---|
| `flashes` | `3` | Number of on/off cycles. |
| `on_duration` | `0.3` | Seconds the lamp stays on during each flash. |
| `off_duration` | `0.3` | Seconds the lamp stays off during each flash. |

Returns `True` if the full sequence completed successfully. Returns `False` if any step failed; the previous state is still restored even on partial failure.

## State cache semantics

The cache (`_state`) is a `DeviceState` dict that starts empty. It is populated:

- **After any successful state-changing command** — the new values are merged in optimistically before the command is sent.
- **After `get_state(force_update=True)`** — the full state is refreshed from the device.

On failure, the pre-command snapshot is restored so the cache remains consistent with the last known good state.

The cache is never invalidated by external changes (e.g. the lamp being controlled via the physical button or another client). Use `force_update=True` when you need fresh data.

## Exceptions

All exceptions are propagated from `AsyncDLightClient`. See [Exceptions](exceptions.md) for the full hierarchy.
