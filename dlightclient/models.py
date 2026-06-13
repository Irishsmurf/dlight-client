"""Defines structured data models for dLight device data."""

from dataclasses import dataclass
from typing import ClassVar, TypedDict


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


@dataclass(frozen=True)
class LightScene:
    """A brightness + colour temperature preset.

    Can be used as a named constant or constructed inline::

        await device.apply_scene(LightScene.READING)
        await device.apply_scene(LightScene(brightness=50, temperature=3500))
    """

    brightness: int
    temperature: int

    READING: ClassVar["LightScene"]
    EVENING: ClassVar["LightScene"]
    DAYLIGHT: ClassVar["LightScene"]
    FOCUS: ClassVar["LightScene"]


LightScene.READING = LightScene(brightness=70, temperature=4000)
LightScene.EVENING = LightScene(brightness=30, temperature=2700)
LightScene.DAYLIGHT = LightScene(brightness=100, temperature=6000)
LightScene.FOCUS = LightScene(brightness=100, temperature=5000)
