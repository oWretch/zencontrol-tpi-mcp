"""Scope constraint for the ZenControl TPI MCP server.

Optionally restricts all tools to a single DALI group, preventing accidental
commands from affecting areas outside a defined zone.
"""

from __future__ import annotations

from zencontrol_tpi_mcp.models.schemas import DaliAddress


class ScopeConstraint:
    """Optional group-level scope lock.

    When a group is set, tools must validate that the target DALI address is
    either:
    - The group address (64 + group_number), or
    - An ECG address (0–63) that is a member of the locked group.

    The MCP tools are responsible for group membership lookup; this class
    provides the validation interface.

    Attributes:
        group_number: The locked DALI group (0–15), or None if not set.
    """

    def __init__(self, group_number: int | None = None) -> None:
        if group_number is not None and not 0 <= group_number <= 15:
            raise ValueError(f"DALI group must be 0–15, got {group_number}")
        self.group_number: int | None = group_number

    @property
    def is_active(self) -> bool:
        """Return True if a scope constraint is currently set."""
        return self.group_number is not None

    def set_group(self, group: int) -> None:
        """Lock the scope to a DALI group (0–15)."""
        if not 0 <= group <= 15:
            raise ValueError(f"DALI group must be 0–15, got {group}")
        self.group_number = group

    def clear(self) -> None:
        """Remove the scope constraint (allow all addresses)."""
        self.group_number = None

    @property
    def group_address(self) -> int | None:
        """Return the DALI group address byte (64–79), or None if not set."""
        if self.group_number is None:
            return None
        return DaliAddress.for_group(self.group_number)

    def is_broadcast(self, address: int) -> bool:
        """Return True if the address is a broadcast address."""
        return address in (DaliAddress.BROADCAST_CLASSIC, DaliAddress.BROADCAST)

    def validate_address(self, address: int, member_groups: list[int] | None = None) -> str | None:
        """Check whether a DALI address is permitted under the current scope.

        Args:
            address: DALI address byte to validate.
            member_groups: Optional list of group numbers (0–15) the ECG belongs to,
                           used when validating an ECG address against the scope group.
                           Pass None to skip ECG membership check (allow all ECGs).

        Returns:
            None if the address is allowed, or an error message string if not.
        """
        if not self.is_active:
            return None

        assert self.group_number is not None  # noqa: S101 — guarded by is_active

        # Broadcast is always rejected when scope is active
        if self.is_broadcast(address):
            return (
                f"Broadcast commands are not allowed while scope is locked to group {self.group_number}. "
                "Clear the scope first with clear_scope()."
            )

        # Group address: must match the locked group
        if 64 <= address <= 79:
            locked_addr = DaliAddress.for_group(self.group_number)
            if address != locked_addr:
                target_group = DaliAddress.from_group_address(address)
                return (
                    f"Group {target_group} address is not allowed while scope is locked to group {self.group_number}."
                )
            return None

        # ECG address (0–63): check membership if provided
        if 0 <= address <= 63:
            if member_groups is not None and self.group_number not in member_groups:
                return (
                    f"ECG address {address} is not a member of scope group {self.group_number}."
                )
            return None

        return f"Unrecognised DALI address {address}."

    def describe(self) -> str:
        """Return a human-readable description of the current scope."""
        if self.group_number is None:
            return "No scope constraint active — all DALI addresses are reachable."
        return (
            f"Scope locked to DALI group {self.group_number} "
            f"(address {DaliAddress.for_group(self.group_number)})."
        )
