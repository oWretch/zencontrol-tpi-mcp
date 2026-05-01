"""ZenControl TPI MCP tools package."""

from __future__ import annotations

from fastmcp import FastMCP


def register_all_tools(mcp: FastMCP) -> None:
    """Register all tool modules with the FastMCP server."""
    from zencontrol_tpi_mcp.tools import (
        control,
        controller,
        devices,
        instances,
        profiles,
        scenes,
        scope,
        status,
        system,
    )

    controller.register(mcp)
    devices.register(mcp)
    scenes.register(mcp)
    control.register(mcp)
    status.register(mcp)
    profiles.register(mcp)
    instances.register(mcp)
    system.register(mcp)
    scope.register(mcp)
