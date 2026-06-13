# dlightclient/__init__.py
"""
dlight-client

A Python library for discovering and controlling dLight smart lamps locally.
"""

# Define package version (single source of truth; pyproject.toml reads this)
__version__ = "1.6.1"


# Import key components to make them available at the package level
from .client import AsyncDLightClient
from .constants import (
    BROADCAST_ADDRESS,
    DEFAULT_TCP_PORT,
    DEFAULT_TIMEOUT,
    DEFAULT_UDP_DISCOVERY_PORT,
    DEFAULT_UDP_RESPONSE_PORT,
    FACTORY_RESET_IP,
    MAX_PAYLOAD_SIZE,
    STATUS_SUCCESS,
    UDP_DISCOVERY_PAYLOAD_HEX,
)
from .device import (
    DLightDevice,
)
from .discovery import discover_devices, discover_devices_stream
from .exceptions import (
    DLightCommandError,
    DLightConnectionError,
    DLightError,
    DLightResponseError,
    DLightTimeoutError,
)
from .models import LightScene

__all__ = [
    # Client
    "AsyncDLightClient",
    # Discovery
    "discover_devices",
    "discover_devices_stream",
    # Exceptions
    "DLightError",
    "DLightConnectionError",
    "DLightTimeoutError",
    "DLightCommandError",
    "DLightResponseError",
    # Key Constants
    "DEFAULT_TCP_PORT",
    "DEFAULT_UDP_DISCOVERY_PORT",
    "DEFAULT_UDP_RESPONSE_PORT",
    "FACTORY_RESET_IP",
    "DEFAULT_TIMEOUT",
    "BROADCAST_ADDRESS",
    "UDP_DISCOVERY_PAYLOAD_HEX",
    "MAX_PAYLOAD_SIZE",
    "STATUS_SUCCESS",
    # Device
    "DLightDevice",
    "LightScene",
    # Version
    "__version__",
]
