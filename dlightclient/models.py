"""Defines structured data models for dLight device data."""

from typing import TypedDict


class ColorState(TypedDict):
    """Represents the color-related state of a dLight device."""

    temperature: int


class DeviceState(TypedDict, total=False):
    """Represents the full power and visual state of a dLight device."""

    on: bool
    brightness: int
    color: ColorState


class DeviceInfo(TypedDict, total=False):
    """Represents descriptive information about a dLight device."""

    deviceId: str
    deviceModel: str
    swVersion: str
    hwVersion: str
    macAddress: str


class CommandResult(TypedDict, total=False):
    """Represents the common response format from a dLight command."""

    status: str
    commandId: str
    deviceId: str
    states: DeviceState
    _payload_length: int
