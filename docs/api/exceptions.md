# Exceptions

All exceptions are importable from `dlightclient` or `dlightclient.exceptions`.

## Hierarchy

```
DLightError
├── DLightConnectionError
│   └── DLightTimeoutError
├── DLightCommandError
└── DLightResponseError
```

## `DLightError`

```python
class DLightError(Exception)
```

Base class for all library exceptions. Catch this to handle any dlight-client error without importing subtypes.

## `DLightConnectionError`

```python
class DLightConnectionError(DLightError)
```

Raised when a TCP connection to the lamp cannot be established or drops unexpectedly.

| Attribute | Description |
|---|---|
| `args[0]` | Human-readable message describing the failure. |

**Retryable:** Yes — triggers retry logic when `max_retries > 0`.

**Common causes:** Lamp is powered off, wrong IP address, firewall blocking port 3333.

## `DLightTimeoutError`

```python
class DLightTimeoutError(DLightConnectionError)
```

Raised when a connect or read operation exceeds `default_timeout`. A subclass of `DLightConnectionError`, so catching the parent also catches this.

**Retryable:** Yes.

**Common causes:** Lamp is slow to respond (heavy load, weak Wi-Fi signal), `default_timeout` set too low for the network.

## `DLightCommandError`

```python
class DLightCommandError(DLightError)
```

Raised when the lamp acknowledges the command but returns a non-SUCCESS status. This indicates a logic error in the command (e.g. brightness value out of range), not a network problem.

**Retryable:** No — the same command will be rejected again.

**Common causes:** Parameter out of range, command not supported by this firmware version.

## `DLightResponseError`

```python
class DLightResponseError(DLightError)
```

Raised when the device returns a response that cannot be parsed, or when it echoes the command back verbatim (a hardware quirk indicating the connection is in a bad state).

**Retryable:** No — the pooled connection is evicted immediately, and the next command will open a fresh connection.

## Import paths

```python
# Preferred — top-level import
from dlightclient import DLightError, DLightConnectionError, DLightTimeoutError

# Also valid — direct module import
from dlightclient.exceptions import DLightCommandError, DLightResponseError
```
