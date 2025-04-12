# dlightclient/constants.py
"""Constants used by the dlightclient library."""

import logging

# Network Configuration
DEFAULT_TCP_PORT = 3333
DEFAULT_UDP_DISCOVERY_PORT = 9478
DEFAULT_UDP_RESPONSE_PORT = 9487
BROADCAST_ADDRESS = "255.255.255.255" # Use specific broadcast if known, else default
FACTORY_RESET_IP = "192.168.4.1"     # IP address when device is in SoftAP mode

# Communication Parameters
DEFAULT_TIMEOUT = 5.0  # seconds
MAX_PAYLOAD_SIZE = 10 * 1024 # 10 KB sanity limit for TCP response payload

# UDP Discovery
UDP_DISCOVERY_PAYLOAD_HEX = "476f6f676c654e50455f457269635f5761796e65" # "GoogleNPE_Eric_Wayne"

# Logging - Define a root logger for the library if desired,
# or let applications configure their own logging.
# Using __name__ ensures loggers are named after the module.
_LOGGER = logging.getLogger(__name__)

# Command Types (as strings, based on observed usage)
COMMAND_TYPE_EXECUTE = "EXECUTE"
COMMAND_TYPE_QUERY_DEVICE_STATES = "QUERY_DEVICE_STATES"
COMMAND_TYPE_QUERY_DEVICE_INFO = "QUERY_DEVICE_INFO"
COMMAND_TYPE_SSID_CONNECT = "SSID_CONNECT"

# Response Status
STATUS_SUCCESS = "SUCCESS"

