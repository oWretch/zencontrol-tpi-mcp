"""Typed command wrappers for the ZenControl TPI Advanced protocol.

Each function corresponds to a TPI command and returns a Python-native value.
All functions accept a ``ZenControlTPI`` client and required parameters.

Protocol constants:
- MAX_SYSVAR = 148 (system variables 0–147)
- MAX_SCENE   = 12  (scenes 0–11)
- Profile 0xFFFF = return to scheduled profile
"""

from __future__ import annotations

import struct
from datetime import datetime
from typing import TYPE_CHECKING

from zencontrol_tpi_mcp.models.schemas import (
    DaliColourInfo,
    DaliColourType,
    InstanceType,
    TpiCommand,
)

if TYPE_CHECKING:
    from zencontrol_tpi_mcp.api.client import ZenControlTPI

# ---------------------------------------------------------------------------
# Protocol limits
# ---------------------------------------------------------------------------

MAX_SYSVAR = 148
MAX_SCENE = 12
PROFILE_SCHEDULED = 0xFFFF


# ---------------------------------------------------------------------------
# Address helpers
# ---------------------------------------------------------------------------


def ecd_wire(ecd_number: int) -> int:
    """Convert an ECD short address (0–63) to its TPI wire format (64–127).

    In the ZenControl TPI, DALI control devices (ECDs — sensors, buttons) are
    addressed as 64 + short_address to distinguish them from control gear (ECGs,
    addressed as 0–63). All ECD-specific commands must use this offset.
    """
    if not 0 <= ecd_number <= 63:
        raise ValueError(f"ECD short address must be 0–63, got {ecd_number}")
    return ecd_number + 64


# Internal alias used throughout this module
_ecd_wire = ecd_wire


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _parse_bitmask_list(data: bytes) -> list[int]:
    """Parse a bitmask response into a sorted list of set-bit indices.

    Each byte represents 8 items. Bit 0 of byte 0 = index 0; bit 7 of byte 7 = index 63.
    Used for QUERY_CONTROL_GEAR_DALI_ADDRESSES (8 bytes → addresses 0–63).
    """
    result = []
    for byte_index, byte_value in enumerate(data):
        for bit_index in range(8):
            if byte_value & (1 << bit_index):
                result.append(byte_index * 8 + bit_index)
    return result


def _parse_2byte_bitmask_high_low(data: bytes) -> list[int]:
    """Parse a 2-byte bitmask where high byte = items 8–15, low byte = items 0–7.

    Used for group membership and scene number responses.
    """
    if len(data) != 2:
        return []
    result = []
    for i in range(8):
        if data[0] & (1 << i):
            result.append(i + 8)
    for i in range(8):
        if data[1] & (1 << i):
            result.append(i)
    return sorted(result)


def _decode_string(data: bytes) -> str | None:
    """Decode a null-terminated or raw byte string from a response payload."""
    if not data:
        return None
    try:
        text = data.rstrip(b"\x00").decode("utf-8", errors="replace")
        return text or None
    except Exception:
        return None


def _parse_colour_bytes(data: bytes) -> DaliColourInfo | None:
    """Parse colour response bytes into a DaliColourInfo.

    Colour format:
    - TC  (0x20): [0x20, kelvin_hi, kelvin_lo]            (3 or 7 bytes)
    - XY  (0x10): [0x10, x_hi, x_lo, y_hi, y_lo]         (5 or 7 bytes)
    - RGBWAF (0x80): [0x80, R, G, B, W, A, F]             (7 bytes)
    """
    if not data:
        return None
    colour_type_byte = data[0]
    try:
        colour_type = DaliColourType(colour_type_byte)
    except ValueError:
        return None

    if colour_type == DaliColourType.TC and len(data) >= 3:
        kelvin = (data[1] << 8) | data[2]
        return DaliColourInfo(colour_type=colour_type, tc_kelvin=kelvin)
    if colour_type == DaliColourType.XY and len(data) >= 5:
        x = (data[1] << 8) | data[2]
        y = (data[3] << 8) | data[4]
        return DaliColourInfo(colour_type=colour_type, x=x, y=y)
    if colour_type == DaliColourType.RGBWAF and len(data) >= 7:
        return DaliColourInfo(
            colour_type=colour_type,
            red=data[1],
            green=data[2],
            blue=data[3],
            white=data[4],
            amber=data[5],
            free=data[6],
        )
    return None


def _colour_data_bytes(colour: DaliColourInfo) -> tuple[int, bytes]:
    """Return (colour_type_byte, 7-byte colour_data) for a DALI Colour frame.

    Unused bytes are padded with 0xFF as per the TPI spec.
    """
    if colour.colour_type == DaliColourType.TC:
        if colour.tc_kelvin is None:
            raise ValueError("tc_kelvin required for TC colour")
        hi = (colour.tc_kelvin >> 8) & 0xFF
        lo = colour.tc_kelvin & 0xFF
        return DaliColourType.TC, bytes([hi, lo, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])
    if colour.colour_type == DaliColourType.XY:
        if colour.x is None or colour.y is None:
            raise ValueError("x and y required for XY colour")
        return DaliColourType.XY, struct.pack(">HH", colour.x, colour.y) + bytes([0xFF, 0xFF, 0xFF])
    if colour.colour_type == DaliColourType.RGBWAF:
        for field in ("red", "green", "blue"):
            if getattr(colour, field) is None:
                raise ValueError(f"{field} required for RGBWAF colour")
        return DaliColourType.RGBWAF, bytes(
            [
                colour.red or 0,
                colour.green or 0,
                colour.blue or 0,
                colour.white or 0,
                colour.amber or 0,
                colour.free or 0,
                0x00,  # control byte
            ]
        )
    raise ValueError(f"Unsupported colour type: {colour.colour_type}")


# ---------------------------------------------------------------------------
# Controller commands
# ---------------------------------------------------------------------------


async def query_controller_label(tpi: ZenControlTPI) -> str | None:
    """Query the controller label string."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_CONTROLLER_LABEL, address=0)
    if resp.is_answer:
        return _decode_string(resp.data)
    return None


async def query_controller_version(tpi: ZenControlTPI) -> str | None:
    """Query the controller firmware version as 'major.minor.patch'."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_CONTROLLER_VERSION_NUMBER, address=0)
    if resp.is_answer and len(resp.data) == 3:
        return f"{resp.data[0]}.{resp.data[1]}.{resp.data[2]}"
    return None


async def query_controller_fitting_number(tpi: ZenControlTPI) -> str | None:
    """Query the controller fitting number string."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_CONTROLLER_FITTING_NUMBER, address=0)
    if resp.is_answer:
        return _decode_string(resp.data)
    return None


async def query_controller_startup_complete(tpi: ZenControlTPI) -> bool:
    """Return True if the controller has completed its startup sequence."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_CONTROLLER_STARTUP_COMPLETE, address=0)
    return resp.is_ok


async def query_is_dali_ready(tpi: ZenControlTPI) -> bool:
    """Return True if the DALI line is ready (no fault)."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_IS_DALI_READY, address=0)
    return resp.is_ok


# ---------------------------------------------------------------------------
# Group commands
# ---------------------------------------------------------------------------


async def query_group_numbers(tpi: ZenControlTPI) -> list[int]:
    """Return a sorted list of configured DALI group numbers (0–15)."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_GROUP_NUMBERS, address=0)
    if resp.is_answer:
        return sorted(resp.data)
    return []


async def query_group_label(tpi: ZenControlTPI, group: int) -> str | None:
    """Query the label for a DALI group (0–15)."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_GROUP_LABEL, address=group)
    if resp.is_answer:
        return _decode_string(resp.data)
    return None


async def query_group_by_number(tpi: ZenControlTPI, group: int) -> dict | None:
    """Query current occupancy and level for a group.

    Returns:
        dict with keys: group_number (int), occupancy (bool), level (int), or None on failure.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_GROUP_BY_NUMBER, address=group)
    if resp.is_answer and len(resp.data) == 3:
        return {
            "group_number": resp.data[0],
            "occupancy": bool(resp.data[1]),
            "level": resp.data[2],
        }
    return None


async def query_group_membership_by_address(tpi: ZenControlTPI, ecg_address: int) -> list[int]:
    """Return sorted list of group numbers (0–15) that an ECG address belongs to.

    Response is 2 bytes: high byte = groups 8–15, low byte = groups 0–7.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_GROUP_MEMBERSHIP_BY_ADDRESS, address=ecg_address)
    if resp.is_answer:
        return _parse_2byte_bitmask_high_low(resp.data)
    return []


# ---------------------------------------------------------------------------
# Device (ECG) commands
# ---------------------------------------------------------------------------


async def query_control_gear_addresses(tpi: ZenControlTPI) -> list[int]:
    """Return sorted list of ECG short addresses (0–63) present in the database.

    Response is an 8-byte bitmask (bit n of byte n//8 = address n).
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_CONTROL_GEAR_DALI_ADDRESSES, address=0)
    if resp.is_answer and len(resp.data) == 8:
        return _parse_bitmask_list(resp.data)
    return []


async def query_dali_device_label(tpi: ZenControlTPI, address: int) -> str | None:
    """Query the label for a DALI ECG or ECD address."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_DALI_DEVICE_LABEL, address=address)
    if resp.is_answer:
        return _decode_string(resp.data)
    return None


async def query_dali_fitting_number(tpi: ZenControlTPI, address: int) -> str | None:
    """Query the fitting number string for a DALI ECG or ECD address."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_DALI_FITTING_NUMBER, address=address)
    if resp.is_answer:
        return _decode_string(resp.data)
    return None


async def query_dali_ean(tpi: ZenControlTPI, address: int) -> int | None:
    """Query the EAN/GTIN (European Article Number) for a DALI ECG or ECD.

    Returns a 48-bit integer, or None on failure.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_DALI_EAN, address=address)
    if resp.is_answer and len(resp.data) == 6:
        value = 0
        for b in resp.data:
            value = (value << 8) | b
        return value
    return None


async def query_dali_serial(tpi: ZenControlTPI, address: int) -> int | None:
    """Query the serial number for a DALI ECG or ECD.

    Returns a 64-bit integer, or None on failure.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_DALI_SERIAL, address=address)
    if resp.is_answer and len(resp.data) == 8:
        value = 0
        for b in resp.data:
            value = (value << 8) | b
        return value
    return None


async def query_dali_cg_type(tpi: ZenControlTPI, ecg_address: int) -> list[int]:
    """Query the device type bitmask for a DALI ECG.

    Returns a list of device type numbers (e.g., 6 = LED, 8 = colour control).
    """
    resp = await tpi.send_basic(command=TpiCommand.DALI_QUERY_CG_TYPE, address=ecg_address)
    if resp.is_answer and len(resp.data) == 4:
        return _parse_bitmask_list(resp.data)
    return []


# ---------------------------------------------------------------------------
# DMX device commands
# ---------------------------------------------------------------------------


async def query_dmx_device_numbers(tpi: ZenControlTPI) -> list[int]:
    """Return sorted list of configured DMX device numbers."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_DMX_DEVICE_NUMBERS, address=0)
    if resp.is_answer:
        return sorted(resp.data)
    return []


async def query_dmx_device_by_number(tpi: ZenControlTPI, device_number: int) -> dict | None:
    """Query DMX device channel configuration.

    Returns dict with keys: start_channel, stop_channel, or None on failure.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_DMX_DEVICE_BY_NUMBER, address=device_number)
    if resp.is_answer and len(resp.data) >= 4:
        start_ch = (resp.data[0] << 8) | resp.data[1]
        stop_ch = (resp.data[2] << 8) | resp.data[3]
        return {"start_channel": start_ch, "stop_channel": stop_ch}
    return None


async def query_dmx_device_label(tpi: ZenControlTPI, device_number: int) -> str | None:
    """Query the label for a DMX device."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_DMX_DEVICE_LABEL_BY_NUMBER, address=device_number)
    if resp.is_answer:
        return _decode_string(resp.data)
    return None


async def query_dmx_level_by_channel(tpi: ZenControlTPI, channel: int) -> int | None:
    """Query the current level on a DMX channel.

    Returns level 0–255, or None on failure.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_DMX_LEVEL_BY_CHANNEL, address=channel)
    if resp.is_answer and len(resp.data) >= 1:
        return resp.data[0]
    return None


# ---------------------------------------------------------------------------
# Colour commands
# ---------------------------------------------------------------------------


async def query_dali_colour(tpi: ZenControlTPI, address: int) -> DaliColourInfo | None:
    """Query the current colour state of a DALI ECG address."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_DALI_COLOUR, address=address)
    if resp.is_answer:
        return _parse_colour_bytes(resp.data)
    return None


async def query_dali_colour_features(tpi: ZenControlTPI, ecg_address: int) -> dict:
    """Query colour capability flags for a DALI ECG.

    Returns:
        dict with keys: supports_xy, supports_tunable, primary_count, rgbwaf_channels.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_DALI_COLOUR_FEATURES, address=ecg_address)
    if resp.is_answer and len(resp.data) == 1:
        f = resp.data[0]
        return {
            "supports_xy": bool(f & 0x01),
            "supports_tunable": bool(f & 0x02),
            "primary_count": (f & 0x1C) >> 2,
            "rgbwaf_channels": (f & 0xE0) >> 5,
        }
    # Device absent / no colour capability
    return {"supports_xy": False, "supports_tunable": False, "primary_count": 0, "rgbwaf_channels": 0}


async def query_dali_colour_temp_limits(tpi: ZenControlTPI, ecg_address: int) -> dict | None:
    """Query the colour temperature limits for a DALI ECG.

    Returns dict with keys: physical_warmest, physical_coolest, soft_warmest,
    soft_coolest, step_value (all in Kelvin), or None on failure.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_DALI_COLOUR_TEMP_LIMITS, address=ecg_address)
    if resp.is_answer and len(resp.data) == 10:
        values = struct.unpack(">HHHHH", resp.data)
        return {
            "physical_warmest": values[0],
            "physical_coolest": values[1],
            "soft_warmest": values[2],
            "soft_coolest": values[3],
            "step_value": values[4],
        }
    return None


async def set_dali_colour(
    tpi: ZenControlTPI,
    address: int,
    colour: DaliColourInfo,
    arc_level: int = 0xFF,
) -> bool:
    """Set a DALI address to a colour with an optional arc level.

    Args:
        address: DALI address byte (ECG 0–63, group 64–79, broadcast 127/255).
        colour: Colour to set.
        arc_level: Arc level 0–254, or 0xFF to skip arc level change.

    Returns:
        True if acknowledged.
    """
    colour_type_byte, colour_data = _colour_data_bytes(colour)
    resp = await tpi.send_dali_colour(
        address=address,
        arc_level=arc_level,
        colour_type=int(colour_type_byte),
        colour_data=colour_data,
    )
    return resp.is_ok


# ---------------------------------------------------------------------------
# Scene commands
# ---------------------------------------------------------------------------


async def query_scene_numbers_for_group(tpi: ZenControlTPI, group: int) -> list[int]:
    """Return sorted list of scene numbers (0–11) configured for a group.

    Response is 2 bytes: high byte = scenes 8–15, low byte = scenes 0–7.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_SCENE_NUMBERS_FOR_GROUP, address=group)
    if resp.is_answer:
        return _parse_2byte_bitmask_high_low(resp.data)
    return []


async def query_scene_label_for_group(tpi: ZenControlTPI, group: int, scene: int) -> str | None:
    """Query the label for a scene (0–11) and group combination."""
    resp = await tpi.send_basic(
        command=TpiCommand.QUERY_SCENE_LABEL_FOR_GROUP,
        address=group,
        data_lo=scene,
    )
    if resp.is_answer:
        return _decode_string(resp.data)
    return None


async def query_scene_numbers_by_address(tpi: ZenControlTPI, ecg_address: int) -> list[int]:
    """Return sorted list of scene numbers (0–11) for which an ECG has a level set."""
    resp = await tpi.send_basic(command=TpiCommand.QUERY_SCENE_NUMBERS_BY_ADDRESS, address=ecg_address)
    if resp.is_answer:
        return sorted(resp.data)
    return []


async def query_scene_levels_by_address(tpi: ZenControlTPI, ecg_address: int) -> list[int | None]:
    """Query all 16 scene levels for an ECG address.

    Returns a list of 16 entries; entries are None where no level is configured (0xFF).
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_SCENE_LEVELS_BY_ADDRESS, address=ecg_address)
    if resp.is_answer:
        return [None if b == 0xFF else b for b in resp.data]
    return [None] * 16


async def query_scene_by_number(tpi: ZenControlTPI, scene: int) -> dict | None:
    """Query scene metadata by scene number.

    Returns dict with keys: scene_number, or None on failure.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_SCENE_BY_NUMBER, address=scene)
    if resp.is_answer:
        return {"scene_number": scene, "data": resp.data}
    return None


# ---------------------------------------------------------------------------
# DALI control commands
# ---------------------------------------------------------------------------


async def dali_arc_level(tpi: ZenControlTPI, address: int, level: int) -> bool:
    """Send a direct arc level (0–254) to a DALI address."""
    if not 0 <= level <= 254:
        raise ValueError(f"Arc level must be 0–254, got {level}")
    resp = await tpi.send_basic(command=TpiCommand.DALI_ARC_LEVEL, address=address, data_lo=level)
    return resp.is_ok


async def dali_scene(tpi: ZenControlTPI, address: int, scene: int) -> bool:
    """Recall a scene (0–11) on a DALI address."""
    if not 0 <= scene < MAX_SCENE:
        raise ValueError(f"Scene must be 0–{MAX_SCENE - 1}, got {scene}")
    resp = await tpi.send_basic(command=TpiCommand.DALI_SCENE, address=address, data_lo=scene)
    return resp.is_ok


async def dali_recall_max(tpi: ZenControlTPI, address: int) -> bool:
    """Send RECALL MAX to a DALI address (instant, no fade)."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_RECALL_MAX, address=address)
    return resp.is_ok


async def dali_recall_min(tpi: ZenControlTPI, address: int) -> bool:
    """Send RECALL MIN to a DALI address (instant, no fade)."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_RECALL_MIN, address=address)
    return resp.is_ok


async def dali_off(tpi: ZenControlTPI, address: int) -> bool:
    """Send OFF to a DALI address (instant, no fade)."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_OFF, address=address)
    return resp.is_ok


async def dali_on_step_up(tpi: ZenControlTPI, address: int) -> bool:
    """Send ON AND STEP UP to a DALI address (no fade)."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_ON_STEP_UP, address=address)
    return resp.is_ok


async def dali_step_down_off(tpi: ZenControlTPI, address: int) -> bool:
    """Send STEP DOWN AND OFF to a DALI address (no fade)."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_STEP_DOWN_OFF, address=address)
    return resp.is_ok


async def dali_up(tpi: ZenControlTPI, address: int) -> bool:
    """Send DALI UP (fade up) to a DALI address."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_UP, address=address)
    return resp.is_ok


async def dali_down(tpi: ZenControlTPI, address: int) -> bool:
    """Send DALI DOWN (fade down) to a DALI address."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_DOWN, address=address)
    return resp.is_ok


async def dali_go_to_last_active_level(tpi: ZenControlTPI, address: int) -> bool:
    """Command a DALI address to go to its last active level."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_GO_TO_LAST_ACTIVE_LEVEL, address=address)
    return resp.is_ok


async def dali_custom_fade(tpi: ZenControlTPI, address: int, level: int, seconds: int) -> bool:
    """Fade a DALI address to a level over a custom duration.

    Args:
        address: DALI ECG or group address.
        level: Target level 0–254.
        seconds: Fade duration 0–65535 seconds.
    """
    if not 0 <= level <= 254:
        raise ValueError(f"Level must be 0–254, got {level}")
    if not 0 <= seconds <= 65535:
        raise ValueError(f"Fade time must be 0–65535 seconds, got {seconds}")
    seconds_hi = (seconds >> 8) & 0xFF
    seconds_lo = seconds & 0xFF
    resp = await tpi.send_basic(
        command=TpiCommand.DALI_CUSTOM_FADE,
        address=address,
        data_hi=level,
        data_mid=seconds_hi,
        data_lo=seconds_lo,
    )
    return resp.is_ok


async def dali_stop_fade(tpi: ZenControlTPI, address: int) -> bool:
    """Stop a running DALI fade immediately (does not jump to target level)."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_STOP_FADE, address=address)
    return resp.is_ok


async def dali_enable_dapc_sequence(tpi: ZenControlTPI, address: int) -> bool:
    """Begin a DALI DAPC sequence on an ECG address.

    DAPC overrides the fade rate for 250 ms, allowing immediate level changes.
    """
    resp = await tpi.send_basic(command=TpiCommand.DALI_ENABLE_DAPC_SEQ, address=address)
    return resp.is_ok or resp.is_answer


async def dali_inhibit(tpi: ZenControlTPI, address: int, seconds: int) -> bool:
    """Prevent sensors from changing a DALI address for a duration.

    Args:
        address: DALI ECG, group or broadcast address.
        seconds: Inhibit duration 0–65535.
    """
    if not 0 <= seconds <= 65535:
        raise ValueError(f"Inhibit time must be 0–65535 seconds, got {seconds}")
    time_hi = (seconds >> 8) & 0xFF
    time_lo = seconds & 0xFF
    resp = await tpi.send_basic(
        command=TpiCommand.DALI_INHIBIT,
        address=address,
        data_mid=time_hi,
        data_lo=time_lo,
    )
    return resp.is_ok


# ---------------------------------------------------------------------------
# DALI status queries
# ---------------------------------------------------------------------------


async def dali_query_level(tpi: ZenControlTPI, address: int) -> int | None:
    """Query the current arc level for a DALI ECG or group.

    Returns level 0–254, or None if there are mixed levels in a group.
    """
    resp = await tpi.send_basic(command=TpiCommand.DALI_QUERY_LEVEL, address=address)
    if resp.is_answer and resp.data:
        level = resp.data[0]
        return None if level == 255 else level
    return None


async def dali_query_control_gear_status(tpi: ZenControlTPI, address: int) -> dict | None:
    """Query status flags for a DALI ECG or group.

    Returns dict with boolean flags, or None on failure.
    """
    resp = await tpi.send_basic(command=TpiCommand.DALI_QUERY_CONTROL_GEAR_STATUS, address=address)
    if resp.is_answer and len(resp.data) == 1:
        b = resp.data[0]
        return {
            "cg_failure": bool(b & 0x01),
            "lamp_failure": bool(b & 0x02),
            "lamp_power_on": bool(b & 0x04),
            "limit_error": bool(b & 0x08),
            "fade_running": bool(b & 0x10),
            "reset": bool(b & 0x20),
            "missing_short_address": bool(b & 0x40),
            "power_failure": bool(b & 0x80),
        }
    return None


async def dali_query_last_scene(tpi: ZenControlTPI, address: int) -> int | None:
    """Query the last recalled scene number for a DALI address.

    Returns scene number 0–11, or None on failure.
    """
    resp = await tpi.send_basic(command=TpiCommand.DALI_QUERY_LAST_SCENE, address=address)
    if resp.is_answer and resp.data:
        return resp.data[0]
    return None


async def dali_query_last_scene_is_current(tpi: ZenControlTPI, address: int) -> bool | None:
    """Return True if the last recalled scene is still the active state."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_QUERY_LAST_SCENE_IS_CURRENT, address=address)
    if resp.is_answer and resp.data:
        return bool(resp.data[0])
    if resp.is_ok:
        return True
    if resp.is_no_answer:
        return False
    return None


async def dali_query_min_level(tpi: ZenControlTPI, ecg_address: int) -> int | None:
    """Query the minimum configured arc level for a DALI ECG."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_QUERY_MIN_LEVEL, address=ecg_address)
    if resp.is_answer and resp.data:
        return resp.data[0]
    return None


async def dali_query_max_level(tpi: ZenControlTPI, ecg_address: int) -> int | None:
    """Query the maximum configured arc level for a DALI ECG."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_QUERY_MAX_LEVEL, address=ecg_address)
    if resp.is_answer and resp.data:
        return resp.data[0]
    return None


async def dali_query_fade_running(tpi: ZenControlTPI, ecg_address: int) -> bool | None:
    """Return True if a fade is currently running on a DALI ECG."""
    resp = await tpi.send_basic(command=TpiCommand.DALI_QUERY_FADE_RUNNING, address=ecg_address)
    if resp.is_ok:
        return True
    if resp.is_no_answer:
        return False
    if resp.is_answer and resp.data:
        return bool(resp.data[0])
    return None


# ---------------------------------------------------------------------------
# DMX colour command
# ---------------------------------------------------------------------------


async def set_dmx_colour(
    tpi: ZenControlTPI,
    fade_id: int,
    universe_mask: int,
    start_channel: int,
    stop_channel: int,
    levels: list[int],
    *,
    address_divisor: int = 1,
    block_mode: int = 0x00,
    personality_type: int = 0x00,
    fade_mode: int = 0x00,
    fade_time_ms: int = 0,
    fade_type_a: int = 0x01,
    fade_type_b: int = 0x00,
) -> bool:
    """Send a DMX Colour frame.

    Args:
        fade_id: Fade ID for cancellation/overwriting.
        universe_mask: 16-bit universe mask (0x0001 for universe 1).
        start_channel: Start DMX channel (1-indexed).
        stop_channel: Stop DMX channel (1-indexed).
        levels: Level bytes (max 16).
        address_divisor: Channel skip factor (1 = every channel).
        block_mode: 0=INTERSECTION, 1=DIFFERENCE.
        personality_type: 0=8-bit dimming.
        fade_mode: 0=fade time mode.
        fade_time_ms: Fade time in milliseconds.
        fade_type_a: 1=linear.
        fade_type_b: 0=no combined fade.

    Returns:
        True if acknowledged.
    """
    resp = await tpi.send_dmx_colour(
        fade_id=fade_id,
        universe_mask=universe_mask,
        start_channel=start_channel,
        stop_channel=stop_channel,
        address_divisor=address_divisor,
        block_mode=block_mode,
        personality_type=personality_type,
        fade_mode=fade_mode,
        fade_time_ms=fade_time_ms,
        fade_type_a=fade_type_a,
        fade_type_b=fade_type_b,
        levels=levels,
    )
    return resp.is_ok


# ---------------------------------------------------------------------------
# Profile commands
# ---------------------------------------------------------------------------


async def query_profile_numbers(tpi: ZenControlTPI) -> list[int]:
    """Return sorted list of configured profile numbers.

    Profile numbers are 2 bytes each in the response payload.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_PROFILE_NUMBERS, address=0)
    if resp.is_answer and len(resp.data) >= 2:
        numbers = []
        for i in range(0, len(resp.data) - 1, 2):
            number = (resp.data[i] << 8) | resp.data[i + 1]
            numbers.append(number)
        return sorted(numbers)
    return []


async def query_profile_label(tpi: ZenControlTPI, profile: int) -> str | None:
    """Query the label for a profile number (0–65534)."""
    hi = (profile >> 8) & 0xFF
    lo = profile & 0xFF
    resp = await tpi.send_basic(command=TpiCommand.QUERY_PROFILE_LABEL, address=0, data_mid=hi, data_lo=lo)
    if resp.is_answer:
        return _decode_string(resp.data)
    return None


async def query_current_profile_number(tpi: ZenControlTPI) -> int | None:
    """Query the currently active profile number.

    Returns profile number (0–65534), or None on failure.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_CURRENT_PROFILE_NUMBER, address=0)
    if resp.is_answer and len(resp.data) >= 2:
        return (resp.data[0] << 8) | resp.data[1]
    if resp.is_answer and len(resp.data) == 1:
        return resp.data[0]
    return None


async def query_profile_information(tpi: ZenControlTPI) -> dict | None:
    """Query full profile state and list from the controller.

    Returns:
        dict with keys:
            state: current_active_profile, last_scheduled_profile,
                   last_overridden_utc, last_scheduled_utc
            profiles: dict mapping profile_number → {enabled, priority, priority_label}
        or None on failure.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_PROFILE_INFORMATION, address=0)
    if resp.is_answer and len(resp.data) >= 12:
        unpacked = struct.unpack(">HHII", resp.data[0:12])
        state = {
            "current_active_profile": unpacked[0],
            "last_scheduled_profile": unpacked[1],
            "last_overridden_utc": datetime.fromtimestamp(unpacked[2]).isoformat() if unpacked[2] else None,
            "last_scheduled_utc": datetime.fromtimestamp(unpacked[3]).isoformat() if unpacked[3] else None,
        }
        profiles: dict[int, dict] = {}
        for i in range(12, len(resp.data) - 2, 3):
            profile_number = struct.unpack(">H", resp.data[i : i + 2])[0]
            behaviour = resp.data[i + 2]
            enabled = not bool(behaviour & 0x01)
            priority = (behaviour >> 1) & 0x03
            priority_label = ["Scheduled", "Medium", "High", "Emergency"][priority]
            profiles[profile_number] = {
                "enabled": enabled,
                "priority": priority,
                "priority_label": priority_label,
            }
        return {"state": state, "profiles": profiles}
    return None


async def change_profile_number(tpi: ZenControlTPI, profile: int) -> bool:
    """Activate a profile by number.

    Args:
        profile: Profile number 0–65534, or 65535 (PROFILE_SCHEDULED) to return
                 to the scheduled profile.

    Returns:
        True if acknowledged.
    """
    if not 0 <= profile <= PROFILE_SCHEDULED:
        raise ValueError(f"Profile number must be 0–{PROFILE_SCHEDULED}, got {profile}")
    hi = (profile >> 8) & 0xFF
    lo = profile & 0xFF
    resp = await tpi.send_basic(
        command=TpiCommand.CHANGE_PROFILE_NUMBER,
        address=0,
        data_mid=hi,
        data_lo=lo,
    )
    return resp.is_ok


# ---------------------------------------------------------------------------
# Instance commands
# ---------------------------------------------------------------------------


async def query_dali_addresses_with_instances(
    tpi: ZenControlTPI,
    start_address: int = 0,
) -> list[int]:
    """Query for ECD addresses that have instances.

    Returns ECD short addresses 0–63 (not DALI-offset addresses).
    Due to payload limits, call twice: start_address=0 and start_address=60.
    """
    resp = await tpi.send_basic(
        command=TpiCommand.QUERY_DALI_ADDRESSES_WITH_INSTANCES,
        address=0,
        data_lo=start_address,
    )
    if resp.is_answer:
        return [n - 64 for n in sorted(resp.data) if 64 <= n <= 127]
    return []


async def query_instances_by_address(tpi: ZenControlTPI, ecd_address: int) -> list[dict]:
    """Query instances associated with a DALI ECD address.

    Returns list of dicts with keys: number, type, active, error.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_INSTANCES_BY_ADDRESS, address=_ecd_wire(ecd_address))
    if resp.is_answer and len(resp.data) >= 4:
        instances = []
        for i in range(0, len(resp.data) - 3, 4):
            try:
                inst_type = InstanceType(resp.data[i + 1])
            except ValueError:
                inst_type = None
            instances.append(
                {
                    "number": resp.data[i],
                    "type": inst_type,
                    "active": bool(resp.data[i + 2] & 0x02),
                    "error": bool(resp.data[i + 2] & 0x01),
                }
            )
        return instances
    return []


async def query_dali_instance_label(
    tpi: ZenControlTPI,
    ecd_address: int,
    instance_number: int,
) -> str | None:
    """Query the label for a DALI ECD instance."""
    resp = await tpi.send_basic(
        command=TpiCommand.QUERY_DALI_INSTANCE_LABEL,
        address=_ecd_wire(ecd_address),
        data_lo=instance_number,
    )
    if resp.is_answer:
        return _decode_string(resp.data)
    return None


async def query_dali_instance_fitting_number(
    tpi: ZenControlTPI,
    ecd_address: int,
    instance_number: int,
) -> str | None:
    """Query the fitting number for a DALI ECD instance."""
    resp = await tpi.send_basic(
        command=TpiCommand.QUERY_DALI_INSTANCE_FITTING_NUMBER,
        address=_ecd_wire(ecd_address),
        data_lo=instance_number,
    )
    if resp.is_answer:
        return _decode_string(resp.data)
    return None


async def query_instance_groups(
    tpi: ZenControlTPI,
    ecd_address: int,
    instance_number: int,
) -> tuple[int | None, int | None, int | None]:
    """Query group targets for a DALI ECD instance.

    Returns tuple of (primary_group, first_group, second_group).
    Group 255 indicates "not configured" (returned as None).
    """
    resp = await tpi.send_basic(
        command=TpiCommand.QUERY_INSTANCE_GROUPS,
        address=_ecd_wire(ecd_address),
        data_lo=instance_number,
    )
    if resp.is_answer and len(resp.data) == 3:
        return (
            resp.data[0] if resp.data[0] != 0xFF else None,
            resp.data[1] if resp.data[1] != 0xFF else None,
            resp.data[2] if resp.data[2] != 0xFF else None,
        )
    return (None, None, None)


async def query_occupancy_instance_timers(
    tpi: ZenControlTPI,
    ecd_address: int,
    instance_number: int,
) -> dict | None:
    """Query occupancy sensor timer values for a DALI ECD instance.

    Returns dict with keys: deadtime, hold, report (seconds), last_detect (seconds
    since last occupied event), or None on failure.
    """
    resp = await tpi.send_basic(
        command=TpiCommand.QUERY_OCCUPANCY_INSTANCE_TIMERS,
        address=_ecd_wire(ecd_address),
        data_lo=instance_number,
    )
    if resp.is_answer and len(resp.data) >= 5:
        return {
            "deadtime": resp.data[0],
            "hold": resp.data[1],
            "report": resp.data[2],
            "last_detect": (resp.data[3] << 8) | resp.data[4],
        }
    return None


async def query_virtual_instances(tpi: ZenControlTPI) -> list[dict]:
    """Query all virtual instances on the controller.

    Returns list of dicts with keys: number, type.
    """
    resp = await tpi.send_basic(command=TpiCommand.QUERY_VIRTUAL_INSTANCES, address=0)
    if resp.is_answer:
        instances = []
        for i in range(0, len(resp.data) - 1, 2):
            try:
                inst_type = InstanceType(resp.data[i + 1])
            except ValueError:
                inst_type = None
            instances.append({"number": resp.data[i], "type": inst_type})
        return instances
    return []


async def trigger_virtual_instance(tpi: ZenControlTPI, instance_number: int) -> bool:
    """Trigger a virtual instance.

    Returns True if acknowledged.
    """
    resp = await tpi.send_basic(command=TpiCommand.VIRTUAL_INSTANCE, address=instance_number)
    return resp.is_ok


# ---------------------------------------------------------------------------
# System variable commands
# ---------------------------------------------------------------------------


async def query_system_variable(tpi: ZenControlTPI, variable: int) -> int | None:
    """Query the value of a system variable (0–147).

    Returns a signed 16-bit integer, or None if the variable is unset.
    """
    if not 0 <= variable < MAX_SYSVAR:
        raise ValueError(f"Variable must be 0–{MAX_SYSVAR - 1}, got {variable}")
    resp = await tpi.send_basic(command=TpiCommand.QUERY_SYSTEM_VARIABLE, address=variable)
    if resp.is_answer and len(resp.data) == 2:
        return int.from_bytes(resp.data, byteorder="big", signed=True)
    return None


async def query_system_variable_name(tpi: ZenControlTPI, variable: int) -> str | None:
    """Query the name of a system variable (0–147)."""
    if not 0 <= variable < MAX_SYSVAR:
        raise ValueError(f"Variable must be 0–{MAX_SYSVAR - 1}, got {variable}")
    resp = await tpi.send_basic(command=TpiCommand.QUERY_SYSTEM_VARIABLE_NAME, address=variable)
    if resp.is_answer:
        return _decode_string(resp.data)
    return None


async def set_system_variable(tpi: ZenControlTPI, variable: int, value: int) -> bool:
    """Set a system variable (0–147) to a signed 16-bit value (-32768–32767).

    Returns True if acknowledged.
    """
    if not 0 <= variable < MAX_SYSVAR:
        raise ValueError(f"Variable must be 0–{MAX_SYSVAR - 1}, got {variable}")
    if not -32768 <= value <= 32767:
        raise ValueError(f"Value must be -32768–32767, got {value}")
    value_bytes = value.to_bytes(2, byteorder="big", signed=True)
    resp = await tpi.send_basic(
        command=TpiCommand.SET_SYSTEM_VARIABLE,
        address=variable,
        data_mid=value_bytes[0],
        data_lo=value_bytes[1],
    )
    return resp.is_ok


# ---------------------------------------------------------------------------
# Button LED commands
# ---------------------------------------------------------------------------


async def override_dali_button_led_state(
    tpi: ZenControlTPI,
    ecd_address: int,
    instance_number: int,
    led_on: bool,
) -> bool:
    """Override the LED state of a DALI push button instance.

    Args:
        ecd_address: DALI ECD short address (0–63).
        instance_number: Instance number.
        led_on: True to turn LED on, False to turn off.

    Returns:
        True if acknowledged.
    """
    state_byte = 0x02 if led_on else 0x01
    resp = await tpi.send_basic(
        command=TpiCommand.OVERRIDE_DALI_BUTTON_LED_STATE,
        address=_ecd_wire(ecd_address),
        data_mid=state_byte,
        data_lo=instance_number,
    )
    return resp.is_ok


async def query_last_known_dali_button_led_state(
    tpi: ZenControlTPI,
    ecd_address: int,
    instance_number: int,
) -> bool | None:
    """Query the last known LED state for a DALI push button instance.

    Returns True (on), False (off), or None if unknown/failed.
    Note: This reflects the controller's last known state, which may differ
    from the physical LED state when the device manages its own LEDs.
    """
    resp = await tpi.send_basic(
        command=TpiCommand.QUERY_LAST_KNOWN_DALI_BUTTON_LED_STATE,
        address=_ecd_wire(ecd_address),
        data_lo=instance_number,
    )
    if resp.is_answer and len(resp.data) == 1:
        if resp.data[0] == 0x01:
            return False
        if resp.data[0] == 0x02:
            return True
    return None
