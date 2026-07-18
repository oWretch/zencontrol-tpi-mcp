"""Tests for the ZenControl TPI async TCP client."""

from __future__ import annotations

import asyncio

import pytest

from zencontrol_tpi_mcp.api.client import ZenControlTPI
from zencontrol_tpi_mcp.api.framing import (
    RESPONSE_ANSWER,
    RESPONSE_NO_ANSWER,
    RESPONSE_OK,
    build_basic_frame,
    crc8,
)


def _make_response(response_type: int, seq: int, data: bytes = b"") -> bytes:
    """Build a valid TPI response byte string."""
    header = bytes([response_type, seq, len(data)])
    checksum = crc8(header + data)
    return header + data + bytes([checksum])


class FakeStreamReader:
    """Feed-based asyncio.StreamReader fake."""

    def __init__(self, data: bytes = b"") -> None:
        self._buffer = bytearray(data)
        self._closed = False

    def feed(self, data: bytes) -> None:
        self._buffer.extend(data)

    def close(self) -> None:
        self._closed = True

    async def readexactly(self, n: int) -> bytes:
        while len(self._buffer) < n:
            if self._closed:
                raise asyncio.IncompleteReadError(bytes(self._buffer), n)
            await asyncio.sleep(0)
        result = bytes(self._buffer[:n])
        del self._buffer[:n]
        return result


class FakeStreamWriter:
    """asyncio.StreamWriter fake that captures written bytes."""

    def __init__(self) -> None:
        self.written: bytearray = bytearray()
        self._closed = False

    def write(self, data: bytes) -> None:
        self.written.extend(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        pass

    def is_closing(self) -> bool:
        return self._closed


async def _make_client_with_streams(reader: FakeStreamReader, writer: FakeStreamWriter) -> ZenControlTPI:
    """Create a ZenControlTPI client pre-wired with fake streams."""
    client = ZenControlTPI(host="127.0.0.1", port=5108)
    client._reader = reader  # type: ignore[assignment]
    client._writer = writer  # type: ignore[assignment]
    client._read_task = asyncio.create_task(client._read_loop(), name="tpi-read-loop")
    return client


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class TestSequenceCounter:
    async def test_increments(self):
        client = ZenControlTPI("127.0.0.1")
        s1 = await client._next_seq()
        s2 = await client._next_seq()
        s3 = await client._next_seq()
        assert s1 == 0
        assert s2 == 1
        assert s3 == 2

    async def test_wraps_at_256(self):
        client = ZenControlTPI("127.0.0.1")
        client._seq = 255
        s = await client._next_seq()
        assert s == 255
        s2 = await client._next_seq()
        assert s2 == 0


class TestSendBasic:
    async def test_sends_correct_frame(self):
        reader = FakeStreamReader()
        writer = FakeStreamWriter()
        client = await _make_client_with_streams(reader, writer)

        # Schedule a response
        async def feed_response():
            await asyncio.sleep(0.01)
            reader.feed(_make_response(RESPONSE_OK, seq=0))

        asyncio.create_task(feed_response())

        response = await client.send_basic(command=0x01, address=0x0A)
        await client.close()

        # Verify the frame written: should be QUERY_GROUP_LABEL for group 10
        expected_frame = build_basic_frame(seq=0, command=0x01, address=0x0A)
        assert bytes(writer.written) == expected_frame
        assert response.is_ok

    async def test_returns_answer_with_data(self):
        reader = FakeStreamReader()
        writer = FakeStreamWriter()
        client = await _make_client_with_streams(reader, writer)

        async def feed_response():
            await asyncio.sleep(0.01)
            reader.feed(_make_response(RESPONSE_ANSWER, seq=0, data=b"Office"))

        asyncio.create_task(feed_response())

        response = await client.send_basic(command=0x01, address=0x00)
        await client.close()

        assert response.is_answer
        assert response.data == b"Office"

    async def test_concurrent_requests_are_serialized(self):
        reader = FakeStreamReader()
        writer = FakeStreamWriter()
        client = await _make_client_with_streams(reader, writer)

        # Concurrent callers are serialized onto one TCP stream.
        async def feed_responses():
            await asyncio.sleep(0.02)
            reader.feed(_make_response(RESPONSE_ANSWER, seq=0, data=b"A"))
            await asyncio.sleep(0.01)
            reader.feed(_make_response(RESPONSE_ANSWER, seq=1, data=b"B"))

        asyncio.create_task(feed_responses())

        r0, r1 = await asyncio.gather(
            client.send_basic(command=0x01, address=0x00),
            client.send_basic(command=0x01, address=0x01),
        )
        await client.close()

        assert r0.data == b"A"
        assert r1.data == b"B"

    async def test_timeout_raises(self):
        reader = FakeStreamReader()
        writer = FakeStreamWriter()
        client = await _make_client_with_streams(reader, writer)
        client._timeout = 0.05  # very short timeout

        with pytest.raises(TimeoutError):
            await client.send_basic(command=0x01, address=0x00)

        await client.close()


class TestReadLoopDisconnect:
    async def test_connection_lost_fails_pending(self):
        reader = FakeStreamReader()
        writer = FakeStreamWriter()
        client = await _make_client_with_streams(reader, writer)
        client._timeout = 5.0

        # Start a request that will never get a response
        request_task = asyncio.create_task(client.send_basic(command=0x01, address=0x00))
        await asyncio.sleep(0.01)

        # Simulate disconnect by closing the reader
        reader.close()
        await asyncio.sleep(0.05)

        with pytest.raises((ConnectionError, TimeoutError)):
            await request_task

        await client.close()


class TestCheckStartupComplete:
    async def test_returns_true_when_answer_nonzero(self):
        reader = FakeStreamReader()
        writer = FakeStreamWriter()
        client = await _make_client_with_streams(reader, writer)

        async def feed():
            await asyncio.sleep(0.01)
            reader.feed(_make_response(RESPONSE_ANSWER, seq=0, data=bytes([0x01])))

        asyncio.create_task(feed())
        result = await client.check_startup_complete()
        await client.close()
        assert result is True

    async def test_returns_false_when_no_answer(self):
        reader = FakeStreamReader()
        writer = FakeStreamWriter()
        client = await _make_client_with_streams(reader, writer)

        async def feed():
            await asyncio.sleep(0.01)
            reader.feed(_make_response(RESPONSE_NO_ANSWER, seq=0))

        asyncio.create_task(feed())
        result = await client.check_startup_complete()
        await client.close()
        assert result is False


class TestIsConnected:
    async def test_connected_after_streams_set(self):
        reader = FakeStreamReader()
        writer = FakeStreamWriter()
        client = await _make_client_with_streams(reader, writer)
        assert client.is_connected
        await client.close()

    async def test_not_connected_initially(self):
        client = ZenControlTPI("127.0.0.1")
        assert not client.is_connected
