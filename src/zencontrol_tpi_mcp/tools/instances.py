"""DALI instance and virtual instance MCP tools."""

from __future__ import annotations

from fastmcp import Context, FastMCP

from zencontrol_tpi_mcp.api import commands
from zencontrol_tpi_mcp.api.commands import ecd_wire
from zencontrol_tpi_mcp.models.schemas import InstanceType
from zencontrol_tpi_mcp.tools._helpers import get_tpi


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def list_instances(ctx: Context) -> str:
        """List all DALI ECD addresses that have instances, with instance details.

        Queries the controller for all DALI control devices (ECDs) that have
        associated input instances (buttons, occupancy sensors, light sensors, etc.)
        and returns their configuration.

        Returns:
            A list of devices with their instances, types, and labels.
        """
        tpi = get_tpi(ctx)
        # Query in two passes to cover all 64 possible addresses
        ecd_addresses = await commands.query_dali_addresses_with_instances(tpi, start_address=0)
        ecd_addresses += await commands.query_dali_addresses_with_instances(tpi, start_address=60)
        ecd_addresses = sorted(set(ecd_addresses))

        if not ecd_addresses:
            return "No DALI ECD devices with instances found."

        lines = [f"## DALI Instances ({len(ecd_addresses)} devices)\n"]
        for ecd_addr in ecd_addresses:
            label = await commands.query_dali_device_label(tpi, ecd_wire(ecd_addr))
            instances = await commands.query_instances_by_address(tpi, ecd_addr)
            lines.append(f"### A{ecd_addr:02d} — {label or '(no label)'}")
            for inst in instances:
                inst_label = await commands.query_dali_instance_label(tpi, ecd_addr, inst["number"])
                inst_fitting = await commands.query_dali_instance_fitting_number(
                    tpi, ecd_addr, inst["number"]
                )
                type_name = (
                    inst["type"].name if isinstance(inst["type"], InstanceType) else "Unknown"
                )
                status_parts = []
                if inst.get("active"):
                    status_parts.append("active")
                if inst.get("error"):
                    status_parts.append("⚠️ error")
                status_str = f" [{', '.join(status_parts)}]" if status_parts else ""
                lines.append(
                    f"- **Instance {inst['number']}** ({type_name}){status_str}"
                    f" — {inst_label or '(no label)'}"
                )
                if inst_fitting:
                    lines.append(f"  - Fitting: {inst_fitting}")
                # Show group targets
                groups = await commands.query_instance_groups(tpi, ecd_addr, inst["number"])
                group_strs = [str(g) for g in groups if g is not None]
                if group_strs:
                    lines.append(f"  - Groups: {', '.join(group_strs)}")

        return "\n".join(lines)

    @mcp.tool()
    async def list_virtual_instances(ctx: Context) -> str:
        """List all virtual instances on the controller.

        Virtual instances can be triggered programmatically to activate
        automation rules and scenes.

        Returns:
            A list of virtual instances with their numbers and types.
        """
        tpi = get_tpi(ctx)
        instances = await commands.query_virtual_instances(tpi)
        if not instances:
            return "No virtual instances found on this controller."

        lines = [f"## Virtual Instances ({len(instances)} instances)\n"]
        for inst in instances:
            type_name = inst["type"].name if isinstance(inst["type"], InstanceType) else "Unknown"
            lines.append(f"- **Virtual {inst['number']}** ({type_name})")

        return "\n".join(lines)

    @mcp.tool()
    async def query_occupancy_timers(
        ctx: Context,
        ecd_address: int,
        instance_number: int,
    ) -> str:
        """Query occupancy sensor timer configuration for a DALI ECD instance.

        Args:
            ecd_address: DALI ECD short address (0–63).
            instance_number: Instance number.

        Returns:
            Deadtime, hold time, report time, and seconds since last occupancy event.
        """
        if not 0 <= ecd_address <= 63:
            return f"Invalid ECD address {ecd_address}. Must be 0–63."
        tpi = get_tpi(ctx)
        timers = await commands.query_occupancy_instance_timers(tpi, ecd_address, instance_number)
        if timers is None:
            return (
                f"A{ecd_address:02d} instance {instance_number}: occupancy timer data unavailable."
            )

        last = timers["last_detect"]
        last_str = f"{last} seconds ago" if last < 65535 else "never (or >65535s)"
        return (
            f"A{ecd_address:02d} instance {instance_number} occupancy timers:\n"
            f"- Deadtime: {timers['deadtime']}s\n"
            f"- Hold time: {timers['hold']}s\n"
            f"- Report time: {timers['report']}s\n"
            f"- Last occupied: {last_str}"
        )
