# dlightclient/_frame.py
"""Wire-format codec for the dLight TCP protocol.

Commands are sent as bare UTF-8 JSON. Responses are a 4-byte big-endian
length prefix followed by a JSON payload.
"""

import asyncio
import json
import struct
from typing import Any, Dict, Optional

from .constants import MAX_PAYLOAD_SIZE, STATUS_SUCCESS
from .exceptions import (
    DLightCommandError,
    DLightConnectionError,
    DLightResponseError,
    DLightTimeoutError,
)
from .models import CommandResult

_SENSITIVE_KEYS = ("password", "ssid")


def mask_command(command: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a copy of the command safe for logging (credentials masked)."""
    if not any(key in command for key in _SENSITIVE_KEYS):
        return command
    masked = command.copy()
    for key in _SENSITIVE_KEYS:
        if key in masked:
            masked[key] = "********"
    return masked


def encode_command(command: Dict[str, Any]) -> bytes:
    """Serializes a command dict to the bytes sent on the wire.

    Raises:
        DLightCommandError: If the command cannot be serialized to JSON.
    """
    try:
        return json.dumps(command).encode("utf-8")
    except TypeError as e:
        raise DLightCommandError(f"Failed to serialize command to JSON: {e}\nCommand: {mask_command(command)}") from e


async def read_response(
    reader: asyncio.StreamReader,
    timeout: float,
    operation: str,
    command: Optional[Dict[str, Any]] = None,
) -> CommandResult:
    """Reads and validates one framed response from the device.

    An empty payload is an acknowledgement; it is returned as a synthesized
    success response. If ``command`` is given, a response that merely echoes
    it back is rejected.

    Raises:
        DLightTimeoutError: If reading the header or payload times out.
        DLightConnectionError: If a network error occurs while reading.
        DLightResponseError: If the response is invalid or indicates an error.
    """
    try:
        header = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
    except asyncio.TimeoutError:
        raise DLightTimeoutError(f"Timeout reading header for {operation}") from None
    except asyncio.IncompleteReadError as e:
        raise DLightResponseError(
            f"Connection closed unexpectedly while reading header for {operation}. "
            f"Expected 4 bytes, got {len(e.partial)}: {e.partial!r}"
        ) from e
    except OSError as e:
        raise DLightConnectionError(f"Network error reading header for {operation}: {e}") from e

    payload_length = struct.unpack(">I", header)[0]
    if payload_length > MAX_PAYLOAD_SIZE:
        raise DLightResponseError(f"Payload length {payload_length} exceeds maximum limit {MAX_PAYLOAD_SIZE}")

    if payload_length == 0:
        # Some commands acknowledge with an empty payload; treat as success.
        return {"status": STATUS_SUCCESS}

    try:
        payload_bytes = await asyncio.wait_for(reader.readexactly(payload_length), timeout=timeout)
    except asyncio.TimeoutError:
        raise DLightTimeoutError(f"Timeout reading payload ({payload_length} bytes) for {operation}") from None
    except asyncio.IncompleteReadError as e:
        raise DLightResponseError(f"Connection closed unexpectedly while reading payload for {operation}.") from e
    except OSError as e:
        raise DLightConnectionError(f"Network error reading payload for {operation}: {e}") from e

    try:
        response: CommandResult = json.loads(payload_bytes.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise DLightResponseError(f"Failed to decode JSON payload: {e}\nRaw Payload: {payload_bytes!r}") from e
    except UnicodeDecodeError as e:
        raise DLightResponseError(f"Failed to decode payload as UTF-8: {e}\nRaw Payload: {payload_bytes!r}") from e

    if command is not None and response == command:
        raise DLightResponseError("Device echoed back the command (unrecognized?).")

    status = response.get("status")
    if status != STATUS_SUCCESS:
        raise DLightResponseError(f"dLight returned non-SUCCESS status: '{status}'")

    return response
