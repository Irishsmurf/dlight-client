# Controlling Devices

`DLightDevice` is the recommended way to control a lamp. It wraps `AsyncDLightClient` with a per-device stateful interface, caching the last-known state and applying optimistic updates.

## Creating a device

```python
from dlightclient import AsyncDLightClient, DLightDevice

client = AsyncDLightClient()
lamp = DLightDevice(
    ip_address="192.168.1.123",
    device_id="DL12345",
    client=client,
)
```

| Parameter | Type | Description |
|---|---|---|
| `ip_address` | `str` | IP address of the lamp (from `discover_devices`). |
| `device_id` | `str` | Device identifier (from `discover_devices`). |
| `client` | `AsyncDLightClient` | Shared client instance. One client can drive many `DLightDevice` objects. |

## State-changing methods

All methods are `async` and return a `CommandResult` dict on success.

| Method | Parameters | Description |
|---|---|---|
| `turn_on()` | — | Powers the lamp on. |
| `turn_off()` | — | Powers the lamp off. |
| `set_brightness(brightness)` | `int` 0–100 | Sets brightness as a percentage. |
| `set_color_temperature(temperature)` | `int` 2600–6000 | Sets colour temperature in Kelvin. |

```python
await lamp.turn_on()
await lamp.set_brightness(80)
await lamp.set_color_temperature(2700)  # warm, candle-like
```

### Colour temperature range

![Colour temperature range 2600 K to 6000 K](../assets/brand/color-temp.svg)

The lamp accepts integer Kelvin values between **2600 K** (warm amber) and **6000 K** (cool daylight). Values outside this range raise `DLightCommandError`.

## Reading state

### `get_state(force_update=False)`

Returns a `DeviceState` dict describing the lamp's current state.

```python
state = await lamp.get_state()
# {'on': True, 'brightness': 80, 'color': {'temperature': 2700}}

# bypass the cache and query the device directly
state = await lamp.get_state(force_update=True)
```

By default, `get_state()` returns the cached value populated by the most recent command. If no command has been sent yet, it queries the device. Pass `force_update=True` to always query the device.

### `get_info()`

Returns a `DeviceInfo` dict with hardware metadata.

```python
info = await lamp.get_info()
# {'deviceId': 'DL12345', 'deviceModel': '...', 'swVersion': '...', 'hwVersion': '...', 'macAddress': '...'}
```

## State caching and optimistic updates

`DLightDevice` maintains an internal cache (`_state`). When you call `set_brightness(50)`:

1. The cache is updated to `brightness: 50` **before** the network call.
2. The command is sent to the lamp.
3. If the command fails, the previous cache value is restored.

This means `get_state()` returns immediately after a successful command without a second round-trip, and UI state is consistent even while the command is in flight.

## Flash sequence

```python
success = await lamp.flash(
    flashes=3,        # number of on/off cycles
    on_duration=0.3,  # seconds lamp stays on each flash
    off_duration=0.3, # seconds lamp stays off each flash
)
```

`flash()` saves the current state (power, brightness, colour temperature), performs the flash sequence, then restores the saved state. Returns `True` if the full sequence completed, `False` if any step failed (state is still restored on failure).

## Wi-Fi provisioning

For a lamp in SoftAP (factory reset) mode at `192.168.4.1`:

```python
result = await client.connect_to_wifi(
    device_id="DL12345",
    ssid="MyNetwork",
    password="s3cret",
    # target_ip defaults to "192.168.4.1"
    # port defaults to 3333
)
```

This is handled directly on `AsyncDLightClient`, not `DLightDevice`, because the lamp is not yet on your home network when provisioning.
