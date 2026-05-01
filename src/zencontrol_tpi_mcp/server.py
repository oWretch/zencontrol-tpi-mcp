"""FastMCP server for ZenControl TPI Advanced.

Entry points:
    create_server() → FastMCP  (for testing / programmatic embedding)
    main()          → CLI entry point (called by uv run zencontrol-tpi-mcp)
"""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from fastmcp import FastMCP

from zencontrol_tpi_mcp.api.client import ZenControlTPI
from zencontrol_tpi_mcp.scope import ScopeConstraint
from zencontrol_tpi_mcp.tools import register_all_tools

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# .env loading
# ---------------------------------------------------------------------------


def _load_runtime_dotenv() -> str | None:
    """Load environment variables from .env using runtime-friendly lookup.

    `uv run` (local source checkout) and `uvx` (published install) execute code
    from different locations. Explicitly resolving `.env` from the current
    working directory keeps behavior consistent across both modes.

    Priority:
      1. ``ZENCONTROL_ENV_FILE`` environment variable (explicit path)
      2. ``.env`` in the current working directory
      3. ``find_dotenv(usecwd=True)`` — walks up from CWD as a last resort
    """
    explicit_env_file = os.environ.get("ZENCONTROL_ENV_FILE", "").strip()
    if explicit_env_file:
        env_path = Path(explicit_env_file).expanduser()
        if env_path.is_file():
            load_dotenv(dotenv_path=env_path, override=False)
            return str(env_path)
        return None

    cwd_env_file = Path.cwd() / ".env"
    if cwd_env_file.is_file():
        load_dotenv(dotenv_path=cwd_env_file, override=False)
        return str(cwd_env_file)

    discovered = find_dotenv(filename=".env", usecwd=True)
    if discovered:
        load_dotenv(dotenv_path=discovered, override=False)
        return discovered

    return None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastMCP) -> AsyncIterator[dict]:  # type: ignore[type-arg]
    """Connect to the TPI controller and verify startup readiness."""
    host = os.environ.get("ZENCONTROL_TPI_HOST", "").strip()
    if not host:
        logger.error("ZENCONTROL_TPI_HOST is not set. Set it in .env or the environment.")
        sys.exit(1)

    port = int(os.environ.get("ZENCONTROL_TPI_PORT", "5108"))

    tpi = ZenControlTPI(host=host, port=port)
    try:
        await tpi.connect()
        logger.info("Connected to ZenControl TPI at %s:%d", host, port)
    except OSError as exc:
        logger.error(
            "Cannot connect to ZenControl controller at %s:%d — %s\n"
            "Check ZENCONTROL_TPI_HOST and ZENCONTROL_TPI_PORT.",
            host,
            port,
            exc,
        )
        sys.exit(1)

    # Optional: initialise scope from environment
    scope = ScopeConstraint()
    scope_group_env = os.environ.get("ZENCONTROL_SCOPE_GROUP", "").strip()
    if scope_group_env:
        try:
            scope.set_group(int(scope_group_env))
            logger.info("Scope locked to DALI group %d", scope.group_number)
        except (ValueError, TypeError) as exc:
            logger.warning("Invalid ZENCONTROL_SCOPE_GROUP value '%s': %s", scope_group_env, exc)

    try:
        yield {"tpi": tpi, "scope": scope}
    finally:
        await tpi.close()
        logger.info("Disconnected from ZenControl TPI")


# ---------------------------------------------------------------------------
# Server factory
# ---------------------------------------------------------------------------


def create_server() -> FastMCP:
    """Create and configure the FastMCP server instance."""
    mcp: FastMCP = FastMCP(
        name="ZenControl TPI",
        instructions=(
            "Control ZenControl DALI-2 lighting systems via the Third-Party Interface (TPI). "
            "Use the available tools to query and control DALI control gear, groups, scenes, "
            "profiles, DMX devices, and system variables. "
            "Before sending broad commands (broadcast, all groups, profile changes), "
            "confirm the scope with get_scope() or use set_scope() to restrict to a group."
        ),
        lifespan=_lifespan,
    )
    register_all_tools(mcp)
    return mcp


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the ZenControl TPI MCP server (stdio transport)."""
    import argparse

    loaded_env_file = _load_runtime_dotenv()

    parser = argparse.ArgumentParser(description="ZenControl TPI MCP server")
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: WARNING)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    if loaded_env_file:
        logger.debug("Loaded environment variables from %s", loaded_env_file)

    server = create_server()
    server.run()
