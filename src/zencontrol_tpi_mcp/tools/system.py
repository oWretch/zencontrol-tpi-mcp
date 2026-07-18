"""System variable and button LED MCP tools."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_tpi_mcp.api import commands
from zencontrol_tpi_mcp.api.commands import MAX_SYSVAR
from zencontrol_tpi_mcp.tools._helpers import get_tpi


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def get_system_variable(ctx: Context, variable_index: int) -> str:
        """Read the value and name of a system variable.

        System variables (0–147) are user-programmable values that can be used
        in ZenControl automation rules and scenes.
        Use list_system_variables to discover named variables before reading one
        by index.

        Args:
            variable_index: System variable index (0–147).

        Returns:
            Variable name and current value.
        """
        if not 0 <= variable_index < MAX_SYSVAR:
            return f"❌ Invalid variable index {variable_index}. Must be 0–{MAX_SYSVAR - 1}."
        tpi = get_tpi(ctx)
        name = await commands.query_system_variable_name(tpi, variable_index)
        value = await commands.query_system_variable(tpi, variable_index)
        name_str = f"'{name}'" if name else "(unnamed)"
        value_str = str(value) if value is not None else "unset"
        return f"System variable {variable_index} {name_str}: {value_str}"

    @mcp.tool()
    async def set_system_variable(
        ctx: Context,
        variable_index: int,
        value: int,
    ) -> str:
        """Set a system variable to a new value.

        This changes controller automation state. Use get_system_variable first
        if you need to inspect the current name/value before writing.

        Args:
            variable_index: System variable index (0–147).
            value: Signed 16-bit integer value (-32768–32767).

        Returns:
            Confirmation message or error description.
        """
        if not 0 <= variable_index < MAX_SYSVAR:
            return f"❌ Invalid variable index {variable_index}. Must be 0–{MAX_SYSVAR - 1}."
        tpi = get_tpi(ctx)
        try:
            success = await commands.set_system_variable(tpi, variable_index, value)
        except ValueError as exc:
            return f"❌ {exc}"
        if success:
            return f"✓ System variable {variable_index} set to {value}."
        return "✗ Controller did not acknowledge system variable update."

    @mcp.tool()
    async def list_system_variables(ctx: Context) -> str:
        """List all named system variables with their current values.

        Queries all 148 system variables and returns those that have names set.
        Unnamed variables are omitted from the result.

        Returns:
            A list of named system variables with index, name, and value.
        """
        tpi = get_tpi(ctx)
        lines = ["## System Variables (named only)\n"]
        found = 0
        for i in range(MAX_SYSVAR):
            name = await commands.query_system_variable_name(tpi, i)
            if name:
                value = await commands.query_system_variable(tpi, i)
                value_str = str(value) if value is not None else "unset"
                lines.append(f"- **[{i}] {name}:** {value_str}")
                found += 1
        if not found:
            return "No named system variables found."
        lines.insert(1, f"*{found} named variables found*\n")
        return "\n".join(lines)

    @mcp.tool()
    async def override_button_led(
        ctx: Context,
        ecd_address: int,
        instance_number: int,
        led_on: bool,
    ) -> str:
        """Override the LED state of a DALI push button instance.

        Note: This only works when the controller or TPI is managing the button
        LED state. In many configurations, the control device manages its own LED.
        This changes the controller's requested LED state.

        Args:
            ecd_address: DALI ECD short address (0–63).
            instance_number: Instance number of the push button.
            led_on: True to turn the LED on, False to turn it off.

        Returns:
            Confirmation message or error description.
        """
        if not 0 <= ecd_address <= 63:
            return f"❌ Invalid ECD address {ecd_address}. Must be 0–63."
        tpi = get_tpi(ctx)
        success = await commands.override_dali_button_led_state(
            tpi, ecd_address, instance_number, led_on
        )
        state_str = "on" if led_on else "off"
        if success:
            return f"✓ A{ecd_address:02d} instance {instance_number} LED turned {state_str}."
        return "✗ Controller did not acknowledge button LED override."

    @mcp.tool()
    async def query_button_led_state(
        ctx: Context,
        ecd_address: int,
        instance_number: int,
    ) -> str:
        """Query the last known LED state for a DALI push button instance.

        Note: This reflects the controller's last known state, which may differ
        from the physical LED state if the device manages its own LEDs.
        Use list_instances first to find push button ECD addresses and instance numbers.

        Args:
            ecd_address: DALI ECD short address (0–63).
            instance_number: Instance number of the push button.

        Returns:
            LED state (on/off) or unavailable.
        """
        if not 0 <= ecd_address <= 63:
            return f"❌ Invalid ECD address {ecd_address}. Must be 0–63."
        tpi = get_tpi(ctx)
        state = await commands.query_last_known_dali_button_led_state(
            tpi, ecd_address, instance_number
        )
        if state is None:
            return f"A{ecd_address:02d} instance {instance_number}: LED state unknown."
        return f"A{ecd_address:02d} instance {instance_number}: LED is {'on' if state else 'off'}."
