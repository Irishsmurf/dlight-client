# Contributing to dlight-client

Contributions are welcome — bug fixes, tests, documentation, and features aligned with the [roadmap](docs/roadmap.md). This document covers setup and conventions.

## Quick start

```bash
git clone https://github.com/irishsmurf/dlight-client.git
cd dlight-client
python -m venv .venv && source .venv/bin/activate
pip install -e .
pip install pytest pytest-asyncio flake8 ruff
python -m pytest tests/
```

All tests use an in-process fake dLight server — no physical hardware needed.

## What we welcome

- Bug fixes with a regression test
- Tests for untested behaviour
- Documentation improvements (typos, clarity, missing examples)
- Features on the roadmap — open an Issue first for significant work

## Project layout

```
dlightclient/            Main package (see docs/architecture.md for layers)
tests/
  fake_server.py         Real asyncio server for testing — use this, not mocks
  test_pool_regressions.py  Concurrency invariants — do not weaken
tools/
  fake_dlight_server.py  Standalone test server for manual experiments
docs/                    MkDocs source
issues/                  Roadmap feature specifications
```

## Testing

- Use `FakeDLightServer` (`tests/fake_server.py`) — a real asyncio TCP server speaking the actual protocol. Do not mock asyncio streams.
- Assert observable behaviour (connection counts, return values), not internal call sequences.
- New behaviour = new test. Bug fix = regression test.
- `tests/test_pool_regressions.py` encodes pool concurrency invariants. If your change breaks them, fix the implementation.

```bash
python -m pytest tests/
flake8 dlightclient tests --max-line-length=120
ruff check dlightclient/
```

## Code style

- 120-character line limit
- Type hints on all public methods
- Comments only when the *why* is non-obvious

## Commit conventions

[Conventional Commits](https://www.conventionalcommits.org/): `feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`, `perf:`. One logical change per commit.

## Pull requests

1. Branch from `main`
2. Tests pass and CI is green
3. PR title uses conventional commit format
4. Describe what changed, why, and how you tested it

## Release process (maintainers)

1. Bump `dlightclient.__version__` in `dlightclient/__init__.py`
2. Update `CHANGELOG.md` (move `[Unreleased]` entries to a new version heading)
3. Commit: `chore: bump version to X.Y.Z`
4. `git tag vX.Y.Z && git push origin vX.Y.Z`
5. GitHub Actions publishes to PyPI automatically via OIDC trusted publishing
