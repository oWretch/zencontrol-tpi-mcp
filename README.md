# ZenControl TPI MCP Server

An MCP (Model Context Protocol) server for controlling ZenControl DALI-2
lighting systems via the **ZenControl Third-Party Interface (TPI)** — a
direct LAN protocol that communicates with ZenControl Pro-series controllers
without going through the cloud.

## Features

- DALI lighting commands: arc level, scenes, on/off, step up/down, custom fade
- DALI colour control: Tc (colour temperature), XY chromaticity, RGBWAF
- DMX channel commands with pattern and fade support
- Device and group discovery with labels
- Scene discovery and management
- Controller profile management
- DALI instance and virtual instance support
- Occupancy sensor timer queries
- System variable read/write
- Scope constraint to lock the server to a specific DALI group

## Requirements

- Python 3.11+
- A ZenControl Pro-series controller with TPI Advanced licence
- Network access to the controller (LAN or VLAN)

## Installation

```bash
uv add zencontrol-tpi-mcp
```

Or for development:

```bash
git clone https://github.com/oWretch/zencontrol-tpi-mcp
cd zencontrol-tpi-mcp
uv sync
```

## Configuration

Copy `.env.example` to `.env` and set your controller address:

```bash
cp .env.example .env
```

Edit `.env`:

```env
ZENCONTROL_TPI_HOST=192.168.1.100
ZENCONTROL_TPI_PORT=5108        # optional, default: 5108
ZENCONTROL_SCOPE_GROUP=0        # optional, lock to DALI group 0
```

No API key is required — the TPI protocol has no authentication mechanism;
access control is provided at the network level.

## Usage

### stdio (for Claude Desktop, VS Code, etc.)

```bash
uv run zencontrol-tpi-mcp
```

### Debug mode

```bash
uv run zencontrol-tpi-mcp --log-level DEBUG
```

### VS Code

See `.vscode/mcp.json` for VS Code MCP configuration.

## Protocol

This server uses TPI Advanced, a binary UDP/TCP protocol on port 5108.
All commands use TCP for reliable, ordered delivery.

See the [TPI documentation](https://support.zencontrol.com) for protocol details.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0
