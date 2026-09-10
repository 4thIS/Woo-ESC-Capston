#ifndef LORA_PROTO_RADIO_PARAMS_H
#define LORA_PROTO_RADIO_PARAMS_H
// v2 스펙 §2 원본. 바꾸면 lora_proto/proto.py RADIO 와 test_vectors.json 을 같은 커밋에서 갱신한다.
#define RP_FREQ_MHZ          922.5f
#define RP_BW_KHZ            125.0f
#define RP_SF                9
#define RP_CR                5
#define RP_SYNC_WORD         0x12
#define RP_TX_POWER_DBM      14
#define RP_PREAMBLE_NORMAL   8
#define RP_PREAMBLE_WAKE_MS  3000
#define RP_RX_DUTY_MIN_SYM   8
#define RP_CAD_MAX_TRIES     5
#define RP_CAD_BACKOFF_MIN_MS 50
#define RP_CAD_BACKOFF_MAX_MS 200
#define RP_HW_CRC            1
#define RP_NET_ID            0x4B
#endif
