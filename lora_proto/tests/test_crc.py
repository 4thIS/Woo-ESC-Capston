from lora_proto.codec import crc8, crc16_ccitt


def test_crc8_poly07_known_vectors():
    # CRC-8 (poly 0x07, init 0x00, no reflect, xorout 0) 표준 check 값
    assert crc8(b"123456789") == 0xF4
    assert crc8(b"") == 0x00
    assert crc8(b"\x00") == 0x00
    assert crc8(b"\x01") == 0x07


def test_crc16_ccitt_false_known_vectors():
    assert crc16_ccitt(b"123456789") == 0x29B1
    assert crc16_ccitt(b"") == 0xFFFF
