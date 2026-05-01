"""Tests for binary framing helpers.

Test values verified against examples in the TPI Advanced documentation.
"""

import pytest

from zencontrol_tpi_mcp.api.framing import (
    RESPONSE_ANSWER,
    RESPONSE_ERROR,
    RESPONSE_NO_ANSWER,
    RESPONSE_OK,
    FrameError,
    TPIResponse,
    build_basic_frame,
    build_dali_colour_frame,
    build_dynamic_frame,
    crc8,
    parse_response_body,
    parse_response_header,
    validate_checksum,
)


class TestCRC8:
    def test_doc_example(self):
        # From TPI doc: checksum = 0x04 ^ 0x00 ^ 0x01 ^ 0x0A ^ 0x00 ^ 0x00 ^ 0x00 = 0x0F
        data = bytes([0x04, 0x00, 0x01, 0x0A, 0x00, 0x00, 0x00])
        assert crc8(data) == 0x0F

    def test_empty(self):
        assert crc8(b"") == 0

    def test_single_byte(self):
        assert crc8(bytes([0xAB])) == 0xAB

    def test_xor_self_cancels(self):
        assert crc8(bytes([0x55, 0x55])) == 0


class TestValidateChecksum:
    def test_valid_frame(self):
        # QUERY_GROUP_LABEL request from doc: [0x04,0x00,0x01,0x0A,0x00,0x00,0x00,0x0F]
        frame = bytes([0x04, 0x00, 0x01, 0x0A, 0x00, 0x00, 0x00, 0x0F])
        validate_checksum(frame)  # should not raise

    def test_invalid_checksum(self):
        frame = bytes([0x04, 0x00, 0x01, 0x0A, 0x00, 0x00, 0x00, 0xFF])
        with pytest.raises(FrameError, match="Checksum mismatch"):
            validate_checksum(frame)

    def test_empty_frame(self):
        with pytest.raises(FrameError, match="Empty frame"):
            validate_checksum(b"")


class TestBuildBasicFrame:
    def test_query_group_label_example(self):
        # From TPI doc: QUERY_GROUP_LABEL (0x01) for group 10 (0x0A)
        # Request: [0x04, 0x00, 0x01, 0x0A, 0x00, 0x00, 0x00, 0x0F]
        frame = build_basic_frame(seq=0x00, command=0x01, address=0x0A)
        assert frame == bytes([0x04, 0x00, 0x01, 0x0A, 0x00, 0x00, 0x00, 0x0F])

    def test_frame_length_always_8(self):
        frame = build_basic_frame(seq=0, command=0xA2, address=1)
        assert len(frame) == 8

    def test_checksum_valid(self):
        frame = build_basic_frame(seq=0xBE, command=0xAA, address=0x05)
        validate_checksum(frame)

    def test_control_byte_is_0x04(self):
        frame = build_basic_frame(seq=0, command=0, address=0)
        assert frame[0] == 0x04

    def test_data_bytes_included(self):
        frame = build_basic_frame(
            seq=0, command=0xA0, address=64, data_hi=0x01, data_mid=0x02, data_lo=0x03
        )
        assert frame[4] == 0x01
        assert frame[5] == 0x02
        assert frame[6] == 0x03
        validate_checksum(frame)

    def test_seq_in_position_1(self):
        frame = build_basic_frame(seq=0x42, command=0x01, address=0x00)
        assert frame[1] == 0x42

    def test_command_in_position_2(self):
        frame = build_basic_frame(seq=0x00, command=0xA9, address=0x00)
        assert frame[2] == 0xA9


class TestBuildDALIColourFrame:
    def test_rgbwaf_colour_checksum_valid(self):
        # Set RGBWAF (red only) on address 1
        colour_data = bytes([0xFF, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF])  # Red only, 7 bytes
        frame = build_dali_colour_frame(
            seq=0x00,
            address=0x01,
            arc_level=0xFF,  # colour-only fade
            colour_type=0x80,  # RGBWAF
            colour_data=colour_data,
        )
        assert frame[0] == 0x04
        assert frame[2] == 0x0E  # DALI_COLOUR command
        assert frame[3] == 0x01  # address
        assert frame[4] == 0xFF  # arc_level
        assert frame[5] == 0x80  # colour_type RGBWAF
        validate_checksum(frame)

    def test_tc_colour_frame(self):
        # Set Tc = 4000K
        tc_bytes = (4000).to_bytes(2, "big")
        colour_data = tc_bytes + bytes([0xFF] * 5)  # pad to 7 bytes
        frame = build_dali_colour_frame(
            seq=0x01,
            address=0x00,
            arc_level=0x80,
            colour_type=0x20,  # Tc
            colour_data=colour_data,
        )
        validate_checksum(frame)
        assert frame[5] == 0x20

    def test_xy_colour_frame(self):
        # Set XY colour x=0.3, y=0.3 (approx 0x4CCC, 0x4CCC)
        x = int(0.3 * 0xFFFE)
        y = int(0.3 * 0xFFFE)
        colour_data = x.to_bytes(2, "big") + y.to_bytes(2, "big") + bytes([0xFF] * 3)
        frame = build_dali_colour_frame(
            seq=0x02,
            address=0x40,  # group 0
            arc_level=0xFF,
            colour_type=0x10,  # XY
            colour_data=colour_data,
        )
        validate_checksum(frame)


class TestBuildDynamicFrame:
    def test_basic_structure(self):
        data = bytes([0x01, 0x02, 0x03])
        frame = build_dynamic_frame(seq=0x00, command=0x40, data=data)
        assert frame[0] == 0x04
        assert frame[1] == 0x00  # seq
        assert frame[2] == 0x40  # command
        assert frame[3] == 0x03  # data length
        assert frame[4:7] == data
        validate_checksum(frame)

    def test_empty_data(self):
        frame = build_dynamic_frame(seq=0x00, command=0x42, data=b"")
        assert frame[3] == 0x00
        validate_checksum(frame)


class TestParseResponseHeader:
    def test_basic_parse(self):
        header = bytes([0xA1, 0x00, 0x03])
        rt, seq, dl = parse_response_header(header)
        assert rt == RESPONSE_ANSWER
        assert seq == 0x00
        assert dl == 3

    def test_wrong_length(self):
        with pytest.raises(FrameError):
            parse_response_header(bytes([0xA0, 0x00]))


class TestParseResponseBody:
    def test_query_group_label_answer(self):
        # From TPI doc: label "Foo" for group 10
        # Response: [0xA1, 0x00, 0x03, 0x46, 0x6F, 0x6F, 0xE4]
        header = bytes([0xA1, 0x00, 0x03])
        body = bytes([0x46, 0x6F, 0x6F, 0xE4])  # "Foo" + checksum
        response = parse_response_body(header, body)
        assert response.is_answer
        assert response.seq == 0x00
        assert response.data == b"Foo"

    def test_no_answer_response(self):
        # No-label response: [0xA2, 0x00, 0x00, 0xA2]
        header = bytes([0xA2, 0x00, 0x00])
        body = bytes([0xA2])  # checksum only (data_length = 0)
        response = parse_response_body(header, body)
        assert response.is_no_answer
        assert response.data == b""

    def test_ok_response(self):
        header = bytes([0xA0, 0x05, 0x00])
        # checksum = 0xA0 ^ 0x05 ^ 0x00 = 0xA5
        checksum = crc8(header)
        body = bytes([checksum])
        response = parse_response_body(header, body)
        assert response.is_ok
        assert response.seq == 0x05
        assert response.data == b""

    def test_error_response_with_code(self):
        # ERROR with error code 0x01 (ERROR_CHECKSUM)
        header = bytes([0xA3, 0x00, 0x01])
        data = bytes([0x01])  # error code
        checksum = crc8(header + data)
        body = data + bytes([checksum])
        response = parse_response_body(header, body)
        assert response.is_error
        assert response.error_code == 0x01

    def test_body_length_mismatch(self):
        header = bytes([0xA1, 0x00, 0x05])  # claims 5 data bytes
        body = bytes([0x01, 0x02, 0xFF])  # only 2 data + checksum
        with pytest.raises(FrameError, match="length mismatch"):
            parse_response_body(header, body)

    def test_bad_checksum(self):
        header = bytes([0xA1, 0x00, 0x01])
        body = bytes([0xAB, 0xFF])  # wrong checksum
        with pytest.raises(FrameError, match="Checksum mismatch"):
            parse_response_body(header, body)


class TestTPIResponse:
    def test_is_ok(self):
        r = TPIResponse(RESPONSE_OK, 0, b"")
        assert r.is_ok
        assert not r.is_error

    def test_is_answer(self):
        r = TPIResponse(RESPONSE_ANSWER, 0, b"data")
        assert r.is_answer
        assert not r.is_no_answer

    def test_is_no_answer(self):
        r = TPIResponse(RESPONSE_NO_ANSWER, 0, b"")
        assert r.is_no_answer

    def test_error_code_present(self):
        r = TPIResponse(RESPONSE_ERROR, 0, bytes([0xB1]))
        assert r.is_error
        assert r.error_code == 0xB1

    def test_error_code_absent_when_not_error(self):
        r = TPIResponse(RESPONSE_ANSWER, 0, bytes([0x01]))
        assert r.error_code is None

    def test_repr(self):
        r = TPIResponse(RESPONSE_ANSWER, 5, b"AB")
        assert "ANSWER" in repr(r)
        assert "seq=5" in repr(r)
