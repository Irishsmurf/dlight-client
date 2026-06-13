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

### `toggle`

```python
async def toggle() -> CommandResult
```

Toggles the lamp's power state. Uses the cached `on` value to avoid a network
round-trip; falls back to `get_state()` if the cache is empty.

Delegates to `turn_on()` or `turn_off()`, so the cache is updated optimistically
and state change listeners are notified.

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

## Event listeners

### `on_state_change`

```python
def on_state_change(callback: Callable) -> None
```

Registers a callable that is invoked whenever the device state settles to a new value. Both sync and async callables are accepted. Registering the same callable twice has no effect.

**Callback signature:**

```python
def cb(device: DLightDevice, old_state: DeviceState, new_state: DeviceState) -> None: ...
```

| Argument | Type | Description |
|---|---|---|
| `device` | `DLightDevice` | The device whose state changed. |
| `old_state` | `DeviceState` | Snapshot of state before the change. |
| `new_state` | `DeviceState` | Snapshot of state after the change. |

Async callbacks are scheduled with `asyncio.ensure_future` and do not block the calling coroutine. Exceptions raised inside a callback are logged and suppressed — they never propagate to the caller.

```python
def on_change(device, old, new):
    print(f"{device.id}: {old} → {new}")

lamp.on_state_change(on_change)
await lamp.turn_on()
# prints: lamp1: {} → {'on': True}
```

### `remove_state_listener`

```python
def remove_state_listener(callback: Callable) -> None
```

Removes a previously registered listener. Silently ignored if the callable is not registered.

!!! note "Limitation: physical button presses"
    Callbacks only fire for state changes made **through this client instance**. If someone physically toggles the lamp, or another client sends a command, the library has no way to detect it. To observe external changes, poll with `get_state(force_update=True)` and the callback will fire if the returned state differs from the cache. A dedicated `watch()` polling helper is planned ([#43](https://github.com/Irishsmurf/dlight-client/issues/43)).

## State cache semantics

The cache (`_state`) is a `DeviceState` dict that starts empty. It is populated:

- **After any successful state-changing command** — the new values are merged in optimistically before the command is sent.
- **After `get_state(force_update=True)`** — the full state is refreshed from the device.

On failure, the pre-command snapshot is restored so the cache remains consistent with the last known good state.

The cache is never invalidated by external changes (e.g. the lamp being controlled via the physical button or another client). Use `force_update=True` when you need fresh data.

## Exceptions

All exceptions are propagated from `AsyncDLightClient`. See [Exceptions](exceptions.md) for the full hierarchy.
