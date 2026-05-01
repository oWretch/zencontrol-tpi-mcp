# Agent Instructions — zencontrol-tpi-mcp

This is an MCP (Model Context Protocol) server that lets AI assistants control
ZenControl DALI-2 lighting systems via the **ZenControl Third-Party Interface
(TPI)** — a local/LAN-based JSON-over-TCP protocol that communicates directly
with ZenControl gateway controllers without going through the cloud.

This project is structurally modelled on [`zencontrol-cloud-mcp`](https://github.com/oWretch/zencontrol-cloud-mcp).
Read `BOOTSTRAP.md` for the full architectural decisions and lessons learned
from that implementation before making changes.

---

## Language & Runtime

- **Python 3.11+**, async-first (`async def` everywhere).
- Package manager: **uv**. Run tools with `uv run`.
- Entry point: `src/zencontrol_tpi_mcp/server.py` → `main()`.

---

## Key Libraries

| Library      | Purpose                                              |
|-------------|------------------------------------------------------|
| `fastmcp`   | MCP server framework (tools, resources, lifespan)    |
| `pydantic`  | Data models / schemas for all TPI types              |
| `python-dotenv` | Load `.env` config at startup                   |
| `platformdirs` | Cross-platform config/state directories           |

> **Note:** The TPI uses a persistent TCP socket connection, not HTTP.
> Use `asyncio.open_connection` / `asyncio.StreamReader` / `asyncio.StreamWriter`
> rather than `httpx`. See `BOOTSTRAP.md §3` for details.

---

## File Organisation

```text
src/zencontrol_tpi_mcp/
  server.py        — FastMCP server, lifespan, CLI entry point
  tools/           — MCP tool definitions (one file per domain)
    __init__.py    — register_all_tools()
    sites.py       — site/controller discovery
    devices.py     — device/group/ECG listing
    control.py     — DALI command dispatch
    status.py      — query current levels / sensor state
    scope.py       — set_scope / get_scope / clear_scope
  api/
    __init__.py
    client.py      — persistent TCP client, framing, reconnect logic
    commands.py    — typed helpers for every TPI command
  models/
    __init__.py
    schemas.py     — Pydantic models for TPI request/response types
  scope.py         — ScopeConstraint (single-controller guardrail)
  resources/
    __init__.py
    hierarchy.py   — MCP resources for controller hierarchy URIs
```

---

## Naming Conventions

- **Functions / tools:** `snake_case` (e.g., `list_groups`, `control_light`).
- **Pydantic models:** `PascalCase` (e.g., `TpiResponse`, `GroupSummary`).
- **Files:** `snake_case.py`, one module per logical domain.

---

## Tool Design Patterns

### Accessing the API client

All tools get the TPI client from the MCP lifespan context:

```python
tpi: ZenControlTPI = ctx.lifespan_context["tpi"]
```

Never construct `ZenControlTPI` inside a tool function.

### Scope-parameterised tools

Where a resource can be queried at multiple levels, accept `scope_type` +
`scope_id` rather than creating separate tools per level:

```python
@mcp.tool()
async def list_groups(
    ctx: Context,
    scope_type: Literal["controller", "group"],
    scope_id: str,
) -> str: ...
```

### Return values

Tools return **formatted strings** (not raw JSON/dicts) because the output is
consumed by an LLM. Use bullet lists, tables, or short paragraphs.

### Elicitation guard for broad commands

Before sending commands to large scopes (the whole controller, a floor, etc.),
use `ctx.elicit()` to ask the user for confirmation. See the `_helpers.py`
pattern from the cloud implementation.

---

## Authentication

The TPI authenticates with a static **API key** (not OAuth). The key is
passed as part of every request packet. Store it in the environment:

```
ZENCONTROL_TPI_HOST=192.168.1.100    # controller IP or hostname
ZENCONTROL_TPI_PORT=52100            # default TPI port (confirm with ZenControl docs)
ZENCONTROL_TPI_API_KEY=<key>         # issued by the ZenControl controller
```

**Never** hardcode keys in source. Read them with `os.environ.get(...)` and
raise `SystemExit` with a clear message if they are missing at startup.

---

## Error Handling

- **Connection refused / timeout** → surface clearly; instruct user to verify
  `ZENCONTROL_TPI_HOST` and `ZENCONTROL_TPI_PORT`.
- **Auth rejected** (bad API key) → surface clearly; do not retry forever.
- **DALI errors in response** → include error code and message in the tool
  return string so the LLM can report them.
- **Reconnect logic** → implement in `client.py`; tools should not need to
  know whether a reconnect occurred.
- Prefer raising descriptive exceptions over returning empty strings on failure.

---

## Testing

- Framework: **pytest** + **pytest-asyncio**.
- Mock the TCP connection with `unittest.mock.AsyncMock` or a custom asyncio
  protocol stub — do **not** require a live controller in tests.
- Test that tools return the expected formatted strings for canned TPI
  responses.
- Mark async tests with `@pytest.mark.asyncio`.

---

## Linting & Formatting

- **Ruff** for both linting and formatting.
- Run before committing:
  ```bash
  uv run ruff check src/ tests/
  uv run ruff format --check src/ tests/
  ```

---

## Local MCP Restart Workflow

After changing MCP-facing code, restart the server from VS Code:
- `MCP: List Servers` → select `zencontrol-tpi` → `Restart`
- or the inline restart action in `.vscode/mcp.json`

Use `uv run zencontrol-tpi-mcp --log-level DEBUG` when reproducing startup
issues outside VS Code.

---

## Things to Avoid

- Do **not** add synchronous blocking calls (`socket.recv`, `time.sleep`).
- Do **not** store credentials in source code.
- Do **not** create tools that duplicate existing ones — extend the scope
  parameter instead.
- Do **not** return raw dicts/JSON from tools — always format for LLM readability.
- Do **not** open a new TCP connection per tool call — reuse the persistent
  client from lifespan context.
