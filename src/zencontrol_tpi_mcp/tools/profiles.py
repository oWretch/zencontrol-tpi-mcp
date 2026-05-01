"""Profile management MCP tools."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_tpi_mcp.api import commands
from zencontrol_tpi_mcp.api.commands import PROFILE_SCHEDULED
from zencontrol_tpi_mcp.tools._helpers import confirm_broad_command, get_tpi


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_profiles(ctx: Context) -> str:
        """List all configured profiles with numbers, labels, and status.

        Returns the active profile, a list of all available profiles, their
        enabled/disabled state and priority level.
        """
        tpi = get_tpi(ctx)
        info = await commands.query_profile_information(tpi)
        if info is None:
            return "Profile information is unavailable."

        state = info["state"]
        profiles = info["profiles"]

        lines = ["## Profiles"]
        current = state.get("current_active_profile")
        scheduled = state.get("last_scheduled_profile")
        lines.append(f"- **Active profile:** {current if current is not None else 'unknown'}")
        lines.append(f"- **Last scheduled:** {scheduled if scheduled is not None else 'unknown'}")
        if state.get("last_overridden_utc"):
            lines.append(f"- **Last override:** {state['last_overridden_utc']}")
        lines.append("")

        if not profiles:
            lines.append("*(No profiles configured)*")
            return "\n".join(lines)

        # Fetch labels for all profiles
        for pnum, pdata in sorted(profiles.items()):
            label = await commands.query_profile_label(tpi, pnum)
            active_marker = " ← **active**" if pnum == current else ""
            status_str = "✓ enabled" if pdata["enabled"] else "✗ disabled"
            lines.append(
                f"- **Profile {pnum}** — {label or '(no label)'}{active_marker}"
                f"  [{status_str}, {pdata['priority_label']} priority]"
            )

        return "\n".join(lines)

    @mcp.tool()
    async def get_current_profile(ctx: Context) -> str:
        """Get the currently active profile number and label.

        Returns:
            Active profile number and label.
        """
        tpi = get_tpi(ctx)
        profile_num = await commands.query_current_profile_number(tpi)
        if profile_num is None:
            return "Could not determine the active profile."
        label = await commands.query_profile_label(tpi, profile_num)
        return f"Active profile: **{profile_num}** — {label or '(no label)'}"

    @mcp.tool()
    async def change_profile(
        ctx: Context,
        profile_number: int,
    ) -> str:
        """Activate a lighting profile on the controller.

        Profiles control scheduled lighting scenes and behaviours across the
        entire controller. Activating a profile affects all connected devices.

        Use profile_number 65535 to return to the scheduled (automatic) profile.

        Args:
            profile_number: Profile number to activate (0–65534), or 65535 to return
                            to scheduled.

        Returns:
            Confirmation message or error description.
        """
        tpi = get_tpi(ctx)

        if not 0 <= profile_number <= PROFILE_SCHEDULED:
            return f"❌ Invalid profile number {profile_number}. Must be 0–65535."

        label = await commands.query_profile_label(tpi, profile_number) if profile_number != PROFILE_SCHEDULED else None
        profile_desc = (
            "the scheduled (automatic) profile"
            if profile_number == PROFILE_SCHEDULED
            else f"profile {profile_number} ({label or 'no label'})"
        )

        confirmed = await confirm_broad_command(
            ctx,
            f"Activate **{profile_desc}** on the controller. This will change lighting "
            "behaviour across all devices on this controller.",
        )
        if not confirmed:
            return "Profile change cancelled."

        try:
            success = await commands.change_profile_number(tpi, profile_number)
        except ValueError as exc:
            return f"❌ {exc}"

        if success:
            return f"✓ Activated {profile_desc}."
        return f"✗ Controller did not acknowledge profile change to {profile_desc}."
