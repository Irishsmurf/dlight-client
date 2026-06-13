# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `DLightDevice.on_state_change(cb)` and `remove_state_listener(cb)` — register sync or async
  callbacks that fire whenever device state settles to a new value. Callbacks receive
  `(device, old_state, new_state)`; async callables are scheduled without blocking the caller.

### Fixed
- `turn_on()` and `turn_off()` rollback now correctly removes the `"on"` key when it was absent
  before the command, rather than setting it to a default value.

## [1.6.1] — 2026-06-10

### Changed
- Internal version bump; no functional changes.

## [1.6.0] — 2026-06-10

### Added
- `ConnectionPool` extracted to `_pool.py`; `_async_send_tcp_command` is now a thin retry loop over the pool.
- Wire-format codec extracted to `_frame.py` (`encode_command`, `read_response`, `mask_command`).
- Technical architecture document (`docs/ARCHITECTURE.md`).
- Real in-process `FakeDLightServer` replaces asyncio stream mocks across the entire test suite.

### Changed
- `async with AsyncDLightClient()` no longer implicitly enables `persistent`; pass `persistent=True` explicitly. (Breaking if you relied on the implicit behaviour.)
- Package version is now single-sourced from `dlightclient.__version__` via `pyproject.toml`.

### Fixed
- `__aenter__` no longer mutates `persistent`; import-fallback test dummies removed.

## [1.5.1] — 2026-05-01

### Security
- Credentials (`password` field in `SSID_CONNECT` commands) are now masked in all debug log output regardless of log level.

## [1.5.0] — 2026-04-20

### Added
- Automatic retry logic with exponential backoff (`max_retries`, `retry_backoff` constructor arguments) — **DL-003**.
- Per-device `asyncio.Lock` in the connection pool prevents concurrent request desynchronisation.
- Idle timeout eviction: connections unused longer than `idle_timeout` (default 60 s) are closed and removed from the pool.
- TLS support: pass `ssl=True` or a custom `ssl.SSLContext` to `AsyncDLightClient`; `--ssl` / `--insecure` CLI flags.
- Command IDs now use `secrets.token_hex(4)` for cryptographic uniqueness.
- State caching and optimistic updates in `DLightDevice` — **DL-005**.

### Changed
- `get_state()` returns the cached value by default; pass `force_update=True` to query the device.

## [1.4.0] — 2026-03-15

### Added
- Python 3.11, 3.12, and 3.13 added to the supported matrix and CI workflow.

## [1.3.2] — 2026-03-10

### Fixed
- `pyproject.toml`: modernised `license` field format; resolved `setuptools` deprecation warnings during build.

## [1.3.0] — 2026-03-01

### Added
- Connection pooling and persistent TCP connections (`persistent=True`, `idle_timeout`) — **DL-001**.
- `async with AsyncDLightClient(...)` context manager for automatic pool cleanup.
- Feature specification documents added to `issues/` directory for DL-001 through DL-005.

## [1.2.0] — 2025-11-01

### Added
- Significantly expanded test coverage for `AsyncDLightClient` and `DLightDevice`.

### Fixed
- Echo detection: a device that echoes a command verbatim now raises `DLightResponseError` instead of silently returning malformed data.

## [1.1.0] — 2025-08-01

### Added
- `DLightDevice` high-level facade: `turn_on`, `turn_off`, `set_brightness`, `set_color_temperature`, `get_state`, `get_info`, `flash`.
- Comprehensive docstrings on all public classes and methods.

## [1.0.1] — 2025-06-01

### Changed
- Full async/await rewrite using `asyncio` throughout; blocking socket calls removed.

## [0.1.0] — 2025-04-11

### Added
- Initial release: `AsyncDLightClient`, `discover_devices`, UDP broadcast discovery, TCP command protocol (4-byte length prefix + JSON).
- PyPI packaging and GitHub Actions CI/CD (test matrix, trusted publishing to PyPI).

[Unreleased]: https://github.com/irishsmurf/dlight-client/compare/v1.6.1...HEAD
[1.6.1]: https://github.com/irishsmurf/dlight-client/compare/v1.6.0...v1.6.1
[1.6.0]: https://github.com/irishsmurf/dlight-client/compare/v1.5.1...v1.6.0
[1.5.1]: https://github.com/irishsmurf/dlight-client/compare/v1.5.0...v1.5.1
[1.5.0]: https://github.com/irishsmurf/dlight-client/compare/v1.4.0...v1.5.0
[1.4.0]: https://github.com/irishsmurf/dlight-client/compare/v1.3.2...v1.4.0
[1.3.2]: https://github.com/irishsmurf/dlight-client/compare/v1.3.0...v1.3.2
[1.3.0]: https://github.com/irishsmurf/dlight-client/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/irishsmurf/dlight-client/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/irishsmurf/dlight-client/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/irishsmurf/dlight-client/compare/v0.1.0...v1.0.1
[0.1.0]: https://github.com/irishsmurf/dlight-client/releases/tag/v0.1.0
