# dlightclient/exceptions.py
"""Custom exception types for the dlightclient library."""


class DLightError(Exception):
    """The base exception for all dlightclient errors."""


class DLightConnectionError(DLightError):
    """Raised when a connection to a dLight device cannot be established."""


class DLightTimeoutError(DLightConnectionError):
    """Raised when a network operation times out."""


class DLightCommandError(DLightError):
    """Raised for errors related to command formatting or execution."""


class DLightResponseError(DLightError):
    """Raised when a response from a dLight device is invalid or indicates an error."""
