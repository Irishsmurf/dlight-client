# dlightclient/__init__.py
"""
dlight-client

A Python library for discovering and controlling dLight smart lamps locally.
"""

# Define package version
__version__ = "1.2.0" # Increment version after refactor

# Import key components to make them available at the package level
from .constants import (
    DEFAULT_TCP_PORT,
    DEFAULT_UDP_DISCOVERY_PORT,
    DEFAULT_UDP_RESPONSE_PORT,
    FACTORY_RESET_IP,
    DEFAULT_TIMEOUT,
    BROADCAST_ADDRESS,
    UDP_DISCOVERY_PAYLOAD_HEX,
    MAX_PAYLOAD_SIZE,
    STATUS_SUCCESS
)
from .exceptions import (
    DLightError,
    DLightConnectionError,
    DLightTimeoutError,
    DLightCommandError,
    DLightResponseError,
)
from .discovery import discover_devices
from .client import AsyncDLightClient
from .device import (
    DLightDevice,
)

__all__ = [
    # Client
    'AsyncDLightClient',
    # Discovery
    'discover_devices',
    # Exceptions
    'DLightError',
    'DLightConnectionError',
    'DLightTimeoutError',
    'DLightCommandError',
    'DLightResponseError',
    # Key Constants
    'DEFAULT_TCP_PORT',
    'DEFAULT_UDP_DISCOVERY_PORT',
    'DEFAULT_UDP_RESPONSE_PORT',
    'FACTORY_RESET_IP',
    'DEFAULT_TIMEOUT',
    'BROADCAST_ADDRESS',
    'UDP_DISCOVERY_PAYLOAD_HEX',
    'MAX_PAYLOAD_SIZE',
    'STATUS_SUCCESS',
    # Device
    'DLightDevice',
    # Version
    '__version__',
]

