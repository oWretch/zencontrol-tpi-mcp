"""Binary framing helpers for the ZenControl TPI Advanced protocol.

TPI Advanced uses binary packed bytes with a CRC8 (XOR) checksum.
All request frames start with control byte 0x04 (TPI Advanced marker).

Frame types:
- Basic (8 bytes): control | seq | cmd | addr | data_hi | data_mid | data_lo | checksum
- DALI Colour (variable): control | seq | 0x0E | addr | arc_level | colour_type | data... | checksum
- DMX Colour (variable): control | seq | 0x10 | fade_id | ... | data... | checksum
- Dynamic Subframe (variable): control | seq | cmd | data_length | data... | checksum

All responses use:
  response_type | seq | data_length | data[0..n] | checksum
"""

from __future__ import annotations

import struct

# Control byte for all TPI Advanced requests
TPI_CONTROL = 0x04

# Response type codes
RESPONSE_OK = 0xA0
RESPONSE_ANSWER = 0xA1
RESPONSE_NO_ANSWER = 0xA2
RESPONSE_ERROR = 0xA3


class FrameError(Exception):
    """Raised when a response frame fails validation."""


def crc8(data: bytes) -> int:
    """Calculate CRC8 checksum by XOR-ing all bytes."""
    acc = 0
    for b in data:
        acc ^= b
    return acc


def validate_checksum(frame: bytes) -> None:
    """Raise FrameError if the frame checksum is invalid.

    The checksum is the last byte; XOR-ing all bytes including the checksum
    must produce 0.
    """
    if not frame:
        raise FrameError("Empty frame")
    if crc8(frame) != 0:
        raise FrameError(f"Checksum mismatch in frame: {frame.hex()}")


def build_basic_frame(
    seq: int,
    command: int,
    address: int,
    data_hi: int = 0x00,
    data_mid: int = 0x00,
    data_lo: int = 0x00,
) -> bytes:
    """Build an 8-byte TPI Advanced basic request frame.

    Args:
        seq: Sequence counter (0–255).
        command: Command byte.
        address: DALI address byte (see DALI addressing scheme in protocol docs).
        data_hi: High data byte (default 0x00).
        data_mid: Mid data byte (default 0x00).
        data_lo: Low data byte (default 0x00).

    Returns:
        8-byte frame including checksum.
    """
    body = bytes([TPI_CONTROL, seq, command, address, data_hi, data_mid, data_lo])
    return body + bytes([crc8(body)])


def build_dali_colour_frame(
    seq: int,
    address: int,
    arc_level: int,
    colour_type: int,
    colour_data: bytes,
) -> bytes:
    """Build a TPI Advanced DALI Colour request frame.

    Args:
        seq: Sequence counter (0–255).
        address: DALI address byte.
        arc_level: Arc level (0–254). Use 0xFF to do colour-only fade.
        colour_type: Colour type byte (0x10=XY, 0x20=Tc, 0x80=RGBWAF).
        colour_data: Colour channel bytes (7 bytes; pad unused with 0xFF).

    Returns:
        Variable-length frame including checksum.
    """
    DALI_COLOUR_CMD = 0x0E
    body = bytes([TPI_CONTROL, seq, DALI_COLOUR_CMD, address, arc_level, colour_type]) + colour_data
    return body + bytes([crc8(body)])


def build_dmx_colour_frame(
    seq: int,
    fade_id: int,
    universe_mask: int,
    start_channel: int,
    stop_channel: int,
    address_divisor: int,
    block_mode: int,
    personality_type: int,
    fade_mode: int,
    fade_time_ms: int,
    fade_type_a: int,
    fade_type_b: int,
    levels: list[int],
) -> bytes:
    """Build a TPI Advanced DMX Colour request frame.

    Args:
        seq: Sequence counter (0–255).
        fade_id: Fade ID for cancellation/overwriting.
        universe_mask: 16-bit universe mask (use 0xFFFF for all, or 0x0001).
        start_channel: Start DMX channel (1-indexed, 2 bytes).
        stop_channel: Stop DMX channel (1-indexed, 2 bytes).
        address_divisor: Channel skip divisor (1 = every channel).
        block_mode: Block mode (0x00=INTERSECTION, 0x01=DIFFERENCE).
        personality_type: 0x00=8bit dimming.
        fade_mode: 0x00=fade time mode.
        fade_time_ms: Fade time in milliseconds (up to 24-bit).
        fade_type_a: 0x01=linear fade.
        fade_type_b: 0x00=no combined fade.
        levels: List of level bytes (max 16).

    Returns:
        Variable-length frame including checksum.
    """
    DMX_COLOUR_CMD = 0x10
    if len(levels) > 16:
        raise ValueError(f"DMX levels list must be at most 16 entries, got {len(levels)}")

    # Fade data: mode (1) + time hi/mid/lo (3)
    fade_hi = (fade_time_ms >> 16) & 0xFF
    fade_mid = (fade_time_ms >> 8) & 0xFF
    fade_lo = fade_time_ms & 0xFF

    body = bytes([TPI_CONTROL, seq, DMX_COLOUR_CMD, fade_id])
    body += struct.pack(">H", universe_mask)
    body += struct.pack(">H", start_channel)
    body += struct.pack(">H", stop_channel)
    body += bytes([address_divisor, block_mode, personality_type])
    body += bytes([fade_mode, fade_hi, fade_mid, fade_lo])
    body += bytes([fade_type_a, fade_type_b])
    body += bytes([len(levels)])
    body += bytes(levels)
    return body + bytes([crc8(body)])


def build_dynamic_frame(
    seq: int,
    command: int,
    data: bytes,
) -> bytes:
    """Build a TPI Advanced dynamic subframe.

    Args:
        seq: Sequence counter (0–255).
        command: Command byte.
        data: Variable-length data bytes.

    Returns:
        Variable-length frame including checksum.
    """
    body = bytes([TPI_CONTROL, seq, command, len(data)]) + data
    return body + bytes([crc8(body)])


class TPIResponse:
    """Parsed TPI Advanced response frame.

    Attributes:
        response_type: One of RESPONSE_OK, RESPONSE_ANSWER, RESPONSE_NO_ANSWER, RESPONSE_ERROR.
        seq: Sequence counter byte from the response.
        data: Response payload bytes (may be empty).
    """

    __slots__ = ("response_type", "seq", "data")

    def __init__(self, response_type: int, seq: int, data: bytes) -> None:
        self.response_type = response_type
        self.seq = seq
        self.data = data

    @property
    def is_ok(self) -> bool:
        return self.response_type == RESPONSE_OK

    @property
    def is_answer(self) -> bool:
        return self.response_type == RESPONSE_ANSWER

    @property
    def is_no_answer(self) -> bool:
        return self.response_type == RESPONSE_NO_ANSWER

    @property
    def is_error(self) -> bool:
        return self.response_type == RESPONSE_ERROR

    @property
    def error_code(self) -> int | None:
        """Return the error code byte if this is an error response with data."""
        if self.is_error and self.data:
            return self.data[0]
        return None

    def __repr__(self) -> str:
        type_name = {
            RESPONSE_OK: "OK",
            RESPONSE_ANSWER: "ANSWER",
            RESPONSE_NO_ANSWER: "NO_ANSWER",
            RESPONSE_ERROR: "ERROR",
        }.get(self.response_type, f"0x{self.response_type:02X}")
        return f"TPIResponse({type_name}, seq={self.seq}, data={self.data.hex() or '(empty)'})"


def parse_response_header(header: bytes) -> tuple[int, int, int]:
    """Parse the 3-byte response header.

    Args:
        header: Exactly 3 bytes: response_type | seq | data_length.

    Returns:
        Tuple of (response_type, seq, data_length).

    Raises:
        FrameError: If header is not exactly 3 bytes.
    """
    if len(header) != 3:
        raise FrameError(f"Response header must be 3 bytes, got {len(header)}")
    return header[0], header[1], header[2]


def parse_response_body(header: bytes, body: bytes) -> TPIResponse:
    """Validate and parse a complete response frame.

    Args:
        header: 3-byte header (response_type | seq | data_length).
        body: data_length bytes of data + 1 checksum byte.

    Returns:
        Parsed TPIResponse.

    Raises:
        FrameError: If checksum fails or lengths don't match.
    """
    response_type, seq, data_length = parse_response_header(header)
    expected_body_len = data_length + 1  # data + checksum
    if len(body) != expected_body_len:
        raise FrameError(
            f"Response body length mismatch: expected {expected_body_len}, got {len(body)}"
        )
    full_frame = header + body
    validate_checksum(full_frame)
    data = body[:data_length]
    return TPIResponse(response_type=response_type, seq=seq, data=data)
