"""Controller info and health MCP tools."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_tpi_mcp.api import commands
from zencontrol_tpi_mcp.tools._helpers import get_tpi


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_controller_info(ctx: Context) -> str:
        """Get ZenControl controller label, firmware version, fitting number, and status.

        Returns a summary of the controller's identity and operational state,
        including whether the DALI startup sequence is complete.
        """
        tpi = get_tpi(ctx)
        label = await commands.query_controller_label(tpi)
        version = await commands.query_controller_version(tpi)
        fitting = await commands.query_controller_fitting_number(tpi)
        startup = await commands.query_controller_startup_complete(tpi)
        dali_ready = await commands.query_is_dali_ready(tpi)

        lines = ["## ZenControl Controller"]
        lines.append(f"- **Label:** {label or '(none)'}")
        lines.append(f"- **Version:** {version or 'unknown'}")
        lines.append(f"- **Fitting number:** {fitting or '(none)'}")
        lines.append(f"- **Startup complete:** {'✓ Yes' if startup else '⏳ In progress'}")
        lines.append(f"- **DALI line ready:** {'✓ Yes' if dali_ready else '✗ Fault detected'}")

        if not startup:
            lines.append(
                "\n> ⚠️ The controller is still completing its startup sequence. "
                "DALI device queries may return incomplete results until startup finishes."
            )
        return "\n".join(lines)
