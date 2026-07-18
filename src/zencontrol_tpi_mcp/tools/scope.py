"""Scope constraint MCP tools."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_tpi_mcp.tools._helpers import get_scope as _get_scope


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def set_scope(ctx: Context, group_number: int) -> str:
        """Lock all DALI commands to a specific group.

        When a scope is active, commands to other groups, individual devices not
        in this group, or broadcast addresses will be rejected.
        This affects subsequent tool calls in the MCP server session; it does not
        change controller configuration.

        Args:
            group_number: DALI group number (0–15) to lock scope to.

        Returns:
            Confirmation of the new scope.
        """
        scope = _get_scope(ctx)
        try:
            scope.set_group(group_number)
        except ValueError as exc:
            return f"❌ {exc}"
        return f"✓ Scope locked to DALI group {group_number}. {scope.describe()}"

    @mcp.tool()
    async def get_scope(ctx: Context) -> str:
        """Show the current scope constraint.

        Use this before sending broad or state-changing commands to confirm
        whether the MCP server is restricted to a DALI group.

        Returns:
            Description of the active scope constraint, or that no constraint is set.
        """
        scope = _get_scope(ctx)
        return scope.describe()

    @mcp.tool()
    async def clear_scope(ctx: Context) -> str:
        """Remove the scope constraint, allowing commands to all DALI addresses.

        This affects subsequent MCP tool calls only; it does not change
        controller configuration.

        Returns:
            Confirmation that the scope constraint has been cleared.
        """
        scope = _get_scope(ctx)
        scope.clear()
        return "✓ Scope constraint cleared. All DALI addresses are now reachable."
