# dlightclient/constants.py
"""Defines constant values used throughout the dlightclient library.

This module contains network configuration, communication parameters, command
types, and other shared constants to ensure consistency and ease of maintenance.
"""

import logging

# Network Configuration
DEFAULT_TCP_PORT = 3333
"""The default TCP port used for sending commands to dLight devices."""

DEFAULT_UDP_DISCOVERY_PORT = 9478
"""The UDP port that dLight devices listen on for discovery probes."""

DEFAULT_UDP_RESPONSE_PORT = 9487
"""The local UDP port that the client listens on for discovery responses."""

BROADCAST_ADDRESS = "255.255.255.255"
"""The default broadcast address for UDP discovery."""

FACTORY_RESET_IP = "192.168.4.1"
"""The static IP address of a dLight device in SoftAP mode."""

# Communication Parameters
DEFAULT_TIMEOUT = 5.0
"""The default timeout for network operations in seconds."""

MAX_PAYLOAD_SIZE = 10 * 1024
"""The maximum allowed size for a TCP response payload in bytes."""

# UDP Discovery
UDP_DISCOVERY_PAYLOAD_HEX = "476f6f676c654e50455f457269635f5761796e65"
"""The hexadecimal representation of the UDP discovery probe payload."""

# Logging
_LOGGER = logging.getLogger(__name__)
"""A logger instance for the dlightclient library."""

# Command Types
COMMAND_TYPE_EXECUTE = "EXECUTE"
"""Command type for executing actions like setting brightness or power state."""

COMMAND_TYPE_QUERY_DEVICE_STATES = "QUERY_DEVICE_STATES"
"""Command type for querying the current state of a device."""

COMMAND_TYPE_QUERY_DEVICE_INFO = "QUERY_DEVICE_INFO"
"""Command type for querying device information like model and firmware version."""

COMMAND_TYPE_SSID_CONNECT = "SSID_CONNECT"
"""Command type for sending Wi-Fi credentials to a device."""

# Response Status
STATUS_SUCCESS = "SUCCESS"
"""The status string indicating a successful command execution."""

