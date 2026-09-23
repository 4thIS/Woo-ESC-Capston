"""rx 프레임 → STATUS/HELLO 업링크 행. 올리는 것은 링크(wj) (S6 spec §4.5, v2 §8.5).

행 body 는 링크가 `{"t": "uplink", **body}` 로 그대로 메인에 보내고 메인 `api.on_uplink` 가 읽는다.
키 이름·값 타입은 로드맵 §4.2 인코딩 규칙을 따른다 — codec `Ack` 필드명 그대로 평탄화
(`status, detail, …`), STATUS 는 `rssi_last, snr_last_x4, flags, uptime_h` 추가, `rssi`/`snr` 은
모뎀이 잰 이 업링크 프레임의 링크 값이다(노드가 잰 마지막 다운링크 값은 `rssi_last`/`snr_last_x4`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable

from lora_proto import codec as C
from lora_proto import proto as P

from modempi.lora.modem_client import ModemClient, RxEvent
from modempi.store import SqliteStore

log = logging.getLogger("lora.uplink")


def _is_letter(b: int) -> bool:
    """메인은 bld 를 `[A-Za-z]` 한 글자로 받는다(server/app/schemas.py)."""
    return 0x41 <= b <= 0x5A or 0x61 <= b <= 0x7A


def _type_name(t: int) -> str:
    try:
        return P.Type(t).name
    except ValueError:
        return f"{t:#x}"


class UplinkReader:
    """`client.rx` 의 비요청 프레임을 STATUS/HELLO 업링크 행으로 바꾼다. 보내는 쪽 결정은 하지 않는다 —
    단 CLOCK_STALE 노드에는 타겟 TIME 행 하나를 넣는다(v2 §8.5)."""

    def __init__(
        self,
        store: SqliteStore,
        client: ModemClient | None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.store, self.client, self._clock = store, client, clock

    async def run(self, stop: asyncio.Event) -> None:
        """`rx` 를 소비한다. 한 건 처리가 무엇으로 실패하든 로그만 남기고 다음 건으로 간다.
        `stop` 은 한 건을 받은 뒤에만 본다 — 곧바로 끊으려면 호출자가 태스크를 cancel 한다."""
        assert self.client is not None
        while not stop.is_set():
            ev = await self.client.rx.get()
            try:
                self.handle(ev)
            except Exception:
                log.exception("업링크 처리 실패 — 버리고 계속")

    def handle(self, ev: RxEvent) -> str | None:
        """넣은 업링크 행의 kind(`"STATUS"`/`"HELLO"`), 버렸으면 None.
        프레임·페이로드 해석 실패(CRC·NET_ID·길이)는 경고 로그 후 버린다 — 예외를 내지 않는다."""
        try:
            h, pb = C.decode_frame(ev.frame)
            obj = C.decode_payload(h.type, pb)
        except C.FrameError as e:
            log.warning("업링크 프레임 버림: %s (rssi=%s snr=%s)", e, ev.rssi, ev.snr)
            return None
        if h.type == P.Type.STATUS:
            return self._status(h, obj, ev)
        if h.type == P.Type.HELLO:
            self._hello(obj, ev)
            return "HELLO"
        # 대개 늦게 온 ACK(워커가 이미 no_ack 로 판정한 뒤) — 결과는 워커의 몫이라 로그만 (v2 §8.5)
        log.info(
            "요청하지 않은 %s 프레임 — 무시 (%s%d#%d txn=%d)",
            _type_name(h.type),
            chr(h.bld) if _is_letter(h.bld) else f"{h.bld:#x}",
            h.room,
            h.unit,
            h.txn,
        )
        return None

    def _hello(self, hello: C.Hello, ev: RxEvent) -> None:
        # 미설정 노드 — 주소는 계약 ⑥ 대로 정수 0, MAC 은 소문자 hex 12자(bytes 는 JSON 불가)
        self.store.put_uplink(
            {
                "kind": "HELLO",
                "bld": 0,
                "room": 0,
                "unit": 0,
                "mac": hello.mac.hex(),
                "fw": hello.fw,
                "batt_mv": hello.batt_mv,
                "rssi": ev.rssi,
                "snr": ev.snr,
            }
        )

    def _status(self, h: C.Header, st: C.Status, ev: RxEvent) -> str | None:
        if not _is_letter(h.bld):
            log.warning("STATUS 의 bld=%#x 는 건물 문자가 아님 — 버림", h.bld)
            return None
        bld = chr(h.bld)
        a = st.ack
        self.store.put_uplink(
            {
                "kind": "STATUS",
                "bld": bld,
                "room": h.room,
                "unit": h.unit,
                "mac": None,
                "status": int(a.status),
                "detail": a.detail,
                "batt_mv": a.batt_mv,
                "sched_ver": a.sched_ver,
                "resv_ver": a.resv_ver,
                "exam_ver": a.exam_ver,
                "ident_ver": a.ident_ver,
                "fw": a.fw,
                "layout": int(a.layout),
                "rssi_last": st.rssi_last,
                "snr_last_x4": st.snr_last_x4,
                "flags": st.flags,
                "uptime_h": st.uptime_h,
                "rssi": ev.rssi,
                "snr": ev.snr,
            }
        )
        if st.flags & int(P.StatusFlag.CLOCK_STALE):
            self._queue_time(bld, h.room, h.unit)
        return "STATUS"

    def _queue_time(self, bld: str, room: int, unit: int) -> None:
        """그 노드에만 TIME 1건(브로드캐스트 아님). 워커가 txn=0·ack_ms=0 으로 보내고 노드는 TIME 을
        DUP 검사하지 않으므로 노드 TXN 을 건드리지 않는다. job_id 는 노드·초 단위로 고정 — 같은 초에
        STATUS 가 두 번 와도 `put_job` 이 중복 job_id 를 무시해 한 행만 남는다. 시계를 못 믿는 동안은
        워커가 송신을 미루고, epoch 는 워커가 보낼 때 지금 시각으로 다시 채운다(preprocess)."""
        epoch = int(self._clock())
        job_id = f"time-{epoch}-{bld}{room}-{unit}"
        if self.store.put_job(
            job_id=job_id,
            bld=bld,
            room=room,
            unit=unit,
            type="TIME",
            payload=json.dumps({"epoch": epoch, "flags": 0}),
            priority=0,
            new_ver=None,
            uploaded=1,  # 메인은 TIME 결과에 관심 없음 (S6 §4.4)
        ):
            log.info("CLOCK_STALE %s%d#%d — 타겟 TIME %s 큐잉", bld, room, unit, job_id)
