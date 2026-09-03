# AsyncDLightClient

```python
from dlightclient import AsyncDLightClient
```

The low-level TCP client. It handles command construction, connection pooling, wire-protocol framing, and retry orchestration. Most callers should prefer [`DLightDevice`](device.md) for day-to-day use, and drop to `AsyncDLightClient` only when they need the raw `CommandResult` or are sending commands not covered by the high-level API.

## Constructor

```python
AsyncDLightClient(
    default_timeout: float = 5.0,
    persistent: bool = False,
    max_retries: int = 0,
    retry_backoff: float = 0.5,
    idle_timeout: float = 60.0,
    ssl: Optional[Union[bool, ssl.SSLContext]] = None,
)
```

| Parameter | Type | Default | Description |
|---|---|---|---|
| `default_timeout` | `float` | `5.0` | Seconds before a connect or read is abandoned. |
| `persistent` | `bool` | `False` | When `True`, connections are kept in a pool and reused. A pooled connection is checked for a departed peer before reuse; the pool never re-sends a command. |
| `max_retries` | `int` | `0` | Number of retry attempts on transient errors (0 = no retries). This is the **only** retry counter: `max_retries=2` means the device receives a command at most three times. |
| `retry_backoff` | `float` | `0.5` | Base backoff in seconds. Each retry doubles: `backoff * 2^attempt`. |
| `idle_timeout` | `float` | `60.0` | Seconds of inactivity before a pooled connection is evicted. `0` disables idle eviction. |
| `ssl` | `bool \| SSLContext \| None` | `None` | `True` for system CA trust, a custom `SSLContext`, or `None`/`False` for plain TCP. |

## Properties

### `persistent`

```python
client.persistent = True   # enable persistence after construction
client.persistent = False  # disable and flush the pool
```

Setting `persistent` to `False` on a live client closes all pooled connections immediately.

!!! warning "Changed in 2.1.0"
    The pool no longer re-sends a failed command on a fresh connection. It checks a pooled connection for a departed peer before handing it out, so most stale connections are replaced before anything is written — but a failure that survives that check is now raised to you rather than silently retried. With `persistent=True` and the default `max_retries=0` this surfaces as a `DLightConnectionError` where earlier versions recovered. Set `max_retries=1` to restore the old effective behaviour.

    Rationale: [ADR 0001](../adr/0001-no-byte-replay-in-the-connection-pool.md).

### `idle_timeout`

```python
client.idle_timeout = 120.0
```

Can be updated at any time. The new value is applied to future connections; existing connections retain their current timer.

## Methods

### `set_light_state`

```python
async def set_light_state(target_ip: str, device_id: str, on: bool) -> CommandResult
```

Turn the lamp on (`True`) or off (`False`).

### `set_brightness`

```python
async def set_brightness(target_ip: str, device_id: str, brightness: int) -> CommandResult
```

Set brightness (0–100). Raises `DLightCommandError` if `brightness` is out of range.

### `set_color_temperature`

```python
async def set_color_temperature(target_ip: str, device_id: str, temperature: int) -> CommandResult
```

Set colour temperature in Kelvin (2600–6000). Raises `DLightCommandError` if out of range.

### `query_device_state`

```python
async def query_device_state(target_ip: str, device_id: str) -> CommandResult
```

Query the lamp's current power, brightness, and colour temperature.

### `query_device_info`

```python
async def query_device_info(target_ip: str, device_id: str) -> CommandResult
```

Query hardware metadata (model, firmware version, MAC address).

### `connect_to_wifi`

```python
async def connect_to_wifi(
    device_id: str,
    ssid: str,
    password: str,
    target_ip: str = "192.168.4.1",
    port: int = 3333,
    ssl: Optional[Union[bool, ssl.SSLContext]] = None,
) -> CommandResult
```

Send Wi-Fi credentials to a lamp in SoftAP (factory-reset) mode. The `password` value is masked in all log output regardless of log level.

### `close`

```python
async def close() -> None
```

Flush all pooled connections and release resources. Called automatically by `__aexit__`.

## Context manager

```python
async with AsyncDLightClient(persistent=True) as client:
    result = await client.query_device_state("192.168.1.123", "DL12345")
# client.close() called on exit
```

## Exceptions raised

| Exception | When |
|---|---|
| `DLightTimeoutError` | Connect or read exceeded `default_timeout`. Retried if `max_retries > 0`. |
| `DLightConnectionError` | TCP connection refused or reset. Retried if `max_retries > 0`. |
| `DLightCommandError` | Device returned a non-SUCCESS status. Never retried. |
| `DLightResponseError` | Response could not be parsed, or device echoed the command. Never retried. |
