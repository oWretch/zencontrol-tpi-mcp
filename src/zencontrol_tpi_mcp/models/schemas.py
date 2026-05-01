"""Pydantic models and enumerations for the ZenControl TPI Advanced protocol."""

from __future__ import annotations

from enum import IntEnum

from pydantic import BaseModel, ConfigDict

# ---------------------------------------------------------------------------
# Command byte enumerations
# ---------------------------------------------------------------------------


class TpiCommand(IntEnum):
    """TPI Advanced command bytes (Basic frame type unless noted)."""

    QUERY_GROUP_LABEL = 0x01
    QUERY_SCENE_LABEL = 0x02
    QUERY_DALI_DEVICE_LABEL = 0x03
    QUERY_PROFILE_LABEL = 0x04
    QUERY_CURRENT_PROFILE_NUMBER = 0x05
    TRIGGER_SDDP_IDENTIFY = 0x06
    QUERY_TPI_EVENT_EMIT_STATE = 0x07
    ENABLE_TPI_EVENT_EMIT = 0x08
    QUERY_GROUP_NUMBERS = 0x09
    QUERY_SCENE_NUMBERS = 0x0A
    QUERY_PROFILE_NUMBERS = 0x0B
    QUERY_OCCUPANCY_INSTANCE_TIMERS = 0x0C
    QUERY_INSTANCES_BY_ADDRESS = 0x0D
    DALI_COLOUR = 0x0E  # DALI Colour frame type
    DMX_COLOUR = 0x10  # DMX Colour frame type
    QUERY_GROUP_BY_NUMBER = 0x12
    QUERY_SCENE_BY_NUMBER = 0x13
    QUERY_SCENE_NUMBERS_BY_ADDRESS = 0x14
    QUERY_GROUP_MEMBERSHIP_BY_ADDRESS = 0x15
    QUERY_DALI_ADDRESSES_WITH_INSTANCES = 0x16
    QUERY_DMX_DEVICE_NUMBERS = 0x17
    QUERY_DMX_DEVICE_BY_NUMBER = 0x18
    QUERY_DMX_LEVEL_BY_CHANNEL = 0x19
    QUERY_SCENE_NUMBERS_FOR_GROUP = 0x1A
    QUERY_SCENE_LABEL_FOR_GROUP = 0x1B
    QUERY_CONTROLLER_VERSION_NUMBER = 0x1C
    QUERY_CONTROL_GEAR_DALI_ADDRESSES = 0x1D
    QUERY_SCENE_LEVELS_BY_ADDRESS = 0x1E
    QUERY_DMX_DEVICE_LABEL_BY_NUMBER = 0x20
    QUERY_INSTANCE_GROUPS = 0x21
    QUERY_DALI_FITTING_NUMBER = 0x22
    QUERY_DALI_INSTANCE_FITTING_NUMBER = 0x23
    QUERY_CONTROLLER_LABEL = 0x24
    QUERY_CONTROLLER_FITTING_NUMBER = 0x25
    QUERY_IS_DALI_READY = 0x26
    QUERY_CONTROLLER_STARTUP_COMPLETE = 0x27
    QUERY_OPERATING_MODE_BY_ADDRESS = 0x28
    OVERRIDE_DALI_BUTTON_LED_STATE = 0x29
    QUERY_LAST_KNOWN_DALI_BUTTON_LED_STATE = 0x30
    DALI_ADD_TPI_EVENT_FILTER = 0x31
    QUERY_DALI_TPI_EVENT_FILTERS = 0x32
    DALI_CLEAR_TPI_EVENT_FILTERS = 0x33
    QUERY_DALI_COLOUR = 0x34
    QUERY_DALI_COLOUR_FEATURES = 0x35
    SET_SYSTEM_VARIABLE = 0x36
    QUERY_SYSTEM_VARIABLE = 0x37
    QUERY_DALI_COLOUR_TEMP_LIMITS = 0x38
    SET_TPI_EVENT_UNICAST_ADDRESS = 0x40
    QUERY_TPI_EVENT_UNICAST_ADDRESS = 0x41
    QUERY_SYSTEM_VARIABLE_NAME = 0x42
    QUERY_PROFILE_INFORMATION = 0x43
    QUERY_COLOUR_SCENE_MEMBERSHIP_BY_ADDR = 0x44
    QUERY_COLOUR_SCENE_0_7_DATA_FOR_ADDR = 0x45
    QUERY_COLOUR_SCENE_8_11_DATA_FOR_ADDR = 0x46
    DALI_INHIBIT = 0xA0
    DALI_SCENE = 0xA1
    DALI_ARC_LEVEL = 0xA2
    DALI_ON_STEP_UP = 0xA3
    DALI_STEP_DOWN_OFF = 0xA4
    DALI_UP = 0xA5
    DALI_DOWN = 0xA6
    DALI_RECALL_MAX = 0xA7
    DALI_RECALL_MIN = 0xA8
    DALI_OFF = 0xA9
    DALI_QUERY_LEVEL = 0xAA
    DALI_QUERY_CONTROL_GEAR_STATUS = 0xAB
    DALI_QUERY_CG_TYPE = 0xAC
    DALI_QUERY_LAST_SCENE = 0xAD
    DALI_QUERY_LAST_SCENE_IS_CURRENT = 0xAE
    DALI_QUERY_MIN_LEVEL = 0xAF
    DALI_QUERY_MAX_LEVEL = 0xB0
    DALI_QUERY_FADE_RUNNING = 0xB1
    DALI_ENABLE_DAPC_SEQ = 0xB2
    VIRTUAL_INSTANCE = 0xB3
    DALI_CUSTOM_FADE = 0xB4
    DALI_GO_TO_LAST_ACTIVE_LEVEL = 0xB5
    QUERY_VIRTUAL_INSTANCES = 0xB6
    QUERY_DALI_INSTANCE_LABEL = 0xB7
    QUERY_DALI_EAN = 0xB8
    QUERY_DALI_SERIAL = 0xB9
    CHANGE_PROFILE_NUMBER = 0xC0
    DALI_STOP_FADE = 0xC1


# ---------------------------------------------------------------------------
# Protocol constant enumerations
# ---------------------------------------------------------------------------


class DaliColourType(IntEnum):
    """DALI colour type bytes."""

    XY = 0x10
    TC = 0x20
    RGBWAF = 0x80


class DaliAddress(IntEnum):
    """Special DALI address values."""

    BROADCAST_CLASSIC = 127
    BROADCAST = 255

    @staticmethod
    def for_group(group: int) -> int:
        """Return the DALI address byte for a group number (0–15)."""
        if not 0 <= group <= 15:
            raise ValueError(f"DALI group must be 0–15, got {group}")
        return 64 + group

    @staticmethod
    def from_group_address(address: int) -> int:
        """Return the group number (0–15) from a DALI group address (64–79)."""
        if not 64 <= address <= 79:
            raise ValueError(f"Not a DALI group address: {address}")
        return address - 64


class InstanceType(IntEnum):
    """DALI instance types."""

    PUSH_BUTTON = 0x01
    ABSOLUTE_INPUT = 0x02
    OCCUPANCY_SENSOR = 0x03
    LIGHT_SENSOR = 0x04
    GENERAL_PURPOSE_SENSOR = 0x06


class InstanceState(IntEnum):
    """Instance binary states."""

    UNKNOWN = 0x00
    LO = 0x01
    HI = 0x02


class ErrorCode(IntEnum):
    """TPI Advanced error codes."""

    ERROR_CHECKSUM = 0x01
    ERROR_SHORT_CIRCUIT = 0x02
    ERROR_RECEIVE_ERROR = 0x03
    ERROR_UNKNOWN_CMD = 0x04
    ERROR_PAID_FEATURE = 0xB0
    ERROR_INVALID_ARGS = 0xB1
    ERROR_CMD_REFUSED = 0xB2
    ERROR_QUEUE_FAILURE = 0xB3
    ERROR_RESPONSE_UNAVAIL = 0xB4
    ERROR_OTHER_DALI_ERROR = 0xB5
    ERROR_MAX_LIMIT = 0xB6
    ERROR_UNEXPECTED_RESULT = 0xB7
    ERROR_UNKNOWN_TARGET = 0xB8

    @classmethod
    def describe(cls, code: int) -> str:
        try:
            member = cls(code)
            return member.name.replace("_", " ").title()
        except ValueError:
            return f"Unknown error 0x{code:02X}"


class DaliStatusMask(IntEnum):
    """DALI status bitmasks from DALI_QUERY_CONTROL_GEAR_STATUS."""

    CG_FAILURE = 0x01
    LAMP_FAILURE = 0x02
    LAMP_POWER_ON = 0x04
    LIMIT_ERROR = 0x08
    FADE_RUNNING = 0x10
    RESET = 0x20
    MISSING_SHORT_ADDRESS = 0x40
    POWER_FAILURE = 0x80


class DaliHardwareType(IntEnum):
    """DALI control gear type bitmasks from DALI_QUERY_CG_TYPE."""

    FLUORESCENT = 0x01
    EMERGENCY = 0x02
    DISCHARGE = 0x04
    HALOGEN = 0x08
    INCANDESCENT = 0x10
    DC = 0x20
    LED = 0x40
    RELAY = 0x80
    COLOUR_CONTROL = 0x100
    THERMAL_GEAR_PROTECTION = 0x10000
    DIMMING_CURVE_SELECTION = 0x20000


class DmxBlockMode(IntEnum):
    """DMX block mode values."""

    INTERSECTION = 0x00
    DIFFERENCE = 0x01


class DmxPersonalityType(IntEnum):
    """DMX personality/channel type values."""

    DIM_8BIT = 0x00
    DIM_16BIT_BE = 0x01
    DIM_16BIT_LE = 0x02


# ---------------------------------------------------------------------------
# Domain data models
# ---------------------------------------------------------------------------


class DaliGroup(BaseModel):
    """A DALI group."""

    model_config = ConfigDict(populate_by_name=True)

    number: int
    label: str | None = None
    member_addresses: list[int] = []


class DaliScene(BaseModel):
    """A DALI scene."""

    model_config = ConfigDict(populate_by_name=True)

    number: int
    label: str | None = None
    group_number: int | None = None
    levels: dict[int, int] = {}  # address -> level (0-254, 255=mask)


class DaliDevice(BaseModel):
    """A DALI control gear (ECG)."""

    model_config = ConfigDict(populate_by_name=True)

    address: int
    label: str | None = None
    fitting_number: int | None = None
    ean: bytes | None = None
    serial: bytes | None = None
    hardware_type: int = 0
    groups: list[int] = []


class DmxDevice(BaseModel):
    """A DMX device."""

    model_config = ConfigDict(populate_by_name=True)

    number: int
    label: str | None = None
    start_channel: int | None = None
    stop_channel: int | None = None


class ControllerInfo(BaseModel):
    """ZenControl controller information."""

    model_config = ConfigDict(populate_by_name=True)

    label: str | None = None
    version: str | None = None
    fitting_number: int | None = None
    startup_complete: bool = False
    dali_ready: bool = False


class DaliColourInfo(BaseModel):
    """Current colour state of a DALI device."""

    model_config = ConfigDict(populate_by_name=True)

    colour_type: DaliColourType | None = None
    # XY colour
    x: int | None = None
    y: int | None = None
    # Tc colour (Kelvin)
    tc_kelvin: int | None = None
    # RGBWAF
    red: int | None = None
    green: int | None = None
    blue: int | None = None
    white: int | None = None
    amber: int | None = None
    free: int | None = None


class DaliInstance(BaseModel):
    """A DALI input instance associated with a device address."""

    model_config = ConfigDict(populate_by_name=True)

    address: int
    instance_number: int
    instance_type: InstanceType | None = None
    label: str | None = None
    fitting_number: int | None = None
    groups: list[int] = []


class VirtualInstance(BaseModel):
    """A ZenControl virtual instance."""

    model_config = ConfigDict(populate_by_name=True)

    number: int
    instance_type: InstanceType | None = None


class OccupancyTimers(BaseModel):
    """Occupancy sensor instance timer values."""

    model_config = ConfigDict(populate_by_name=True)

    instance_number: int
    deadtime_seconds: int | None = None
    hold_seconds: int | None = None
    report_seconds: int | None = None


class ProfileInfo(BaseModel):
    """A ZenControl controller profile."""

    model_config = ConfigDict(populate_by_name=True)

    number: int
    label: str | None = None
    behaviour: int | None = None


class SystemVariable(BaseModel):
    """A ZenControl system variable."""

    model_config = ConfigDict(populate_by_name=True)

    index: int
    name: str | None = None
    value: int | None = None
