"""Device listing MCP tools (DALI ECG/ECD, groups, DMX)."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_tpi_mcp.api import commands
from zencontrol_tpi_mcp.tools._helpers import get_tpi


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_dali_devices(ctx: Context) -> str:
        """List all DALI control gear (ECG) devices with labels and fitting numbers.

        Returns a table of DALI devices that are configured in the controller database.
        Each entry includes the short address, label, fitting number, and group memberships.
        """
        tpi = get_tpi(ctx)
        addresses = await commands.query_control_gear_addresses(tpi)
        if not addresses:
            return "No DALI control gear found in the controller database."

        lines = [f"## DALI Control Gear ({len(addresses)} devices)\n"]
        for addr in addresses:
            label = await commands.query_dali_device_label(tpi, addr)
            fitting = await commands.query_dali_fitting_number(tpi, addr)
            groups = await commands.query_group_membership_by_address(tpi, addr)
            group_str = ", ".join(str(g) for g in groups) if groups else "none"
            lines.append(f"- **A{addr:02d}** {label or '(no label)'}")
            if fitting:
                lines.append(f"  - Fitting: {fitting}")
            lines.append(f"  - Groups: {group_str}")

        return "\n".join(lines)

    @mcp.tool()
    async def list_groups(ctx: Context) -> str:
        """List all configured DALI groups with labels and current levels.

        Returns a table of DALI groups including group number, label,
        current arc level, and occupancy status.
        """
        tpi = get_tpi(ctx)
        group_numbers = await commands.query_group_numbers(tpi)
        if not group_numbers:
            return "No DALI groups found on this controller."

        lines = [f"## DALI Groups ({len(group_numbers)} groups)\n"]
        for g in group_numbers:
            label = await commands.query_group_label(tpi, g)
            status = await commands.query_group_by_number(tpi, g)
            level_str = "unknown"
            occupancy_str = ""
            if status:
                level = status["level"]
                level_str = f"{level} ({round(level / 254 * 100)}%)" if level else "off"
                occupancy_str = " 🟢 Occupied" if status["occupancy"] else ""
            lines.append(f"- **Group {g}** — {label or '(no label)'}{occupancy_str}")
            lines.append(f"  - Level: {level_str}")

        return "\n".join(lines)

    @mcp.tool()
    async def get_group_info(ctx: Context, group_number: int) -> str:
        """Get detailed information about a specific DALI group.

        Args:
            group_number: DALI group number (0–15).

        Returns group label, current level, occupancy status, and configured scene numbers.
        """
        if not 0 <= group_number <= 15:
            return f"Invalid group number {group_number}. Must be 0–15."
        tpi = get_tpi(ctx)
        label = await commands.query_group_label(tpi, group_number)
        status = await commands.query_group_by_number(tpi, group_number)
        scenes = await commands.query_scene_numbers_for_group(tpi, group_number)

        lines = [f"## Group {group_number} — {label or '(no label)'}"]
        if status:
            level = status["level"]
            level_str = f"{level} ({round(level / 254 * 100)}%)" if level else "off"
            lines.append(f"- **Level:** {level_str}")
            lines.append(f"- **Occupied:** {'Yes' if status['occupancy'] else 'No'}")
        else:
            lines.append("- *(status unavailable)*")
        if scenes:
            lines.append(f"- **Scenes:** {', '.join(str(s) for s in scenes)}")
        else:
            lines.append("- **Scenes:** none configured")
        return "\n".join(lines)

    @mcp.tool()
    async def list_dmx_devices(ctx: Context) -> str:
        """List all DMX devices with labels and channel assignments.

        Returns a table of DMX devices configured in the ZenControl system.
        """
        tpi = get_tpi(ctx)
        device_numbers = await commands.query_dmx_device_numbers(tpi)
        if not device_numbers:
            return "No DMX devices found on this controller."

        lines = [f"## DMX Devices ({len(device_numbers)} devices)\n"]
        for num in device_numbers:
            label = await commands.query_dmx_device_label(tpi, num)
            channels = await commands.query_dmx_device_by_number(tpi, num)
            ch_str = ""
            if channels:
                ch_str = f"  - Channels: {channels['start_channel']}–{channels['stop_channel']}"
            lines.append(f"- **DMX {num}** — {label or '(no label)'}")
            if ch_str:
                lines.append(ch_str)

        return "\n".join(lines)

    @mcp.tool()
    async def get_device_colour_capabilities(ctx: Context, ecg_address: int) -> str:
        """Get colour capability information for a DALI control gear device.

        Args:
            ecg_address: DALI short address (0–63).

        Returns the supported colour modes (tunable white, XY, RGBWAF),
        primary count, channel count, and (for tunable devices) Kelvin limits.
        """
        if not 0 <= ecg_address <= 63:
            return f"Invalid ECG address {ecg_address}. Must be 0–63."
        tpi = get_tpi(ctx)
        features = await commands.query_dali_colour_features(tpi, ecg_address)
        label = await commands.query_dali_device_label(tpi, ecg_address)

        lines = [f"## Colour Capabilities — A{ecg_address:02d} {label or ''}"]
        lines.append(f"- **Tunable white (Tc):** {'Yes' if features['supports_tunable'] else 'No'}")
        lines.append(f"- **XY chromaticity:** {'Yes' if features['supports_xy'] else 'No'}")
        lines.append(f"- **Primary count:** {features['primary_count']}")
        lines.append(f"- **RGBWAF channels:** {features['rgbwaf_channels']}")

        if features["supports_tunable"]:
            limits = await commands.query_dali_colour_temp_limits(tpi, ecg_address)
            if limits:
                lines.append(f"- **Physical range:** {limits['physical_coolest']}K – {limits['physical_warmest']}K")
                lines.append(f"- **Configured range:** {limits['soft_coolest']}K – {limits['soft_warmest']}K")
                lines.append(f"- **Step value:** {limits['step_value']}K")

        if not any([features["supports_tunable"], features["supports_xy"], features["rgbwaf_channels"]]):
            lines.append("\n*(No colour control capability detected)*")

        return "\n".join(lines)
