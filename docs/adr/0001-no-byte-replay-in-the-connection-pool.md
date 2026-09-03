---
status: accepted
---

# The connection pool never replays written bytes

The pool used to buffer a command's bytes and re-send them on a fresh connection
when a reused connection failed mid-exchange (`ReconnectingState`, added in #55).
Because the client also retries, the two layers multiplied: a client configured
with `max_retries=2` was measured delivering one logical `EXECUTE` to the lamp
**four** times, against a documented bound of three. We removed byte replay
entirely. Recovery from a stale pooled connection is now a **pre-flight** concern
— the pool checks liveness before handing a connection out — and any failure that
survives that check surfaces to the client's retry loop, which dials a fresh
connection per attempt.

## Considered options

- **Keep replay, gated and bounded.** Write-path only, gated on the connection
  having been reused, bounded to one, with at-least-once delivery semantics
  published in the documentation. This is the redis-py / Lettuce position and it
  is defensible *only because it is stated*. Rejected because publishing an
  at-least-once contract for commands that drive physical hardware is a poor
  trade for recovering a case the client's retry loop already covers.
- **Move the decision up to the client.** The pool reports that it reconnected
  and the client decides whether to re-send. Rejected as strictly more machinery
  than dropping replay, for the same outcome: the client already owns
  `max_retries` and is already the only layer that can know whether a command is
  safe to re-send.

## Consequences

- **This is an observable behaviour change.** A caller using `persistent=True`
  with the default `max_retries=0` previously got one silent recovery from a
  stale connection and now gets an error. Setting `max_retries=1` restores the
  old effective behaviour — with the caller having chosen it. The default was
  deliberately left at `0`: changing it would paper over one behaviour change
  with another, and defaults that silently re-send commands to hardware are how
  this problem arises in the first place.
- **Retrying on a read failure was the specific hazard, and it is unfixable
  rather than merely unfixed.** A read failure means the bytes reached the wire.
  redis-py hit exactly this (redis/redis-py#3554) and closed the fix
  (redis/redis-py#3559) as structurally impossible: a replacement connection
  runs its own handshake, so it cannot be used to collect the answer to a request
  sent on the dead one. That impossibility applies to any protocol without
  request/response correlation.
- **The premise about correlation is taken from documentation, not measured.**
  `docs/ARCHITECTURE.md` states that the device does not echo `commandId`
  reliably enough to re-correlate responses. No physical lamp was available to
  verify this. If a real device *does* echo `commandId` reliably, response
  correlation becomes possible and the gated-replay option above deserves
  reopening.
- **A pre-flight check is not a guarantee.** It detects a peer that has closed;
  it cannot detect one that vanishes between the check and the write. Those
  failures now surface as errors instead of silently replayed commands, which is
  the intended outcome.
- Reinstates the principle already stated in `docs/ARCHITECTURE.md` —
  *retry-around-exchange, not retry-inside-transport* — which the reconnect
  feature had contradicted, and restores the layering rule that private modules
  do not interpret device semantics.

Prior art surveyed across `aiohttp`, `asyncpg`, `redis-py`, `asyncssh`,
`httpx`/`httpcore` and `urllib3` is recorded on the `research/connection-reuse-retry`
branch. Every library that replays gates it on some proof of safety; the one that
does not (redis-py) has two decades of duplicate-execution reports.
