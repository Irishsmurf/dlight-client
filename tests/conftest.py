# tests/conftest.py
"""Shared pytest configuration for the dlight-client test suite."""

import pytest

try:
    import pytest_socket
except ImportError:  # pytest-socket not installed; nothing to undo
    pytest_socket = None


@pytest.fixture(autouse=True)
def _allow_loopback_sockets():
    """Re-enable socket creation for every test.

    Development environments that have pytest-homeassistant-custom-component
    installed get sockets disabled globally by that plugin. This suite runs a
    real loopback TCP server (tests/fake_server.py), so it needs them back.
    """
    if pytest_socket is not None:
        pytest_socket.enable_socket()
    yield
