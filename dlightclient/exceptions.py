# dlightclient/exceptions.py
"""Custom exception types for the dlightclient library."""

class DLightError(Exception):
    """Base exception for dlightclient errors."""
    pass

class DLightConnectionError(DLightError):
    """Error connecting to the dLight device."""
    pass

class DLightTimeoutError(DLightConnectionError):
    """Timeout during communication with the dLight device."""
    pass

class DLightCommandError(DLightError):
    """Error related to command formatting or execution."""
    pass

class DLightResponseError(DLightError):
    """Error parsing or interpreting the response from the dLight device."""
    pass

