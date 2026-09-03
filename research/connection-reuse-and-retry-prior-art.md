# Prior art: connection reuse and retry in async Python clients

Research for [issue #68](https://github.com/Irishsmurf/dlight-client/issues/68).
Feeds the keep/drop/move-up decision for dLight's transparent reconnect
(`dlightclient/_pool.py`).

All source citations are against the upstream repositories at the commit or tag
named. Where docs and code disagree, both are given and the difference is
called out.

---

## TL;DR

| Library | Replays an already-written request on a fresh connection? | Idempotency gate | Bound | Bound documented? |
| --- | --- | --- | --- | --- |
| `aiohttp` | **Yes** | **Yes** — method must be in `IDEMPOTENT_METHODS` | Exactly **1** replay, hard-coded | **No** (private attribute, absent from docs) |
| `asyncpg` | **No** for connection failures; **yes** for one specific server-side error | Gated on a *proof the statement was never applied* (server rejected it) + not in a transaction | Exactly **1** replay, hard-coded | Only in a source comment |
| `redis-py` (asyncio) | **Yes** | **None whatsoever** | **3** retries (4 deliveries) **by default** since 6.0.0 | Retry count yes; duplication risk **no** |
| `asyncssh` | **No** — zero retry/reconnect code in the library | n/a | n/a | n/a |
| `httpx` / `httpcore` | **No** — retries are scoped to TCP connect only | n/a (never re-sends bytes) | `retries=0` default | Yes |
| `urllib3` | Yes (as an explicit, opt-in `Retry` object) | **Yes** — `allowed_methods` defaults to idempotent verbs only | `total=10` default on the `Retry` object | Yes |

Three coherent positions exist in the ecosystem, and every mature library picks
one of them explicitly:

1. **Replay, but only when the library can prove it is safe** (aiohttp, asyncpg,
   urllib3). The proof is either a protocol-level idempotency signal (HTTP
   method) or a *negative acknowledgement* (the server rejected the statement,
   so it definitely did not run).
2. **Never replay written bytes; surface the failure** (asyncssh, httpx/httpcore).
3. **Replay unconditionally and declare "at-least-once" as the contract**
   (redis-py, Lettuce). This position is only defensible *because it is stated*.

dLight currently occupies a fourth position that nobody else does: replay
unconditionally, *and* let it compose with a caller-level retry, *and* don't
state a bound.

---

## The normative baseline: RFC 9110 §9.2.2

This is the text every HTTP client in this survey is implementing against, and
the reasoning generalises past HTTP.

> Idempotent methods are distinguished because the request can be repeated
> automatically if a communication failure occurs before the client is able to
> read the server's response. [...]
>
> **A client SHOULD NOT automatically retry a request with a non-idempotent
> method unless it has some means to know that the request semantics are
> actually idempotent, regardless of the method, or some means to detect that
> the original request was never applied.**
>
> [...] Some clients take a riskier approach and attempt to guess when an
> automatic retry is possible. For example, a client might automatically retry a
> POST request if the underlying transport connection closed before any part of a
> response is received, particularly if an idle persistent connection was used.
>
> **A proxy MUST NOT automatically retry non-idempotent requests. A client
> SHOULD NOT automatically retry a failed automatic retry.**

Source: <https://www.rfc-editor.org/rfc/rfc9110.txt> §9.2.2 (lines 3861–3904 of
the canonical text file).

Two clauses bear directly on the dLight decision:

- The escape hatch is **"some means to detect that the original request was
  never applied"**. dLight's wire protocol has no request/response correlation,
  so dLight has no such means — it cannot distinguish "never delivered" from
  "delivered, applied, response lost". The only remaining justification would be
  "the request semantics are actually idempotent", which is a *caller-side*
  fact, not a pool-side one.
- **"A client SHOULD NOT automatically retry a failed automatic retry."** This
  is precisely the `(max_retries + 1) x 2` composition dLight has today. The RFC
  names it as the thing not to do. Every library below that replays enforces a
  hard bound of exactly one replay, and none of them let it stack.

RFC 9112 §9.3.1 ("Retrying Requests") adds only that implementations must
anticipate asynchronous close events, and defers the conditions back to
RFC 9110 §9.2.2. Source: <https://www.rfc-editor.org/rfc/rfc9112.html#section-9.3.1>.

---

## aiohttp

**Verdict: replays, but strictly gated on method idempotency, bounded to one,
and the whole mechanism is undocumented and not user-controllable.**

### What the code does

`ClientSession._request()` sets up a single-shot replay flag *before* the send
loop, gated on the HTTP method:

```python
# https://www.rfc-editor.org/rfc/rfc9112.html#name-retrying-requests
retry_persistent_connection = (
    self._retry_connection and method in IDEMPOTENT_METHODS
)
```

and consumes it in the error handler:

```python
except (ClientOSError, ServerDisconnectedError):
    if not retry_persistent_connection:
        raise
    retry_persistent_connection = False
    ...
    continue
```

Source: [`aiohttp/client.py`](https://github.com/aio-libs/aiohttp/blob/master/aiohttp/client.py)
(the `retry_persistent_connection` assignment and the `except (ClientOSError,
ServerDisconnectedError)` block inside `_request`).

The allow-list is explicit and cites the RFC:

```python
# https://www.rfc-editor.org/rfc/rfc9110#section-9.2.2
IDEMPOTENT_METHODS = frozenset(
    {"GET", "HEAD", "OPTIONS", "TRACE", "PUT", "DELETE", "QUERY"}
)
```

Same file. `QUERY` was added by
[PR #13301](https://github.com/aio-libs/aiohttp/pull/13301).

Note the deliberate carve-outs: connector-level failures are **re-raised, never
retried**, because a failure to establish a connection is a different class of
event:

```python
# Client connector errors should not be retried
except (
    ConnectionTimeoutError,
    ClientConnectorError,
    ClientConnectorCertificateError,
    ClientConnectorSSLError,
):
    raise
```

`self._retry_connection` is assigned `True` unconditionally in
`ClientSession.__init__` and is **not** a constructor parameter — it is a
private, always-on attribute.

### What the docs say

Nothing. The `ClientSession` reference page
(<https://docs.aiohttp.org/en/stable/client_reference.html>) contains no mention
of `retry`, `retry_connection`, idempotent methods, persistent-connection retry,
or `ServerDisconnectedError` in this context. **The behaviour exists only in the
code.** The sole public trace is a one-line changelog entry in 3.10.0
(2024-07-30):

> Added a feature to retry closed connections automatically for idempotent
> methods. -- by :user:`Dreamsorcerer`

Source: [`CHANGES.rst`](https://github.com/aio-libs/aiohttp/blob/master/CHANGES.rst),
3.10.0 section, referencing [issue #7297](https://github.com/aio-libs/aiohttp/issues/7297).

### The motivating bug and the pushback

[Issue #7297](https://github.com/aio-libs/aiohttp/issues/7297) — "Client attempts
to reuse a closed connection if `Connection: keep-alive` header was received."
A server may legally advertise keep-alive and then close the socket; the next
request on the recycled connection fails. This is the *exact* failure mode
dLight's transparent reconnect exists to paper over.

[Issue #10790](https://github.com/aio-libs/aiohttp/issues/10790) — "There is no
way to disable request retry in `ClientSession._request()`" — is the closest
thing to a post-mortem, and it is worth reading in full for the decision at
hand. The reporter's position:

> `ClientSession._request()` should not have a hard-coded retry. If anything,
> the retry should be an opt-in by the user only.

Maintainer (`Dreamsorcerer`):

> This is explicitly allowed behaviour in the RFCs. We have many complaints and
> bug reports caused by not retrying connections from servers which close
> keepalive connections immediately after a request. We're definitely not
> disabling this by default. If you have a real use for not retrying, then feel
> free to create a PR to make it opt-out.

Reporter, on why the bound matters:

> aiohttp doesn't really implement a durable retry solution — it only limits it
> to a single retry, so it's clear that it's not trying to offer a real retry
> feature, but is instead trying to work around the keepalive-unfriendly
> scenario, and nothing more. [...] This makes it clear that aiohttp leaves it
> to the user to implement functional retries (more than just the hard-coded 1
> retry).

The reporter's two concrete proposals are both directly transplantable to
dLight:

- **Proposal 1**: also gate on `not self._connector.force_close` — i.e. if the
  user asked for no connection reuse, don't do reuse-recovery either.
- **Proposal 2**: add a `reused: bool` flag to `Connection`, set it when the
  connection came *from the pool*, and gate the replay on `conn.reused`. A
  freshly-dialled connection that fails is a real failure; only a recycled one
  earns a replay.

Neither has landed as of this writing; the issue is closed with the maintainer
saying "I'm thinking we probably still want it to be opt-out."

One further wrinkle, from
[PR #13330](https://github.com/aio-libs/aiohttp/pull/13330) ("Rewind file bodies
when internally retrying a request"): replaying a request with a body is *hard*,
because the body may be a partially-consumed stream. aiohttp's current code
bails out rather than send a truncated body:

```python
if data is not None:
    # Rebuilding from `data` would resend only the unread
    # remainder of a file object; reuse the payload, which
    # rewinds itself once the cancelled writer has settled.
    await req._close()
    if req._body.consumed:
        raise
    data = req._body
```

dLight's byte-buffer replay does not have this problem (commands are small and
fully buffered), but it is a reminder that "replay the bytes" is only simple
because dLight's requests are small.

---

## asyncpg

**Verdict: connection failures are surfaced, never replayed. The one retry that
exists is gated on positive proof the statement never ran, and is bounded to
one.**

### Pooled connections: checked at acquire, never replayed

`PoolConnectionHolder.acquire()` checks liveness *before* handing the connection
out, and dials a new one if the cached connection is closed or has been
generation-expired:

```python
async def acquire(self) -> PoolConnectionProxy:
    if self._con is None or self._con.is_closed():
        self._con = None
        await self.connect()

    elif self._generation != self._pool._generation:
        # Connections have been expired, re-connect the holder.
        ...
```

Source: [`asyncpg/pool.py`](https://github.com/MagicStack/asyncpg/blob/master/asyncpg/pool.py),
`PoolConnectionHolder.acquire`.

That is the *entire* extent of asyncpg's staleness handling: it is a
**pre-flight check**, not a post-failure recovery. If the connection dies after
the query has been written, the failure propagates to the caller as
`ConnectionDoesNotExistError` / `InterfaceError`. There is no replay path in
`pool.py` or the query execution path.

Note the same "if we can't prove it's clean, close it" instinct in the `setup`
error handler, with the reasoning spelled out:

```python
except (Exception, asyncio.CancelledError) as ex:
    # If a user-defined `setup` function fails, we don't
    # know if the connection is safe for re-use, hence
    # we close it.
```

### The one retry asyncpg does have — and why it is legitimate

`Connection._do_execute()` takes a `retry=True` parameter and re-runs the query
exactly once on `InvalidCachedStatementError`:

```python
except exceptions.InvalidCachedStatementError:
    # PostgreSQL will raise an exception when it detects
    # that the result type of the query has changed from
    # when the statement was prepared. [...]
    #
    # When this happens, and there is no transaction running,
    # we can simply re-prepare the statement and try once
    # again.  We deliberately retry only once as this is
    # supposed to be a rare occurrence.
    #
    # If the transaction _is_ running, this error will put it
    # into an error state, and we have no choice but to
    # re-raise the exception.
    self._drop_global_statement_cache()
    if self._protocol.is_in_transaction() or not retry:
        raise
    else:
        return await self._do_execute(
            query, executor, timeout, retry=False)
```

Source: [`asyncpg/connection.py`](https://github.com/MagicStack/asyncpg/blob/master/asyncpg/connection.py),
`Connection._do_execute`. Design discussion:
[asyncpg#72](https://github.com/MagicStack/asyncpg/issues/72),
[asyncpg#76](https://github.com/MagicStack/asyncpg/issues/76).

Three things make this a *safe* replay, and all three are exactly what dLight
lacks:

1. **It is a negative acknowledgement.** `InvalidCachedStatementError` is a
   response *from the server* saying the statement was rejected. asyncpg has the
   RFC 9110 "means to detect that the original request was never applied".
2. **It is gated on an additional precondition the library can check**
   (`is_in_transaction()`), and when that precondition fails it re-raises rather
   than guessing.
3. **The bound is one, enforced structurally** by passing `retry=False` into the
   recursive call, so the retry cannot itself retry. Contrast the RFC's "A
   client SHOULD NOT automatically retry a failed automatic retry."

Note that the contrasting handler two lines above, for
`OutdatedSchemaCacheError`, does *not* retry, with the reason given explicitly:
"It is not possible to recover (the statement is already done at the server's
side)". asyncpg's rule is legible: **replay only when you know it did not run.**

Docs: <https://magicstack.github.io/asyncpg/current/api/index.html>. The bound
appears only in the source comment, not the published API docs.

---

## redis-py (asyncio)

**Verdict: replays the entire send-and-parse cycle, with no idempotency gate at
all, three times by default. The duplication hazard is known, has been reported
twice a decade apart, and has been closed both times as working-as-intended
"at-least-once" semantics — but the docs never say so.**

This is the closest analogue to dLight's current behaviour and the richest
source of evidence.

### What the code does

`Redis.execute_command` wraps `_send_command_parse_response` — *both* the write
and the read — in the connection's retry object:

```python
result = await conn.retry.call_with_retry(
    lambda: self._send_command_parse_response(
        conn, command_name, *args, **options
    ),
    failure_callback,
    with_failure_count=True,
)
```

and the retried unit is:

```python
async def _send_command_parse_response(self, conn, command_name, *args, **options):
    """
    Send a command and parse the response
    """
    await conn.send_command(*args)
    return await self.parse_response(conn, command_name, **options)
```

Source: [`redis/asyncio/client.py` @ v8.1.0](https://github.com/redis/redis-py/blob/v8.1.0/redis/asyncio/client.py),
`Redis.execute_command` and `Redis._send_command_parse_response`.

The failure callback disconnects the connection before the next attempt, so the
replay lands on a **freshly dialled connection** — structurally identical to
dLight's `reconnect_and_retry`:

```python
async def _close_connection(self, conn, error=None, failure_count=None, ...):
    """
    Close the connection before retrying.
    [...]
    After we disconnect the connection, it will try to reconnect and
    do a health check as part of the send_command logic(on connection level).
    """
```

`Retry.call_with_retry` retries on `(ConnectionError, TimeoutError,
socket.timeout)` by default, with no notion of which command is being retried:

```python
_supported_errors: Tuple[Type[E], ...] = (ConnectionError, TimeoutError, socket.timeout)
```

Source: [`redis/retry.py`](https://github.com/redis/redis-py/blob/master/redis/retry.py).

**There is no idempotency concept anywhere in redis-py.** No allow-list, no
command classification, no caller opt-in per command. The unit of decision is
the *connection*, not the *command*.

### The bound, and how it changed

Since 6.0.0 the default is **3 retries — i.e. up to 4 physical deliveries of one
logical command** — with exponential backoff, for every standalone client:

```python
retry: Retry = Retry(
    backoff=ExponentialWithJitterBackoff(
        base=DEFAULT_RETRY_BASE, cap=DEFAULT_RETRY_CAP
    ),
    retries=DEFAULT_RETRY_COUNT,
),
```

Source: [`redis/asyncio/client.py` @ v8.1.0](https://github.com/redis/redis-py/blob/v8.1.0/redis/asyncio/client.py),
`Redis.__init__`; changed by
[PR #3614, merged 2025-04-28](https://github.com/redis/redis-py/pull/3614)
("Updating default retry strategy for standalone clients. 3 retries with
ExponentialWithJitterBackoff become the default config"), part of the broader
[issue #3008](https://github.com/redis/redis-py/issues/3008) "Overall revamp of
connection pool, retries and timeouts". Note the same PR sets cluster-node
clients to **0** retries, because the cluster layer does its own.

**How it composes with caller-level retry:** redis-py exposes exactly one knob
(`retry=` / `set_retry()`), applied at the connection. There is no second,
inner replay mechanism — so unlike dLight, the bound does *not* multiply with
itself. A caller who additionally wraps calls in `tenacity` gets the product,
but that is visibly the caller's own doing.

### What the docs say

The retry page (<https://redis.readthedocs.io/en/stable/retry.html>) documents
the count and the error types:

> If no `retry` is provided, a default one is created with
> `ExponentialWithJitterBackoff` as backoff strategy and 3 retries.

It says **nothing** about idempotency, command duplication, or the fact that a
write that already reached the server can be re-sent. The bound is documented;
the hazard is not.

### The public record of the correctness problem

**[Issue #261](https://github.com/redis/redis-py/issues/261) (2013) —
"execute_command sends command twice to server if server is busy and timeout is
configured".** The reproducer is one line of Redis:

```python
r = redis.Redis(socket_timeout=3)
r.set('x', 1)
#  now run in shell: redis-cli debug sleep 20
r.incr('x', 1)   # This will run twice!!!
r.get('x')       # This will return 3!!!
```

Maintainer `andymccurdy` initially defended the behaviour:

> I believe the current retry behavior is the lesser of two evils. There are
> many network hiccups, especially on cloud providers like AWS. If we didn't
> automatically retry the commands, users would have to perform that logic
> throughout their application. And in the case of incrementing an integer, the
> user will have no idea if the INCR actually went through or not. The retry
> logic isn't perfect, but it's certainly better than not doing it at all.

The reporter's counter is the argument for moving the decision up to the caller:

> Usually you'd expect the client to raise an exception if a command fails. This
> gives the client a chance to decide if they want to retry blindly or check if
> the previous command executed before retrying. **There are cases where you can
> assume the command didn't execute, for example a connection reset. But timeout
> exceptions aren't one of those.**

That distinction won. The outcome was `retry_on_timeout`, defaulting to
`False` — i.e. redis-py split the failure taxonomy into "connection reset,
probably not delivered → replay" and "timeout, possibly delivered → surface",
and made the dangerous half opt-in. Confirmed in `CHANGES`:

> Added a `retry_on_timeout` option that controls how socket.timeout errors are
> handled. [...] if `retry_on_timeout` is set to True, the client will retry a
> command that timed out.

Source: [`CHANGES`](https://github.com/redis/redis-py/blob/master/CHANGES).

**[Issue #3554](https://github.com/redis/redis-py/issues/3554) (2025) —
"Potential Command Duplication in `_send_command_parse_response` Retry
Mechanism".** The same bug, rediscovered against the modern async code:

> if the Redis container goes down after `send_command` and before
> `parse_response`, the entire `_send_command_parse_response` will be retried.
> This means that any command with side effects (such as `XADD`) could be
> executed twice instead of just once, leading to unintended duplication.

Maintainer `vladvildanov` agreed on the substance:

> You have a point here, it doesn't make sense to retry write operation on read
> failure, moreover it may lead to unintended disconnects because we have data
> in a socket buffer that we don't process.

**[PR #3559](https://github.com/redis/redis-py/pull/3559)** attempted the obvious
fix — separate the retry scope for the write from the read, so a *read* failure
never causes a *re-write*. **It was closed without merging**, and the reasoning
is the single most useful thing in this whole document:

- Splitting them breaks the retry: `parse_response` has no reconnect logic, so
  retrying only the read on a dead socket just fails again.
- Reconnecting before the read doesn't work either, because `on_connect` sends
  its own handshake commands (`AUTH`, `SELECT`, ...) on the new socket — so the
  response you would read back is *not* the response to your command. In a
  protocol without request/response correlation, **a new connection cannot be
  used to collect the answer to a request sent on the old one.**
- Therefore the maintainer's conclusion:

  > the existing logic that considers disconnect on retry makes it impossible to
  > separate retries for write and read. I did some investigation in other
  > clients and they also stick to this "transactional" logic when doing
  > retries, so to be consistent **we assume that command is called at least
  > once, but you may live with duplicate. Other way you need to handle retries
  > in the application.**

The reporter's rejected counter-proposal is, notably, option three on dLight's
list — surface a distinguishable error and let the caller decide:

> instead of requiring users to track whether the command was sent once or
> twice, they would only need to check whether it was successful in case of an
> error.

Maintainer's final position: keep at-least-once as the default, and *possibly*
offer an "at most once" retry strategy alongside it. That has not shipped.

### The reference redis-py points at: Lettuce

`vladvildanov` justified the decision by citing Lettuce, the Java Redis client,
which documents the semantics dLight is currently choosing between, by name:

- **At-most-once execution**: "for each command handed to the mechanism, that
  command is executed zero or one time" — "commands may be lost".
- **At-least-once execution**: "potentially multiple attempts made at execution"
  — "commands may be duplicated but not lost".

And it names the hazard explicitly rather than leaving it implicit: commands
like `LPUSH`, `PUBLISH` and `INCR` are non-idempotent, so duplicate execution
under at-least-once produces wrong state. The documented way to opt out is to
disable auto-reconnect, which converts the client to at-most-once: unsuccessful
commands are cancelled and new commands are rejected.

Source: <https://github.com/redis/lettuce/wiki/Command-execution-reliability>.

This is the model for "keep it but state the composed bound": Lettuce keeps the
replay, but it publishes the delivery semantics, names the non-idempotent
commands at risk, and ships a documented switch to the other semantics.

---

## asyncssh

**Verdict: no retry, no reconnect, no replay — anywhere. Connection loss is
surfaced to the caller as a typed exception.**

This is the cleanest result in the survey and it is a negative one:

```
$ grep -rn -i "retry" asyncssh/*.py | wc -l
0
$ grep -rn -i "retry\|reconnect" docs/
(no matches)
```

(against the `develop` branch of <https://github.com/ronf/asyncssh>.)

asyncssh *does* reuse connections in the sense that matters — one
`SSHClientConnection` multiplexes many channels/sessions, so a long-lived
connection serves many logical requests. But when that connection dies, the loss
is propagated, not repaired:

```python
def connection_lost(self, exc: Optional[Exception] = None) -> None:
    """Handle the closing of a connection"""

    if exc is None and self._transport:
        exc = ConnectionLost('Connection lost')

    self._force_close(exc)
```

Source: [`asyncssh/connection.py`](https://github.com/ronf/asyncssh/blob/develop/asyncssh/connection.py),
`SSHConnection.connection_lost`.

The exception is public API and documented as a caller concern:

```python
class ConnectionLost(DisconnectError):
    """SSH connection lost

       This exception is raised when the SSH connection to the remote
       system is unexpectedly lost. It can also occur as a result of
       the remote system failing to respond to keepalive messages or
       as a result of a login timeout, when those features are enabled.
    """
```

Source: [`asyncssh/misc.py`](https://github.com/ronf/asyncssh/blob/develop/asyncssh/misc.py).

`SSHClient.connection_lost(exc)` is a documented application callback — the
library's answer to "the connection died" is to *tell you*, with the reason, and
let you decide. Source:
[`asyncssh/client.py`](https://github.com/ronf/asyncssh/blob/develop/asyncssh/client.py).

The reason asyncssh can afford this stance is instructive: an SSH session is
stateful and a partially-executed remote command cannot be meaningfully
replayed, so there is no safe generic retry to implement. **A library whose
requests are not provably safe to repeat simply does not repeat them.** dLight's
`EXECUTE` is closer to safe than a shell command, but the structural point
stands: asyncssh pushes the decision to the layer that knows the semantics.

---

## Supporting prior art

### httpx / httpcore — retries scoped to connection *establishment* only

`httpx.HTTPTransport` takes `retries: int = 0`, and it is passed straight down
to `httpcore`, where it is consumed **only inside `_connect()`** — the TCP/TLS
dial — never around the request:

```python
async def _connect(self, request: Request) -> AsyncNetworkStream:
    ...
    retries_left = self._retries
    delays = exponential_backoff(factor=RETRIES_BACKOFF_FACTOR)
    while True:
        try:
            ...connect_tcp(**kwargs)
```

Source: [`httpcore/_async/connection.py`](https://github.com/encode/httpcore/blob/master/httpcore/_async/connection.py).

The pool *does* have a retry loop, but it fires on `ConnectionNotAvailable`,
which is raised **before any bytes are written**, when a pooled connection turns
out not to be in a usable state:

```python
except ConnectionNotAvailable:
    # In some cases a connection may initially be available to
    # handle a request, but then become unavailable.
    #
    # In this case we clear the connection and try again.
    pool_request.clear_connection()
```

Source: [`httpcore/_async/connection_pool.py`](https://github.com/encode/httpcore/blob/master/httpcore/_async/connection_pool.py),
with the raise site in
[`httpcore/_async/http11.py`](https://github.com/encode/httpcore/blob/master/httpcore/_async/http11.py):

```python
async with self._state_lock:
    if self._state in (HTTPConnectionState.NEW, HTTPConnectionState.IDLE):
        ...
    else:
        raise ConnectionNotAvailable()
```

This is the **pre-flight check** pattern again (as in asyncpg's `acquire`), and
it is worth separating cleanly from replay: *choosing a different connection
before writing anything is free and always safe; re-writing bytes after a
failure is neither.* dLight conflates the two today, because
`reconnect_and_retry()` is invoked from both the write path and the read path
(`dlightclient/_pool.py`).

### urllib3 — the caller owns the policy, and the default policy is idempotent-only

urllib3's `Retry` is an explicit object the caller constructs, and its method
allow-list defaults to idempotent verbs:

```python
#: Default methods to be used for ``allowed_methods``
DEFAULT_ALLOWED_METHODS = frozenset(
    ["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE"]
)
```

with the docstring stating the rule and the escape hatch:

> By default, we only retry on methods which are considered to be idempotent
> (multiple requests with the same parameters end with the same state). See
> `Retry.DEFAULT_ALLOWED_METHODS`. Set to a `None` value to retry on any verb.

Source: [`urllib3/util/retry.py`](https://github.com/urllib3/urllib3/blob/main/src/urllib3/util/retry.py).

Note `POST` is absent, and note that the unsafe mode exists but requires the
caller to write `allowed_methods=None` — an unmistakable opt-in.

---

## What this means for dLight

Mapping the survey onto `dlightclient/_pool.py` and `client.py`:

**1. dLight's replay is unguarded in a way no surveyed library's is.**
Every library that replays has *some* gate: aiohttp gates on the method being
idempotent; asyncpg gates on a server-side rejection proving the statement never
ran, plus "not in a transaction"; urllib3 gates on a caller-declared method
allow-list. redis-py has no gate — and redis-py is the one with two decades of
duplicate-execution bug reports. dLight is currently in the redis-py position
without redis-py's documented at-least-once contract.

**2. Retrying on *read* failure is the specific hazard, and it is the one
redis-py could not fix.** `_pool.py` calls `reconnect_and_retry()` from the read
proxy paths as well as the write path. A read failure means the bytes were
already on the wire — redis-py #3554 is exactly this, and PR #3559's failure
shows why it cannot be patched around in a protocol without request/response
correlation: *the new connection cannot be used to collect the answer to the
request sent on the old one.* dLight's protocol has no correlation either, so
the same impossibility applies. Even if replay is kept, **replaying on read
failure is a strictly different and less defensible decision than replaying on
write failure**, and the two are worth separating. On write failure to a
recycled connection, "never applied" is a reasonable inference; on read failure
it is not.

**3. The `(max_retries + 1) x 2` composition has no precedent and is explicitly
warned against.** RFC 9110: "A client SHOULD NOT automatically retry a failed
automatic retry." aiohttp bounds itself to one replay by clearing the flag;
asyncpg bounds itself to one by passing `retry=False` into the recursion;
redis-py has a single knob with no second multiplier. No surveyed library lets
two independent retry layers multiply. If transparent reconnect is kept, the two
layers must be made aware of each other — either the pool's replay is disabled
when the client will retry anyway, or the client's `max_retries` is the only
counter and the pool merely reports "I reconnected, you decide".

**4. There is a cheap safe subset: pre-flight, not post-failure.** asyncpg's
`acquire()` liveness check and httpcore's `ConnectionNotAvailable` both recover
from the *stale idle connection* problem — which is the actual motivating case
(aiohttp #7297) — **without ever re-sending bytes**. `_pool.py` already has a
staleness check at line ~251 ("Cached connection for {key} is stale,
discarding"). If most of the value of transparent reconnect comes from catching
dead-idle connections, most of it can be had with no duplication risk at all,
and the byte-replay path is buying a much smaller marginal benefit at a much
higher correctness price.

**5. The reused-vs-fresh distinction is the gate dLight can actually
implement.** dLight cannot classify commands as idempotent from inside the pool,
but it *can* know whether the connection came from the cache. aiohttp #10790's
Proposal 2 is precisely this: only replay when `conn.reused` is true. A failure
on a connection dialled seconds ago is a real failure and should surface; a
failure on a connection that has been idle in the pool is very likely the
stale-keepalive case. That narrows the blast radius without needing protocol
correlation.

**6. If replay is kept, the ecosystem's standard is that you publish the
delivery semantics.** Lettuce names at-least-once vs at-most-once, lists the
non-idempotent commands at risk by name, and ships a documented switch. redis-py
does not, and that omission is the substance of both #261 and #3554. "Keep it
but state the composed bound" is the *minimum* viable version of keeping it, and
the bound should be stated in the delivery-semantics vocabulary ("EXECUTE is
delivered at least once; up to N physical deliveries") rather than as an
implementation note.

**7. On "move the decision up to the client":** this is the position asyncssh
and httpx take outright, the position urllib3 takes by making the policy a
caller-constructed object, and the position redis-py's reporters argued for
twice and lost — but they lost on *ecosystem-consistency* grounds ("other
clients also stick to this transactional logic"), not on grounds that it is
wrong. The counter-argument to watch for is `andymccurdy`'s, which is real: if
the library doesn't retry, every caller reimplements it, usually worse. dLight
already has the answer to that objection, though — `max_retries` on the client
*is* the caller-level retry, and it already exists. The layer that knows whether
a command is safe to re-send is the layer that already owns the retry loop. That
is a materially stronger position than redis-py was in when it made its call.

---

## Sources

Specifications:

- RFC 9110 §9.2.2 Idempotent Methods — <https://www.rfc-editor.org/rfc/rfc9110.txt>
- RFC 9112 §9.3.1 Retrying Requests — <https://www.rfc-editor.org/rfc/rfc9112.html#section-9.3.1>

aiohttp:

- `aiohttp/client.py` — <https://github.com/aio-libs/aiohttp/blob/master/aiohttp/client.py>
- `CHANGES.rst` (3.10.0) — <https://github.com/aio-libs/aiohttp/blob/master/CHANGES.rst>
- Client reference (no retry documented) — <https://docs.aiohttp.org/en/stable/client_reference.html>
- Issue #7297 — <https://github.com/aio-libs/aiohttp/issues/7297>
- Issue #10790 — <https://github.com/aio-libs/aiohttp/issues/10790>
- PR #13301 (QUERY as idempotent) — <https://github.com/aio-libs/aiohttp/pull/13301>
- PR #13330 (rewinding bodies on internal retry) — <https://github.com/aio-libs/aiohttp/pull/13330>

asyncpg:

- `asyncpg/pool.py` — <https://github.com/MagicStack/asyncpg/blob/master/asyncpg/pool.py>
- `asyncpg/connection.py` — <https://github.com/MagicStack/asyncpg/blob/master/asyncpg/connection.py>
- Issue #72 — <https://github.com/MagicStack/asyncpg/issues/72>
- Issue #76 — <https://github.com/MagicStack/asyncpg/issues/76>

redis-py:

- `redis/asyncio/client.py` @ v8.1.0 — <https://github.com/redis/redis-py/blob/v8.1.0/redis/asyncio/client.py>
- `redis/asyncio/connection.py` @ v8.1.0 — <https://github.com/redis/redis-py/blob/v8.1.0/redis/asyncio/connection.py>
- `redis/retry.py` — <https://github.com/redis/redis-py/blob/master/redis/retry.py>
- `CHANGES` — <https://github.com/redis/redis-py/blob/master/CHANGES>
- Retry docs — <https://redis.readthedocs.io/en/stable/retry.html>
- Issue #261 (2013, INCR runs twice) — <https://github.com/redis/redis-py/issues/261>
- Issue #3554 (2025, XADD duplication) — <https://github.com/redis/redis-py/issues/3554>
- PR #3559 (rejected fix, key discussion) — <https://github.com/redis/redis-py/pull/3559>
- PR #3614 (3 retries by default) — <https://github.com/redis/redis-py/pull/3614>
- Issue #3008 (pool/retry/timeout revamp) — <https://github.com/redis/redis-py/issues/3008>
- Lettuce, Command execution reliability — <https://github.com/redis/lettuce/wiki/Command-execution-reliability>

asyncssh:

- `asyncssh/connection.py` — <https://github.com/ronf/asyncssh/blob/develop/asyncssh/connection.py>
- `asyncssh/misc.py` (`ConnectionLost`) — <https://github.com/ronf/asyncssh/blob/develop/asyncssh/misc.py>
- `asyncssh/client.py` (`connection_lost` callback) — <https://github.com/ronf/asyncssh/blob/develop/asyncssh/client.py>

httpx / httpcore / urllib3:

- `httpx/_transports/default.py` — <https://github.com/encode/httpx/blob/master/httpx/_transports/default.py>
- `httpcore/_async/connection.py` — <https://github.com/encode/httpcore/blob/master/httpcore/_async/connection.py>
- `httpcore/_async/connection_pool.py` — <https://github.com/encode/httpcore/blob/master/httpcore/_async/connection_pool.py>
- `httpcore/_async/http11.py` — <https://github.com/encode/httpcore/blob/master/httpcore/_async/http11.py>
- `urllib3/util/retry.py` — <https://github.com/urllib3/urllib3/blob/main/src/urllib3/util/retry.py>
