# Contributing

Contributions are welcome — bug fixes, tests, documentation improvements, and features aligned with the [Roadmap](roadmap.md). This page covers everything you need to get a development environment running and submit a pull request.

---

## Quick setup

```bash
git clone https://github.com/irishsmurf/dlight-client.git
cd dlight-client
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
pip install pytest pytest-asyncio flake8 ruff
```

Run the test suite:

```bash
python -m pytest tests/
```

All tests pass against a real in-process TCP server — no network hardware required.

---

## What we welcome

- Bug fixes with a regression test
- New tests for existing behaviour
- Documentation improvements (typos, clarity, missing examples)
- Features from the [Roadmap](roadmap.md) — open an issue first to align on approach
- Performance improvements with benchmarks

For significant new features, please open a GitHub Issue before writing code so we can discuss design before you invest the time.

---

## Project layout

```
dlightclient/        Public package
  __init__.py        Exports and __version__
  client.py          AsyncDLightClient
  device.py          DLightDevice facade
  discovery.py       UDP broadcast discovery
  cli.py             Command-line interface
  models.py          TypedDicts
  exceptions.py      Exception hierarchy
  constants.py       Ports, limits, protocol literals
  _pool.py           ConnectionPool (private)
  _frame.py          Wire-format codec (private)

tests/
  fake_server.py     In-process asyncio dLight server for testing
  conftest.py        pytest fixtures
  test_dlight.py     Core integration tests
  test_device.py     DLightDevice tests
  test_frame.py      Codec tests
  test_cli.py        CLI tests
  test_retry.py      Retry logic tests
  test_pool_regressions.py  Concurrency invariants (do not weaken)

tools/
  fake_dlight_server.py  Standalone test server (run separately)

docs/                MkDocs source
issues/              Roadmap feature specifications
```

---

## Testing philosophy

The test suite uses `FakeDLightServer` (`tests/fake_server.py`) — a real `asyncio.start_server` instance that speaks the actual dLight wire protocol. It supports scriptable faults: connection hangs, TCP resets, truncated frames, and stale delayed replies.

**Rules:**

- Do not mock `asyncio` streams directly. Use `FakeDLightServer` instead — it tests the actual wire codec and connection lifecycle.
- Assert observable behaviour (connection count, bytes on the wire, return values), not internal call sequences.
- Every new behaviour needs a new test. Every bug fix needs a regression test.
- `tests/test_pool_regressions.py` encodes the pool's concurrency invariants. If your change causes these to fail, fix the implementation — do not adjust the tests to pass.

To run the standalone server for manual testing:

```bash
python tools/fake_dlight_server.py
```

---

## Code style

- **Line length:** 120 characters maximum.
- **Linting:** `ruff check dlightclient/` and `flake8 dlightclient tests --max-line-length=120`.
- **Type hints:** required on all public class methods and module-level functions.
- **Comments:** only when the *why* is non-obvious. No docstrings describing what the code already says.

---

## Commit conventions

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add mDNS discovery support
fix: evict connection on partial frame read
docs: update CLI reference for --discover-duration
chore: bump version to 1.7.0
test: add regression test for concurrent commands to same device
refactor: extract retry backoff into helper
```

One logical change per commit.

---

## Pull requests

1. Branch from `main`: `git checkout -b feat/my-feature`
2. Write tests first if fixing a bug.
3. Ensure CI is green: `python -m pytest tests/` and `flake8 dlightclient tests --max-line-length=120`.
4. Title the PR like a conventional commit: `feat: ...`, `fix: ...`, etc.
5. In the PR description: what changed, why, and how you tested it.
6. Link to a roadmap issue or GitHub Issue if applicable.

---

## Release process (maintainers)

1. Bump `__version__` in `dlightclient/__init__.py`.
2. Update `CHANGELOG.md`: move items from `[Unreleased]` to a new `[X.Y.Z] — YYYY-MM-DD` heading.
3. Commit: `chore: bump version to X.Y.Z`.
4. Tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
5. GitHub Actions (`python-publish.yml`) builds and publishes to PyPI automatically via OIDC trusted publishing.
