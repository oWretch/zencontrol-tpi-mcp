"""DALI and DMX status query MCP tools."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_tpi_mcp.api import commands
from zencontrol_tpi_mcp.tools._helpers import colour_label, get_tpi, level_label


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def query_level(ctx: Context, address: int) -> str:
        """Query the current arc level on a DALI address (ECG or group).

        Args:
            address: DALI address byte. ECG 0–63, group 64–79.

        Returns:
            Current arc level (0–254) or "mixed" if the group has varying levels.
        """
        tpi = get_tpi(ctx)
        level = await commands.dali_query_level(tpi, address)
        addr_desc = _address_label(address)
        return f"{addr_desc}: level {level_label(level)}"

    @mcp.tool()
    async def query_device_status(ctx: Context, address: int) -> str:
        """Query DALI status flags for an address (ECG or group).

        Args:
            address: DALI address byte. ECG 0–63, group 64–79, broadcast 127/255.

        Returns:
            A list of active status flags (lamp failure, fade running, etc.).
        """
        tpi = get_tpi(ctx)
        status = await commands.dali_query_control_gear_status(tpi, address)
        addr_desc = _address_label(address)
        if status is None:
            return f"{addr_desc}: status unavailable."

        flags = []
        if status["cg_failure"]:
            flags.append("⚠️ Control gear failure")
        if status["lamp_failure"]:
            flags.append("🔴 Lamp failure")
        if status["lamp_power_on"]:
            flags.append("✓ Lamp on")
        if status["limit_error"]:
            flags.append("⚠️ Limit error (arc level out of range requested)")
        if status["fade_running"]:
            flags.append("⏳ Fade in progress")
        if status["reset"]:
            flags.append("🔄 Reset state")
        if status["missing_short_address"]:
            flags.append("❓ Missing short address")
        if status["power_failure"]:
            flags.append("⚡ Power failure detected")

        if not flags:
            return f"{addr_desc}: all OK — no faults detected."
        return f"{addr_desc} status:\n" + "\n".join(f"- {f}" for f in flags)

    @mcp.tool()
    async def query_colour(ctx: Context, address: int) -> str:
        """Query the current colour state of a DALI ECG address.

        Args:
            address: DALI ECG short address (0–63).

        Returns:
            Current colour type and values (Kelvin, XY, or RGBWAF channels).
        """
        tpi = get_tpi(ctx)
        colour = await commands.query_dali_colour(tpi, address)
        addr_desc = _address_label(address)
        if colour is None:
            return f"{addr_desc}: colour information unavailable."
        return f"{addr_desc}: colour = {colour_label(colour.colour_type, colour)}"

    @mcp.tool()
    async def query_last_scene(ctx: Context, address: int) -> str:
        """Query the last recalled scene number for a DALI address.

        Args:
            address: DALI address byte. ECG 0–63, group 64–79, broadcast 127/255.

        Returns:
            Last scene number and whether it is still the active state.
        """
        tpi = get_tpi(ctx)
        scene = await commands.dali_query_last_scene(tpi, address)
        is_current = await commands.dali_query_last_scene_is_current(tpi, address)
        addr_desc = _address_label(address)
        if scene is None:
            return f"{addr_desc}: no scene has been recalled."
        current_str = " (still active)" if is_current else " (no longer active)"
        return f"{addr_desc}: last scene = {scene}{current_str}"

    @mcp.tool()
    async def query_dmx_level(ctx: Context, channel: int) -> str:
        """Query the current level on a DMX channel.

        Args:
            channel: DMX channel number.

        Returns:
            Current level (0–255) on the specified channel.
        """
        tpi = get_tpi(ctx)
        level = await commands.query_dmx_level_by_channel(tpi, channel)
        if level is None:
            return f"DMX channel {channel}: level unavailable."
        return f"DMX channel {channel}: level {level} ({round(level / 255 * 100)}%)"

    @mcp.tool()
    async def query_device_type(ctx: Context, ecg_address: int) -> str:
        """Query the device type bitmask for a DALI ECG.

        Args:
            ecg_address: DALI short address (0–63).

        Returns:
            List of device type numbers indicating device capabilities.
        """
        tpi = get_tpi(ctx)
        types = await commands.query_dali_cg_type(tpi, ecg_address)
        if not types:
            return f"A{ecg_address:02d}: device type information unavailable."
        type_names = {
            0: "Fluorescent",
            1: "Emergency lighting",
            2: "HID discharge",
            3: "Low-voltage halogen",
            4: "Incandescent",
            5: "DC control gear",
            6: "LED",
            7: "Relay",
            8: "Colour control",
        }
        type_strs = [type_names.get(t, f"Type {t}") for t in types]
        return f"A{ecg_address:02d}: {', '.join(type_strs)}"

    @mcp.tool()
    async def query_level_limits(ctx: Context, ecg_address: int) -> str:
        """Query the min/max level limits and fade state for a DALI ECG.

        Args:
            ecg_address: DALI short address (0–63).

        Returns:
            Minimum and maximum configured arc levels, and whether a fade is running.
        """
        tpi = get_tpi(ctx)
        min_level = await commands.dali_query_min_level(tpi, ecg_address)
        max_level = await commands.dali_query_max_level(tpi, ecg_address)
        fade_running = await commands.dali_query_fade_running(tpi, ecg_address)
        label = await commands.query_dali_device_label(tpi, ecg_address)
        lines = [f"## A{ecg_address:02d} {label or ''} — Level Limits"]
        lines.append(f"- Min: {min_level if min_level is not None else 'unknown'}")
        lines.append(f"- Max: {max_level if max_level is not None else 'unknown'}")
        lines.append(f"- Fade running: {'Yes' if fade_running else 'No'}")
        return "\n".join(lines)


def _address_label(address: int) -> str:
    from zencontrol_tpi_mcp.models.schemas import DaliAddress

    if address in (DaliAddress.BROADCAST, DaliAddress.BROADCAST_CLASSIC):
        return "All devices (broadcast)"
    if 64 <= address <= 79:
        return f"Group {address - 64}"
    return f"A{address:02d}"
