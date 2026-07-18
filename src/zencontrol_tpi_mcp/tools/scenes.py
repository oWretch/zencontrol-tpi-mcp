"""Scene discovery MCP tools."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_tpi_mcp.api import commands
from zencontrol_tpi_mcp.tools._helpers import get_tpi


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_scenes(ctx: Context, group_number: int) -> str:
        """List all configured scenes for a DALI group with labels and level data.

        Use this after list_groups when you need the scene numbers and labels
        available for a group. For per-device stored scene levels, use
        get_device_scenes.

        Args:
            group_number: DALI group number (0–15).

        Returns the scene number and label for all configured scenes in the
        specified group, or a message that no scenes are configured.
        """
        if not 0 <= group_number <= 15:
            return f"Invalid group number {group_number}. Must be 0–15."
        tpi = get_tpi(ctx)
        group_label = await commands.query_group_label(tpi, group_number)
        scene_numbers = await commands.query_scene_numbers_for_group(tpi, group_number)

        if not scene_numbers:
            return f"No scenes configured for group {group_number} ({group_label or 'no label'})."

        lines = [f"## Scenes for Group {group_number} — {group_label or '(no label)'}"]
        lines.append(f"*{len(scene_numbers)} scenes configured*\n")

        for scene_num in scene_numbers:
            scene_label = await commands.query_scene_label_for_group(tpi, group_number, scene_num)
            lines.append(f"- **Scene {scene_num}** — {scene_label or '(no label)'}")

        return "\n".join(lines)

    @mcp.tool()
    async def get_device_scenes(ctx: Context, ecg_address: int) -> str:
        """Get the scene level configuration for a specific DALI device.

        Use this when you know an ECG short address and want to see which scenes
        contain stored levels for that fixture.

        Args:
            ecg_address: DALI short address (0–63).

        Returns all scene numbers this device participates in, along with the
        arc level stored for each scene.
        """
        if not 0 <= ecg_address <= 63:
            return f"Invalid ECG address {ecg_address}. Must be 0–63."
        tpi = get_tpi(ctx)
        label = await commands.query_dali_device_label(tpi, ecg_address)
        scene_numbers = await commands.query_scene_numbers_by_address(tpi, ecg_address)

        if not scene_numbers:
            return f"A{ecg_address:02d} ({label or 'no label'}) has no scene level data."

        levels = await commands.query_scene_levels_by_address(tpi, ecg_address)
        lines = [f"## Scene Levels — A{ecg_address:02d} {label or ''}"]
        for snum in scene_numbers:
            level = levels[snum] if snum < len(levels) else None
            level_str = (
                f"{level} ({round(level / 254 * 100)}%)" if level is not None else "mask (0xFF)"
            )
            lines.append(f"- **Scene {snum}:** {level_str}")

        return "\n".join(lines)
