# Connection Management

## Ephemeral vs. persistent connections

By default, `AsyncDLightClient` opens a new TCP connection for each command and closes it immediately after the response is received. This is the safest mode and requires no cleanup.

```python
client = AsyncDLightClient()          # ephemeral — new connection per command
```

For applications that send many sequential commands, enable **persistent connections**. The client maintains a pool of open connections keyed by `(host, port, ssl)` and reuses them across calls.

```python
client = AsyncDLightClient(persistent=True)   # connections stay open
```

## Connection pool behaviour

The pool provides these guarantees:

- **Per-device locking.** Each `(host, port, ssl)` key has its own `asyncio.Lock`. Concurrent tasks sharing a client will queue up per device, not per client — so two lamps can be commanded in parallel while requests to the same lamp serialise.
- **Eviction on failure.** Any exception during a send or receive evicts the connection immediately. The error is then raised to the caller.
- **Liveness checked before reuse.** Before a pooled connection is handed out it is checked for a departed peer — one that closed the connection cleanly, or reset it, while it sat idle. Such a connection is discarded and replaced transparently, without the caller noticing.
- **Commands are never re-sent by the pool.** If a failure survives the liveness check, it is raised to the caller. The pool does not re-send the command on a fresh connection, because only the caller can know whether re-sending is safe. See [Retries](#retries) below to opt into recovery.
- **Idle eviction.** Connections unused for longer than `idle_timeout` (default 60 s) are closed and removed from the pool.

!!! warning "Changed in 2.1.0"
    Earlier versions re-sent the failed command once on a new connection when a reused connection failed. Because the client also retries, the two layers multiplied: a client with `max_retries=2` could deliver one command to the lamp **four** times. The pool no longer re-sends anything.

    Most stale connections are now caught before a command is written, so this is invisible. For the rest, `persistent=True` with the default `max_retries=0` surfaces an error where it previously recovered silently — set `max_retries=1` to restore the old effective behaviour, this time as your choice and with a bound you can predict.

## The context manager

The `async with` pattern is the recommended lifecycle for persistent connections:

```python
async with AsyncDLightClient(persistent=True) as client:
    lamp = DLightDevice("192.168.1.123", "DL12345", client)
    await lamp.turn_on()
    await lamp.set_brightness(50)
# pool flushed; all TCP connections closed
```

The `async with` block does **not** enable persistence by itself — you must pass `persistent=True`. The context manager only guarantees that `client.close()` is called on exit, flushing any pooled connections.

!!! note "Changed in 1.6.0"
    Prior to 1.6.0, entering the context manager implicitly set `persistent=True`. The current behaviour is explicit and predictable: persistence is a constructor flag, the context manager handles cleanup only.

## Tuning idle timeout

If your application sends bursts of commands with long pauses between them, you may want to tune `idle_timeout`:

```python
# Keep connections alive for 5 minutes between bursts
client = AsyncDLightClient(persistent=True, idle_timeout=300.0)

# Never evict on idle (not recommended — servers may close the socket anyway)
client = AsyncDLightClient(persistent=True, idle_timeout=0)
```

Setting `idle_timeout=0` disables idle eviction. The connection will still be evicted on the next failure.

## Retries

```python
client = AsyncDLightClient(
    max_retries=2,      # attempt up to 2 retries (3 total attempts)
    retry_backoff=0.5,  # wait 0.5 s before first retry, 1.0 s before second
)
```

Retries fire on `DLightTimeoutError` and `DLightConnectionError` only. They never fire on `DLightCommandError` or `DLightResponseError` — those indicate a protocol-level problem that won't resolve by retrying.

Each retry gets a **fresh TCP connection**, even in persistent mode. A stale or broken connection is not re-used.

`max_retries` is the **only** retry counter, so the attempt count above is exact: `max_retries=2` means the lamp receives the command at most three times. Nothing below this layer re-sends it.

!!! danger "Retries and non-idempotent commands"
    A retry re-sends a command that may already have reached the lamp — the protocol has no way to confirm delivery. For `EXECUTE` commands this is usually harmless because they set absolute values (`brightness=40` twice leaves the lamp at 40). Raise `max_retries` deliberately, not by default.

## TLS

```python
# Trust the server via the system CA store
client = AsyncDLightClient(ssl=True)

# Provide a custom context (self-signed certs, mutual TLS, etc.)
import ssl
ctx = ssl.create_default_context(cafile="/path/to/ca.pem")
client = AsyncDLightClient(ssl=ctx)

# Disable certificate verification (development / testing only)
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
client = AsyncDLightClient(ssl=ctx)
```

## Concurrency

One `AsyncDLightClient` instance is safe to share across multiple coroutines and multiple `DLightDevice` objects. The per-device lock in the pool ensures that concurrent commands to the **same** lamp are serialised while commands to **different** lamps proceed in parallel:

```python
async with AsyncDLightClient(persistent=True) as client:
    lamp_a = DLightDevice("192.168.1.10", "DLA", client)
    lamp_b = DLightDevice("192.168.1.11", "DLB", client)

    # These run concurrently — different devices, different pool slots
    await asyncio.gather(
        lamp_a.set_brightness(100),
        lamp_b.set_brightness(50),
    )
```

## Performance tips

| Scenario | Recommendation |
|---|---|
| Single command, fire-and-forget | Default (ephemeral) — simplest, no cleanup needed |
| Sequential burst of commands | `persistent=True` + context manager |
| Long-running automation / daemon | `persistent=True`, tune `idle_timeout` to match your command cadence |
| Unreliable Wi-Fi | Add `max_retries=2, retry_backoff=0.5` |
| Production with device certificate | Pass a custom `ssl.SSLContext` |
