# Roadmap

This page tracks planned and completed enhancements. Detailed specifications for each item live in the `issues/` directory of the repository.

!!! info "Want to contribute?"
    If you'd like to work on a planned item, open a GitHub Issue to discuss your approach before writing code. See [Contributing](contributing.md) for setup instructions.

---

## Feature status

| ID | Feature | Status | Milestone |
|---|---|---|---|
| DL-001 | Persistent TCP connections + connection pool | ✅ Done | v1.3.0 |
| DL-003 | Automatic retry logic with exponential backoff | ✅ Done | v1.5.0 |
| DL-005 | State caching and optimistic updates | ✅ Done | v1.5.0 |
| DL-002 | Granular CLI subcommands | ⏳ Planned | v1.7.0 |
| DL-004 | mDNS / Zeroconf discovery | ⏳ Planned | v1.8.0 |

---

## Planned

### DL-002 — Granular CLI subcommands

Replace the current fixed interaction sequence with individual subcommands, making the CLI scriptable from shell scripts and cron jobs.

**Proposed interface:**

```bash
dlight discover
dlight on   --ip 192.168.1.123 --id DL12345
dlight off  --ip 192.168.1.123 --id DL12345
dlight brightness 75  --ip 192.168.1.123 --id DL12345
dlight color-temp 3000 --ip 192.168.1.123 --id DL12345
```

The existing `--discover` / `--ip` / `--id` flags remain supported for backwards compatibility.

### DL-004 — mDNS / Zeroconf discovery

Add mDNS-based discovery via `zeroconf` as an alternative (not replacement) to the current UDP broadcast. Lamps that advertise themselves via mDNS will be discoverable on networks where UDP broadcast is blocked or the devices are on a different subnet.

`discover_devices()` will gain an optional `mdns=True` parameter. Existing code using the default call signature does not need changes.

---

## Completed

### DL-001 — Persistent TCP connections (v1.3.0)

Connection pooling keyed by `(host, port, ssl)` with per-device `asyncio.Lock`, idle timeout eviction, and unconditional eviction on any exchange failure.

### DL-003 — Automatic retry logic (v1.5.0)

`max_retries` and `retry_backoff` constructor parameters on `AsyncDLightClient`. Retries only on `DLightTimeoutError` and `DLightConnectionError`; never on protocol errors.

### DL-005 — State caching and optimistic updates (v1.5.0)

Internal `_state` cache in `DLightDevice` with optimistic mutation before network calls and rollback on failure. `get_state()` returns the cache without a network call; `force_update=True` bypasses it.
