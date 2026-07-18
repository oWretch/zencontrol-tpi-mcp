"""Persistent async TCP client for the ZenControl TPI Advanced protocol.

Maintains a single connection to the controller. Automatically reconnects
on disconnect. Request/response matching is via a 1-byte sequence counter.

The read loop uses asyncio.StreamReader.readexactly() rather than readline()
because TPI Advanced is a binary protocol, not newline-delimited.
"""

from __future__ import annotations

import asyncio
import logging

from zencontrol_tpi_mcp.api.framing import (
    FrameError,
    TPIResponse,
    build_basic_frame,
    build_dali_colour_frame,
    build_dmx_colour_frame,
    build_dynamic_frame,
    parse_response_body,
    parse_response_header,
)

logger = logging.getLogger(__name__)

# Commands used internally by the client
_CMD_QUERY_CONTROLLER_STARTUP_COMPLETE = 0x27

_DEFAULT_TIMEOUT = 10.0
_RECONNECT_DELAY = 2.0


class TPIError(Exception):
    """Raised when the controller returns an error response."""

    def __init__(self, message: str, error_code: int | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class ZenControlTPI:
    """Async persistent TCP client for the ZenControl Third-Party Interface.

    Maintains a single connection. Automatically reconnects on disconnect.
    Request/response matching is done via a 1-byte sequence counter.

    Usage:
        tpi = ZenControlTPI(host="192.168.1.100", port=5108)
        await tpi.connect()
        response = await tpi.send_basic(command=0x24, address=0)  # QUERY_CONTROLLER_LABEL
        await tpi.close()
    """

    def __init__(self, host: str, port: int = 5108, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[int, asyncio.Future[TPIResponse]] = {}
        self._read_task: asyncio.Task[None] | None = None
        self._seq: int = 0
        self._seq_lock = asyncio.Lock()
        self._connect_lock = asyncio.Lock()
        self._send_lock = asyncio.Lock()
        self._auto_reconnect = False

    async def connect(self) -> None:
        """Open the TCP connection and start the background read loop."""
        async with self._connect_lock:
            self._auto_reconnect = True
            await self._connect_unlocked()

    async def _connect_unlocked(self) -> None:
        """Open a fresh TCP connection. Caller must hold _connect_lock."""
        await self._close_unlocked()
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self._host, self._port), timeout=self._timeout
        )
        self._read_task = asyncio.create_task(self._read_loop(), name="tpi-read-loop")
        logger.info("Connected to TPI at %s:%d", self._host, self._port)

    async def close(self) -> None:
        """Close the TCP connection and cancel the background read loop."""
        async with self._connect_lock:
            await self._close_unlocked()
        logger.info("Disconnected from TPI")

    async def _close_unlocked(self) -> None:
        """Close the current TCP connection. Caller must hold _connect_lock."""
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None

    def _has_active_connection(self) -> bool:
        """Return True when the socket and read loop are both usable."""
        return (
            self._writer is not None
            and not self._writer.is_closing()
            and self._read_task is not None
            and not self._read_task.done()
        )

    async def _ensure_connected(self) -> None:
        """Reconnect if the socket or read loop has gone stale."""
        if self._has_active_connection():
            return
        async with self._connect_lock:
            if self._has_active_connection():
                return
            logger.info("Reconnecting to TPI at %s:%d", self._host, self._port)
            await self._connect_unlocked()

    async def _next_seq(self) -> int:
        """Atomically increment and return the next sequence counter (0–255, wrapping)."""
        async with self._seq_lock:
            seq = self._seq
            self._seq = (self._seq + 1) % 256
            return seq

    async def _read_loop(self) -> None:
        """Continuously read response frames and dispatch to waiting coroutines."""
        assert self._reader is not None
        try:
            while True:
                # Read 3-byte header: response_type | seq | data_length
                try:
                    header = await self._reader.readexactly(3)
                except asyncio.IncompleteReadError:
                    logger.warning("TPI connection closed by controller")
                    break

                try:
                    response_type, seq, data_length = parse_response_header(header)
                except FrameError as exc:
                    logger.error("Bad response header: %s", exc)
                    continue

                # Read data_length bytes + 1 checksum byte
                try:
                    body = await self._reader.readexactly(data_length + 1)
                except asyncio.IncompleteReadError:
                    logger.warning("TPI connection closed mid-response")
                    break

                try:
                    response = parse_response_body(header, body)
                except FrameError as exc:
                    logger.error("Bad response body (seq=%d): %s", seq, exc)
                    # Still try to deliver to waiter so it can time out cleanly
                    if seq in self._pending:
                        fut = self._pending.pop(seq)
                        if not fut.done():
                            fut.set_exception(exc)
                    continue

                logger.debug("← %r", response)

                if seq in self._pending:
                    fut = self._pending.pop(seq)
                    if not fut.done():
                        fut.set_result(response)
                else:
                    logger.debug("Unmatched response (seq=%d, type=0x%02X)", seq, response_type)

        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Read loop error: %s", exc)
        finally:
            # Fail all pending futures so callers don't hang
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(ConnectionError("TPI connection lost"))
            self._pending.clear()

    async def _send_frame_once(self, frame: bytes, seq: int) -> TPIResponse:
        """Write a frame to the socket and await the matching response."""
        if self._writer is None:
            raise ConnectionError("Not connected to TPI")

        loop = asyncio.get_event_loop()
        fut: asyncio.Future[TPIResponse] = loop.create_future()
        self._pending[seq] = fut

        logger.debug("→ frame seq=%d: %s", seq, frame.hex())
        self._writer.write(frame)
        await self._writer.drain()

        try:
            return await asyncio.wait_for(fut, timeout=self._timeout)
        except TimeoutError as exc:
            self._pending.pop(seq, None)
            raise TimeoutError(f"TPI response timeout for seq={seq}") from exc
        except Exception:
            self._pending.pop(seq, None)
            raise

    async def _send_frame(self, frame: bytes, seq: int) -> TPIResponse:
        """Write a frame, reconnecting only before a request is sent."""
        async with self._send_lock:
            await self._ensure_connected()
            try:
                return await self._send_frame_once(frame, seq)
            except (ConnectionError, OSError, TimeoutError):
                if self._auto_reconnect:
                    async with self._connect_lock:
                        await self._close_unlocked()
                raise

    async def send_basic(
        self,
        command: int,
        address: int,
        data_hi: int = 0x00,
        data_mid: int = 0x00,
        data_lo: int = 0x00,
    ) -> TPIResponse:
        """Send a basic 8-byte TPI command and return the response.

        Args:
            command: Command byte (see TPI Advanced command table).
            address: DALI address byte.
            data_hi: High data byte (default 0x00).
            data_mid: Mid data byte (default 0x00).
            data_lo: Low data byte (default 0x00).
        """
        seq = await self._next_seq()
        frame = build_basic_frame(seq, command, address, data_hi, data_mid, data_lo)
        return await self._send_frame(frame, seq)

    async def send_dali_colour(
        self,
        address: int,
        arc_level: int,
        colour_type: int,
        colour_data: bytes,
    ) -> TPIResponse:
        """Send a DALI Colour command.

        Args:
            address: DALI address byte.
            arc_level: Arc level (0–254). Use 0xFF for colour-only fade.
            colour_type: 0x10=XY, 0x20=Tc, 0x80=RGBWAF.
            colour_data: 7 colour channel bytes (pad unused with 0xFF).
        """
        seq = await self._next_seq()
        frame = build_dali_colour_frame(seq, address, arc_level, colour_type, colour_data)
        return await self._send_frame(frame, seq)

    async def send_dmx_colour(
        self,
        fade_id: int,
        universe_mask: int,
        start_channel: int,
        stop_channel: int,
        address_divisor: int,
        block_mode: int,
        personality_type: int,
        fade_mode: int,
        fade_time_ms: int,
        fade_type_a: int,
        fade_type_b: int,
        levels: list[int],
    ) -> TPIResponse:
        """Send a DMX Colour command."""
        seq = await self._next_seq()
        frame = build_dmx_colour_frame(
            seq,
            fade_id,
            universe_mask,
            start_channel,
            stop_channel,
            address_divisor,
            block_mode,
            personality_type,
            fade_mode,
            fade_time_ms,
            fade_type_a,
            fade_type_b,
            levels,
        )
        return await self._send_frame(frame, seq)

    async def send_dynamic(self, command: int, data: bytes) -> TPIResponse:
        """Send a dynamic subframe command.

        Args:
            command: Command byte.
            data: Variable-length data bytes.
        """
        seq = await self._next_seq()
        frame = build_dynamic_frame(seq, command, data)
        return await self._send_frame(frame, seq)

    async def check_startup_complete(self) -> bool:
        """Return True if the controller startup sequence is complete."""
        response = await self.send_basic(
            command=_CMD_QUERY_CONTROLLER_STARTUP_COMPLETE, address=0x00
        )
        # ANSWER with data[0] non-zero = complete; NO_ANSWER or data[0] == 0 = not ready
        if response.is_answer and response.data:
            return response.data[0] != 0
        return False

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    @property
    def is_connected(self) -> bool:
        return self._has_active_connection()
