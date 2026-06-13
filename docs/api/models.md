# Models

dlight-client uses `TypedDict` classes to represent structured data returned from device calls. These provide IDE autocompletion and static type-checking support without imposing runtime overhead.

All models are importable from `dlightclient.models` (or directly from `dlightclient`):

```python
from dlightclient import LightScene
from dlightclient.models import DeviceState, DeviceInfo, CommandResult, ColorState
```

## `LightScene`

```python
@dataclass(frozen=True)
class LightScene:
    brightness: int   # 0–100
    temperature: int  # 2600–6000 K
```

An immutable brightness + colour temperature preset. Pass it to `DLightDevice.apply_scene()`.

Four built-in scenes are provided as class attributes:

| Name | `brightness` | `temperature` |
|---|---|---|
| `LightScene.READING` | 70 | 4000 K |
| `LightScene.EVENING` | 30 | 2700 K |
| `LightScene.DAYLIGHT` | 100 | 6000 K |
| `LightScene.FOCUS` | 100 | 5000 K |

Custom scenes can be constructed inline:

```python
MOVIE_NIGHT = LightScene(brightness=20, temperature=2700)
await lamp.apply_scene(MOVIE_NIGHT)
```

## `ColorState`

```python
class ColorState(TypedDict, total=False):
    temperature: int   # colour temperature in Kelvin (2600–6000)
```

Embedded inside `DeviceState.color`.

## `DeviceState`

```python
class DeviceState(TypedDict, total=False):
    on:         bool        # True = on, False = off
    brightness: int         # 0–100
    color:      ColorState  # {'temperature': 3000}
```

Returned by `DLightDevice.get_state()` and embedded in `CommandResult.states`.

All fields are optional (`total=False`) — the device may not include every field in every response.

**Example:**

```python
state = await lamp.get_state()
if state.get("on"):
    temp = state.get("color", {}).get("temperature", 4000)
    print(f"Lamp is on at {temp} K, brightness {state.get('brightness')}%")
```

## `DeviceInfo`

```python
class DeviceInfo(TypedDict, total=False):
    deviceId:    str   # unique device identifier
    deviceModel: str   # hardware model string
    swVersion:   str   # firmware version
    hwVersion:   str   # hardware revision
    macAddress:  str   # MAC address
```

Returned by `DLightDevice.get_info()`.

**Example:**

```python
info = await lamp.get_info()
print(f"Model: {info.get('deviceModel')}, FW: {info.get('swVersion')}")
```

## `CommandResult`

```python
class CommandResult(TypedDict, total=False):
    status:    str         # "SUCCESS" or an error code
    commandId: str         # echoed command ID (hex string)
    deviceId:  str         # echoed device ID
    states:    DeviceState # current state after the command (if returned)
```

The raw dict returned by all `AsyncDLightClient` methods and by the underlying calls in `DLightDevice`. Most callers do not need to inspect this directly — `DLightDevice` extracts and caches the relevant fields automatically.

**Example:**

```python
result = await client.set_brightness("192.168.1.123", "DL12345", 50)
print(result.get("status"))   # "SUCCESS"
```
