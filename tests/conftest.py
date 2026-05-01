"""Shared test fixtures for ZenControl TPI MCP tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from zencontrol_tpi_mcp.api.client import ZenControlTPI
from zencontrol_tpi_mcp.api.framing import (
    RESPONSE_ANSWER,
    RESPONSE_ERROR,
    RESPONSE_NO_ANSWER,
    RESPONSE_OK,
    TPIResponse,
)
from zencontrol_tpi_mcp.scope import ScopeConstraint


def make_ok(seq: int = 1) -> TPIResponse:
    """Return a RESPONSE_OK TPIResponse with no data."""
    return TPIResponse(response_type=RESPONSE_OK, seq=seq, data=b"")


def make_answer(data: bytes, seq: int = 1) -> TPIResponse:
    """Return a RESPONSE_ANSWER TPIResponse with the given data."""
    return TPIResponse(response_type=RESPONSE_ANSWER, seq=seq, data=data)


def make_no_answer(seq: int = 1) -> TPIResponse:
    """Return a RESPONSE_NO_ANSWER TPIResponse."""
    return TPIResponse(response_type=RESPONSE_NO_ANSWER, seq=seq, data=b"")


def make_error(code: int = 0xB1, seq: int = 1) -> TPIResponse:
    """Return a RESPONSE_ERROR TPIResponse with the given error code."""
    return TPIResponse(response_type=RESPONSE_ERROR, seq=seq, data=bytes([code]))


@pytest.fixture
def fake_tpi() -> ZenControlTPI:
    """Return a ZenControlTPI instance with mocked transport methods.

    Each send_* method is replaced with AsyncMock. Set the return_value on
    the appropriate mock to control the response.

    Example:
        fake_tpi.send_basic.return_value = make_answer(b"MyController")
    """
    tpi = MagicMock(spec=ZenControlTPI)
    tpi.send_basic = AsyncMock(return_value=make_ok())
    tpi.send_dali_colour = AsyncMock(return_value=make_ok())
    tpi.send_dmx_colour = AsyncMock(return_value=make_ok())
    tpi.send_dynamic = AsyncMock(return_value=make_ok())
    return tpi


@pytest.fixture
def scope() -> ScopeConstraint:
    """Return an unconstrained ScopeConstraint."""
    return ScopeConstraint()


@pytest.fixture
def scoped() -> ScopeConstraint:
    """Return a ScopeConstraint locked to group 3."""
    return ScopeConstraint(group_number=3)
