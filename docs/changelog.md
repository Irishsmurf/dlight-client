---
title: Changelog
---

# Changelog

All notable changes to this project will be documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

The canonical source is [`CHANGELOG.md`](https://github.com/irishsmurf/dlight-client/blob/main/CHANGELOG.md) in the repository root.

---

## [Unreleased]

---

## [1.6.1] — 2026-06-10

### Changed
- Internal version bump; no functional changes.

---

## [1.6.0] — 2026-06-10

### Added
- `ConnectionPool` extracted to `_pool.py`; `_async_send_tcp_command` is now a thin retry loop over the pool.
- Wire-format codec extracted to `_frame.py` (`encode_command`, `read_response`, `mask_command`).
- Technical architecture document (`docs/ARCHITECTURE.md`).
- Real in-process `FakeDLightServer` replaces asyncio stream mocks across the entire test suite.

### Changed
- `async with AsyncDLightClient()` no longer implicitly enables `persistent`; pass `persistent=True` explicitly.
- Package version single-sourced from `dlightclient.__version__` via `pyproject.toml`.

### Fixed
- `__aenter__` no longer mutates `persistent`; import-fallback test dummies removed.

---

## [1.5.1] — 2026-05-01

### Security
- Credentials (`password`) masked in all debug log output regardless of log level.

---

## [1.5.0] — 2026-04-20

### Added
- Automatic retry logic with exponential backoff (`max_retries`, `retry_backoff`) — **DL-003**.
- Per-device `asyncio.Lock` in the connection pool.
- Idle timeout eviction (default 60 s).
- TLS support: `ssl=True` or custom `ssl.SSLContext`; `--ssl` / `--insecure` CLI flags.
- State caching and optimistic updates in `DLightDevice` — **DL-005**.

### Changed
- `get_state()` returns the cached value by default; pass `force_update=True` to query the device.

---

## [1.4.0] — 2026-03-15

### Added
- Python 3.11, 3.12, and 3.13 added to the supported matrix and CI.

---

## [1.3.2] — 2026-03-10

### Fixed
- `pyproject.toml` licence field modernised; resolved `setuptools` deprecation warnings.

---

## [1.3.0] — 2026-03-01

### Added
- Connection pooling and persistent TCP connections (`persistent=True`, `idle_timeout`) — **DL-001**.
- `async with AsyncDLightClient(...)` context manager for automatic pool cleanup.

---

## [1.2.0] — 2025-11-01

### Added
- Significantly expanded test coverage.

### Fixed
- Echo detection: device echoing a command verbatim now raises `DLightResponseError`.

---

## [1.1.0] — 2025-08-01

### Added
- `DLightDevice` high-level facade: `turn_on`, `turn_off`, `set_brightness`, `set_color_temperature`, `get_state`, `get_info`, `flash`.

---

## [1.0.1] — 2025-06-01

### Changed
- Full async/await rewrite using `asyncio`; blocking socket calls removed.

---

## [0.1.0] — 2025-04-11

### Added
- Initial release: `AsyncDLightClient`, `discover_devices`, UDP discovery, TCP command protocol.
- PyPI packaging and GitHub Actions CI/CD.
