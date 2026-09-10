from lora_proto import proto as P


def test_header_constants_match_spec_3_1():
    assert P.PROTO_VER == 2
    assert P.HEADER_LEN == 9
    assert P.MAX_FRAME == 255
    assert P.MAX_PAYLOAD == 245
    assert P.FILE_CHUNK_MAX == 200
    assert (P.FLAG_ACK_REQ, P.FLAG_BROADCAST, P.FLAG_WAKE_SENT) == (0x01, 0x02, 0x04)


def test_type_codes_match_spec_3_2():
    assert P.Type.TIME == 0x01
    assert P.Type.SET_ROOM == 0x0D
    assert P.Type.ACK == 0x10
    assert P.Type.STATUS == 0x11
    assert P.Type.HELLO == 0x12
    assert len(P.Type) == 16


def test_ack_status_and_cmd_match_spec_3_3_3_4():
    assert P.AckStatus.GAP == 0x04
    assert P.AckStatus.DUP == 0x08
    assert P.Cmd.FORCE_RENDER == 0x06
    assert P.SlotType.RENTAL == 6
    assert P.Layout.SETUP == 8
    assert P.FileKind.EXAM == 3


def test_radio_params_match_spec_2():
    assert P.RADIO["RP_NET_ID"] == 0x4B
    assert P.RADIO["RP_SF"] == 9
    assert P.RADIO["RP_PREAMBLE_WAKE_MS"] == 3000
    assert P.RADIO["RP_FREQ_MHZ"] == 922.5
