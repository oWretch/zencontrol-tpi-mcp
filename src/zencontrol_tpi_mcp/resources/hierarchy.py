"""MCP resource handlers for the ZenControl TPI hierarchy."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_tpi_mcp.api import commands
from zencontrol_tpi_mcp.tools._helpers import get_tpi


def register_resources(mcp: FastMCP) -> None:
    """Register all URI-addressable MCP resources."""

    @mcp.resource("zencontrol-tpi://controller")
    async def controller_resource(ctx: Context) -> str:
        """Controller identity, version, and operational status."""
        tpi = get_tpi(ctx)
        label = await commands.query_controller_label(tpi)
        version = await commands.query_controller_version(tpi)
        fitting = await commands.query_controller_fitting_number(tpi)
        startup = await commands.query_controller_startup_complete(tpi)
        dali_ready = await commands.query_is_dali_ready(tpi)
        return (
            f"label={label!r}, version={version!r}, fitting={fitting!r}, "
            f"startup_complete={startup}, dali_ready={dali_ready}"
        )

    @mcp.resource("zencontrol-tpi://groups")
    async def groups_resource(ctx: Context) -> str:
        """All DALI groups with numbers and labels."""
        tpi = get_tpi(ctx)
        group_numbers = await commands.query_group_numbers(tpi)
        lines = []
        for g in group_numbers:
            label = await commands.query_group_label(tpi, g)
            lines.append(f"group={g}, label={label!r}")
        return "\n".join(lines) if lines else "No groups configured."

    @mcp.resource("zencontrol-tpi://groups/{group_number}")
    async def group_detail_resource(ctx: Context, group_number: str) -> str:
        """Group detail: members, scenes, current level."""
        tpi = get_tpi(ctx)
        g = int(group_number)
        label = await commands.query_group_label(tpi, g)
        status = await commands.query_group_by_number(tpi, g)
        scenes = await commands.query_scene_numbers_for_group(tpi, g)
        level = status["level"] if status else None
        return (
            f"group={g}, label={label!r}, level={level}, "
            f"scenes={scenes}"
        )

    @mcp.resource("zencontrol-tpi://devices")
    async def devices_resource(ctx: Context) -> str:
        """All DALI ECG devices with addresses and labels."""
        tpi = get_tpi(ctx)
        addresses = await commands.query_control_gear_addresses(tpi)
        lines = []
        for addr in addresses:
            label = await commands.query_dali_device_label(tpi, addr)
            lines.append(f"address={addr}, label={label!r}")
        return "\n".join(lines) if lines else "No DALI control gear found."

    @mcp.resource("zencontrol-tpi://scenes/{group_number}")
    async def scenes_resource(ctx: Context, group_number: str) -> str:
        """Scenes for a DALI group."""
        tpi = get_tpi(ctx)
        g = int(group_number)
        scene_numbers = await commands.query_scene_numbers_for_group(tpi, g)
        lines = []
        for s in scene_numbers:
            scene_label = await commands.query_scene_label_for_group(tpi, g, s)
            lines.append(f"scene={s}, label={scene_label!r}")
        return "\n".join(lines) if lines else f"No scenes for group {g}."

    @mcp.resource("zencontrol-tpi://profiles")
    async def profiles_resource(ctx: Context) -> str:
        """All profiles with numbers and labels."""
        tpi = get_tpi(ctx)
        info = await commands.query_profile_information(tpi)
        if not info:
            return "Profile information unavailable."
        current = info["state"].get("current_active_profile")
        lines = [f"current_active_profile={current}"]
        for pnum, pdata in sorted(info["profiles"].items()):
            label = await commands.query_profile_label(tpi, pnum)
            lines.append(f"profile={pnum}, label={label!r}, enabled={pdata['enabled']}, priority={pdata['priority_label']}")
        return "\n".join(lines)

    @mcp.resource("zencontrol-tpi://dmx")
    async def dmx_resource(ctx: Context) -> str:
        """All DMX devices with numbers, labels, and channels."""
        tpi = get_tpi(ctx)
        device_numbers = await commands.query_dmx_device_numbers(tpi)
        lines = []
        for num in device_numbers:
            label = await commands.query_dmx_device_label(tpi, num)
            channels = await commands.query_dmx_device_by_number(tpi, num)
            ch_str = f"{channels['start_channel']}-{channels['stop_channel']}" if channels else "unknown"
            lines.append(f"number={num}, label={label!r}, channels={ch_str}")
        return "\n".join(lines) if lines else "No DMX devices found."
