"""Shared helper utilities for ZenControl TPI MCP tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp import Context

from zencontrol_tpi_mcp.api.client import ZenControlTPI
from zencontrol_tpi_mcp.scope import ScopeConstraint

if TYPE_CHECKING:
    pass


def get_tpi(ctx: Context) -> ZenControlTPI:
    """Extract the TPI client from the FastMCP lifespan context."""
    return ctx.lifespan_context["tpi"]  # type: ignore[index]


def get_scope(ctx: Context) -> ScopeConstraint:
    """Extract the ScopeConstraint from the FastMCP lifespan context."""
    return ctx.lifespan_context["scope"]  # type: ignore[index]


async def confirm_broad_command(ctx: Context, description: str) -> bool:
    """Elicit user confirmation before sending a broad (broadcast/whole-controller) command.

    Args:
        ctx: FastMCP context.
        description: Human-readable description of what the command will do.

    Returns:
        True if the user confirmed, False if they declined.
    """
    try:
        result = await ctx.elicit(
            message=(
                f"⚠️ Broad command confirmation required\n\n"
                f"{description}\n\n"
                "This will affect all lights/devices in scope. Do you want to proceed?"
            ),
            response_type=None,
        )
        return result.action == "accept"
    except Exception:
        # If elicitation is not supported (e.g. non-interactive client), default to False
        return False


def level_label(level: int | None) -> str:
    """Return a human-readable label for an arc level (0–254 or None)."""
    if level is None:
        return "mixed/unknown"
    if level == 0:
        return "off (0)"
    return f"{level} ({round(level / 254 * 100)}%)"


def colour_label(colour_type: object, colour_info: object | None) -> str:
    """Return a compact human-readable colour description."""
    from zencontrol_tpi_mcp.models.schemas import DaliColourInfo, DaliColourType

    if not isinstance(colour_info, DaliColourInfo):
        return "unknown"
    if colour_info.colour_type == DaliColourType.TC:
        return f"{colour_info.tc_kelvin}K"
    if colour_info.colour_type == DaliColourType.XY:
        return f"XY ({colour_info.x}, {colour_info.y})"
    if colour_info.colour_type == DaliColourType.RGBWAF:
        return f"RGB ({colour_info.red},{colour_info.green},{colour_info.blue})" + (
            f" W={colour_info.white}" if colour_info.white else ""
        )
    return "unknown"
