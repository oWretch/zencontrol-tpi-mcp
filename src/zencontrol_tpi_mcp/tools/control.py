"""DALI control and DMX command MCP tools."""

from __future__ import annotations

from typing import Literal

from fastmcp import Context, FastMCP

from zencontrol_tpi_mcp.api import commands
from zencontrol_tpi_mcp.models.schemas import DaliAddress, DaliColourInfo, DaliColourType
from zencontrol_tpi_mcp.tools._helpers import confirm_broad_command, get_scope, get_tpi


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def dali_command(
        ctx: Context,
        action: Literal[
            "arc_level",
            "scene",
            "on",
            "off",
            "step_up",
            "step_down",
            "step_down_off",
            "on_step_up",
            "recall_min",
            "recall_max",
            "go_to_last_active",
            "custom_fade",
            "stop_fade",
            "dapc_sequence",
        ],
        address: int,
        level: int | None = None,
        scene: int | None = None,
        fade_seconds: int | None = None,
    ) -> str:
        """Send a DALI command to an address (ECG, group, or broadcast).

        Args:
            action: The DALI command to send. Options:
                - arc_level: Fade to a specific level (requires `level` 0–254).
                - scene: Recall a scene (requires `scene` 0–11).
                - on: Turn on to max level (RECALL MAX, instant).
                - off: Turn off (instant).
                - step_up: Step up one level (fades).
                - step_down: Step down one level (fades).
                - step_down_off: Step down or turn off if at min (instant).
                - on_step_up: Turn on or step up (instant).
                - recall_min: Go to minimum configured level (instant).
                - recall_max: Go to maximum configured level (instant).
                - go_to_last_active: Return to last non-zero level.
                - custom_fade: Fade to a level over N seconds (requires `level` and `fade_seconds`).
                - stop_fade: Stop any running fade immediately.
                - dapc_sequence: Begin DAPC sequence for immediate level control (250 ms window).
            address: DALI address byte. ECG 0–63, group 64–79, broadcast 127 or 255.
            level: Required for arc_level and custom_fade (0–254).
            scene: Required for scene action (0–11).
            fade_seconds: Required for custom_fade (0–65535 seconds).

        Returns:
            Confirmation message or error description.
        """
        tpi = get_tpi(ctx)
        scope = get_scope(ctx)

        # Validate scope
        scope_error = scope.validate_address(address)
        if scope_error:
            return f"❌ Scope violation: {scope_error}"

        # Broadcast confirmation guard
        if scope.is_broadcast(address) or address == DaliAddress.BROADCAST_CLASSIC:
            confirmed = await confirm_broad_command(
                ctx,
                f"Send **{action}** command to **all DALI devices** (broadcast address {address}).",
            )
            if not confirmed:
                return "Command cancelled."

        success = False
        match action:
            case "arc_level":
                if level is None:
                    return "❌ `level` is required for arc_level action."
                success = await commands.dali_arc_level(tpi, address, level)
            case "scene":
                if scene is None:
                    return "❌ `scene` is required for scene action."
                success = await commands.dali_scene(tpi, address, scene)
            case "on" | "recall_max":
                success = await commands.dali_recall_max(tpi, address)
            case "off":
                success = await commands.dali_off(tpi, address)
            case "recall_min":
                success = await commands.dali_recall_min(tpi, address)
            case "step_up":
                success = await commands.dali_up(tpi, address)
            case "step_down":
                success = await commands.dali_down(tpi, address)
            case "step_down_off":
                success = await commands.dali_step_down_off(tpi, address)
            case "on_step_up":
                success = await commands.dali_on_step_up(tpi, address)
            case "go_to_last_active":
                success = await commands.dali_go_to_last_active_level(tpi, address)
            case "custom_fade":
                if level is None:
                    return "❌ `level` is required for custom_fade action."
                if fade_seconds is None:
                    return "❌ `fade_seconds` is required for custom_fade action."
                success = await commands.dali_custom_fade(tpi, address, level, fade_seconds)
            case "stop_fade":
                success = await commands.dali_stop_fade(tpi, address)
            case "dapc_sequence":
                success = await commands.dali_enable_dapc_sequence(tpi, address)
            case _:
                return f"❌ Unknown action: {action}"

        addr_desc = _address_label(address)
        if success:
            return f"✓ {action} sent to {addr_desc}."
        return f"✗ Controller did not acknowledge {action} for {addr_desc}."

    @mcp.tool()
    async def set_dali_colour(
        ctx: Context,
        address: int,
        colour_type: Literal["tc", "xy", "rgbwaf"],
        tc_kelvin: int | None = None,
        xy_x: int | None = None,
        xy_y: int | None = None,
        red: int | None = None,
        green: int | None = None,
        blue: int | None = None,
        white: int | None = None,
        amber: int | None = None,
        free: int | None = None,
        arc_level: int = 0xFF,
    ) -> str:
        """Set the colour of a DALI address with an optional arc level.

        Args:
            address: DALI address byte. ECG 0–63, group 64–79, broadcast 127/255.
            colour_type: Colour mode — "tc" (tunable white), "xy", or "rgbwaf".
            tc_kelvin: Colour temperature in Kelvin (for tc mode). Typical range 2700–6500.
            xy_x: CIE 1931 X chromaticity × 65535 (for xy mode, 0–65535).
            xy_y: CIE 1931 Y chromaticity × 65535 (for xy mode, 0–65535).
            red: Red channel 0–255 (rgbwaf mode).
            green: Green channel 0–255 (rgbwaf mode).
            blue: Blue channel 0–255 (rgbwaf mode).
            white: White channel 0–255 (rgbwaf mode, optional).
            amber: Amber channel 0–255 (rgbwaf mode, optional).
            free: Free-colour channel 0–255 (rgbwaf mode, optional).
            arc_level: Arc level 0–254 to set simultaneously, or 255 to change colour only.

        Returns:
            Confirmation message or error description.
        """
        tpi = get_tpi(ctx)
        scope = get_scope(ctx)

        scope_error = scope.validate_address(address)
        if scope_error:
            return f"❌ Scope violation: {scope_error}"

        try:
            match colour_type:
                case "tc":
                    if tc_kelvin is None:
                        return "❌ `tc_kelvin` is required for tc colour type."
                    colour = DaliColourInfo(colour_type=DaliColourType.TC, tc_kelvin=tc_kelvin)
                case "xy":
                    if xy_x is None or xy_y is None:
                        return "❌ `xy_x` and `xy_y` are required for xy colour type."
                    colour = DaliColourInfo(colour_type=DaliColourType.XY, x=xy_x, y=xy_y)
                case "rgbwaf":
                    if red is None or green is None or blue is None:
                        return "❌ `red`, `green`, and `blue` are required for rgbwaf colour type."
                    colour = DaliColourInfo(
                        colour_type=DaliColourType.RGBWAF,
                        red=red,
                        green=green,
                        blue=blue,
                        white=white,
                        amber=amber,
                        free=free,
                    )
                case _:
                    return f"❌ Unknown colour_type: {colour_type}"

            success = await commands.set_dali_colour(tpi, address, colour, arc_level=arc_level)
        except ValueError as exc:
            return f"❌ Invalid colour values: {exc}"

        addr_desc = _address_label(address)
        if success:
            return f"✓ Colour set on {addr_desc}."
        return f"✗ Controller did not acknowledge colour command for {addr_desc}."

    @mcp.tool()
    async def set_dmx_colour(
        ctx: Context,
        universe: int,
        start_channel: int,
        stop_channel: int,
        levels: list[int],
        fade_time_ms: int = 0,
        fade_id: int = 0,
    ) -> str:
        """Send a DMX channel fade command.

        Args:
            universe: DMX universe number (1-indexed; use 1 for the first universe).
            start_channel: Starting DMX channel (1-indexed).
            stop_channel: Ending DMX channel (1-indexed).
            levels: Level values (0–255) for each channel from start to stop.
            fade_time_ms: Fade time in milliseconds (0 = instant).
            fade_id: Fade ID for cancellation/overwriting (0 if not needed).

        Returns:
            Confirmation message or error description.
        """
        tpi = get_tpi(ctx)
        universe_mask = 1 << (universe - 1)
        try:
            success = await commands.set_dmx_colour(
                tpi,
                fade_id=fade_id,
                universe_mask=universe_mask,
                start_channel=start_channel,
                stop_channel=stop_channel,
                levels=levels,
                fade_time_ms=fade_time_ms,
            )
        except ValueError as exc:
            return f"❌ Invalid DMX parameters: {exc}"

        if success:
            return (
                f"✓ DMX fade sent to universe {universe} channels {start_channel}–{stop_channel}."
            )
        return "✗ Controller did not acknowledge DMX command."

    @mcp.tool()
    async def inhibit_sensors(
        ctx: Context,
        address: int,
        seconds: int,
    ) -> str:
        """Prevent sensors from changing a DALI address for a duration.

        This temporarily overrides sensor-driven behaviour (e.g., occupancy sensors
        turning lights on or off) for the specified duration.

        Args:
            address: DALI address byte. ECG 0–63, group 64–79, broadcast 127/255.
            seconds: Inhibit duration (0–65535 seconds). Use 0 to cancel inhibit.

        Returns:
            Confirmation message or error description.
        """
        tpi = get_tpi(ctx)
        scope = get_scope(ctx)

        scope_error = scope.validate_address(address)
        if scope_error:
            return f"❌ Scope violation: {scope_error}"

        try:
            success = await commands.dali_inhibit(tpi, address, seconds)
        except ValueError as exc:
            return f"❌ Invalid parameters: {exc}"

        addr_desc = _address_label(address)
        if success:
            if seconds == 0:
                return f"✓ Sensor inhibit cleared on {addr_desc}."
            return f"✓ Sensors inhibited on {addr_desc} for {seconds} seconds."
        return f"✗ Controller did not acknowledge inhibit command for {addr_desc}."

    @mcp.tool()
    async def trigger_virtual_instance(ctx: Context, instance_number: int) -> str:
        """Trigger a virtual instance on the controller.

        Virtual instances allow automation rules and scenes to be activated
        programmatically without requiring a physical button press.

        Args:
            instance_number: Virtual instance number.

        Returns:
            Confirmation message or error description.
        """
        tpi = get_tpi(ctx)
        success = await commands.trigger_virtual_instance(tpi, instance_number)
        if success:
            return f"✓ Virtual instance {instance_number} triggered."
        return f"✗ Controller did not acknowledge virtual instance {instance_number}."


def _address_label(address: int) -> str:
    """Return a human-readable DALI address description."""
    if address in (DaliAddress.BROADCAST, DaliAddress.BROADCAST_CLASSIC):
        return "all devices (broadcast)"
    if 64 <= address <= 79:
        return f"group {address - 64}"
    return f"A{address:02d}"
