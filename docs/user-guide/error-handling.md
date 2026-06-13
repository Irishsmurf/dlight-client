# Error Handling

All exceptions raised by dlight-client inherit from `DLightError`, making it easy to catch any library error with a single `except` clause.

## Exception hierarchy

```
DLightError
├── DLightConnectionError    — could not establish or maintain a TCP connection
│   └── DLightTimeoutError  — operation exceeded the timeout threshold
├── DLightCommandError       — the device rejected the command
└── DLightResponseError      — the device returned an unexpected or malformed response
```

## Exception reference

### `DLightError`

Base class. Catch this to handle any error from the library without worrying about subtypes.

```python
from dlightclient.exceptions import DLightError

try:
    await lamp.turn_on()
except DLightError as e:
    print(f"dlight-client error: {e}")
```

### `DLightConnectionError`

Raised when a TCP connection cannot be established to the lamp. Common causes: lamp is off, wrong IP, firewall rule.

```python
from dlightclient.exceptions import DLightConnectionError

try:
    await lamp.turn_on()
except DLightConnectionError:
    print("Could not reach the lamp — is it powered on?")
```

**Retryable:** Yes — this error triggers retries when `max_retries > 0`.

### `DLightTimeoutError`

A subclass of `DLightConnectionError`. Raised when a connect or read operation exceeds `default_timeout`.

```python
from dlightclient.exceptions import DLightTimeoutError

client = AsyncDLightClient(default_timeout=2.0)

try:
    await lamp.get_state(force_update=True)
except DLightTimeoutError:
    print("Lamp did not respond in time")
```

**Retryable:** Yes.

### `DLightCommandError`

Raised when the lamp responds with a non-SUCCESS status — the command was received but rejected (e.g. value out of range, unknown command).

```python
from dlightclient.exceptions import DLightCommandError

try:
    await lamp.set_brightness(150)   # out of range
except DLightCommandError as e:
    print(f"Command rejected: {e}")
```

**Retryable:** No — retrying a rejected command will produce the same result.

### `DLightResponseError`

Raised when the device returns a response that cannot be parsed, or when the device echoes the command back (a known hardware quirk that indicates the connection is in a bad state).

**Retryable:** No — the connection is evicted from the pool; the next command will open a fresh one.

## Granular error handling

```python
from dlightclient.exceptions import (
    DLightTimeoutError,
    DLightConnectionError,
    DLightCommandError,
    DLightResponseError,
    DLightError,
)

try:
    await lamp.set_color_temperature(3000)
except DLightTimeoutError:
    print("Timed out — will retry later")
except DLightConnectionError:
    print("Lamp unreachable")
except DLightCommandError as e:
    print(f"Bad command: {e}")
except DLightResponseError as e:
    print(f"Protocol error: {e}")
except DLightError as e:
    print(f"Unexpected library error: {e}")
```

## Logging

The library uses the standard `logging` module under the `dlightclient` logger hierarchy. By default, no output is produced unless you configure a handler.

```python
import logging

# Show all library debug output
logging.getLogger("dlightclient").setLevel(logging.DEBUG)
logging.basicConfig()
```

Credential values (Wi-Fi passwords) are masked in all log messages regardless of log level.

Log levels used by the library:

| Level | Examples |
|---|---|
| `DEBUG` | Connection opened/closed, command sent, retry attempt, pool eviction |
| `INFO` | Devices discovered |
| `WARNING` | Retry exhausted, unexpected response |
| `ERROR` | Unrecoverable protocol error |
