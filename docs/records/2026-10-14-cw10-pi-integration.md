# cw-10 · wj-08 Pi↔Pi 통합 결과 (실기)

- 일시: 2026-10-14 (KST) · 진행: cw · 가이드: `docs/guides/2026-09-23-pi-integration-cw10.md`
- 결론: **진행표 cw-10 완료 기준 통과** — 메인Pi 웹 저장 → 모뎀Pi(가짜 모뎀) 로그 hex → `job_result` → `acked`, "끊고 붙이기"(모뎀Pi 정지·메인Pi 재시작·두 Pi 재부팅) 통과.

## 1. 구성

| | 메인Pi `ESC-main` | 모뎀Pi `ESC-modem` |
|---|---|---|
| OS | Debian 13 (trixie) aarch64, 4 GB | 같음 |
| 실행 | Docker 29.9 · Compose v5.6 — `esc-server`(:8000)·`esc-web`(:80), `restart: unless-stopped` | systemd `modempi.service`(`--fake`), `EnvironmentFile=/etc/modempi.env`(root 600), `Restart=always` |
| 코드 | `main` 342f714 | `main` 416db75 (uv 0.13) |
| 연결 | 모뎀Pi → `ws://<메인Pi Tailscale IP>:8000/ws/modem` (Tailscale, 같은 LAN 이어도 이 주소) | |

데이터: 학교 1(net_id 75) · 관리자 1 · 모뎀 `mjc-eng` · 건물 `E` 공학관(모뎀 `mjc-eng`) · 강의실 301(유닛 1).

## 2. 결과

| 가이드 | 시험 | 결과 |
|---|---|---|
| §5 | 모뎀Pi 기동 → `hello` · 무선 cfg · TIME | ✅ `hello (pending_results=0)` → `cfg {'sf': 9, 'bw': 125.0, 'cr': 5, 'power': 14, 'freq': 922.5, 'wake_ms': 3000}` → `TIME ALL txn=0` acked |
| §6 | 웹 저장 → `acked` | ✅ outbox 1 `SLOT_SET E301-1` ack OK, rssi −94 / snr 6.0, `terminal_status` `sched_ver 1` `synced` |
| §7-1 | 모뎀Pi 정지 중 2건 저장 → 재기동 | ✅ 재접속 직후 2·3 몰아서 `acked` (`queued` 38 s·13 s 대기 → 전송 1 s) |
| §7-2 | 모뎀Pi 연결 중 `docker compose restart server` | ✅ 1012 종료 → 재시도 2회 → **7 s** 만에 `hello` |
| §7-2 3 | 모뎀Pi **연결 중** 저장(#43 확인) | ✅ 저장 즉시 응답, outbox 7 `queued→dispatched` 70 ms → `acked` **0.94 s**. **#43 은 이 구성에서 재현되지 않음** |
| §8 | 두 Pi `sudo reboot` | ✅ 메인Pi 컨테이너 둘 `healthy`, 모뎀Pi `active` — 첫 접속은 메인Pi 부팅 중이라 시간 초과, **12 s 뒤 재시도에서 `hello`** |

### outbox (메인Pi DB, UTC)

| id | type | ack | new_ver | txn | rssi/snr | created → dispatched → finished |
|---|---|---|---|---|---|---|
| 1 | SLOT_SET | OK | 1 | 1 | −94 / 6.0 | 03:35:42.5 → 03:36:00.1 → 03:36:01.1 (§6, 모뎀Pi 꺼 둔 채 저장) |
| 2 | SLOT_SET | **GAP** | 2 | 2 | −94 / 6.0 | 06:32:08.8 → 06:32:46.4 → 06:32:47.4 (§7-1) |
| 3 | SLOT_SET | OK | 3 | 3 | −92 / 3.8 | 06:32:33.0 → 06:32:46.4 → 06:32:47.4 (§7-1) |
| 4 | FILE | GAP | 3 | 4 (프레임 5~7) | −96 / 2.7 | 06:32:47.4 → 06:32:47.5 → 06:32:48.4 (2 의 GAP 으로 서버가 자동 생성) |
| 5 | SLOT_SET | **GAP** | 4 | 8 | −94 / 6.0 | 06:38:03.1 → 06:38:03.2 → 06:38:04.4 (재부팅 뒤, 연결 중 저장) |
| 6 | FILE | GAP | 4 | 9 (프레임 10~12) | −105 / 6.6 | 06:38:04.4 → 06:38:04.5 → 06:38:05.4 (자동 재동기) |
| 7 | SLOT_SET | OK | 5 | 13 | −96 / 2.7 | 06:38:26.5 → 06:38:26.6 → 06:38:27.5 (연결 중 저장) |

### 모뎀Pi 로그 (§6, 합격 기준의 프레임 hex)

```
lora.worker INFO job 1 → SLOT_SET E301-1 txn=1 frame=214b0245012d01011b010109000a000109ed858cec8aa4ed8ab809ebb095ecb0acec9ab004
lora.worker INFO job 1 ← acked OK rssi=-94 snr=6.0
lora.worker INFO job 1 끝: acked
```

## 3. 관찰 · 후속

1. **GAP → FILE 자동 재동기가 실기에서 동작했다(의도치 않은 확인).** 가짜 모뎀의 가상 노드는 버전을 메모리에만 들고 있어 `modempi` 가 다시 뜰 때마다 0 이 된다 → 다음 SLOT_SET 이 GAP → 서버가 FILE 을 만들어 보내고 `synced` 로 돌아왔다. 실물 노드는 NVS 에 버전을 두므로 재시작으로는 GAP 이 나지 않는다.
2. **FILE_END 도 GAP 으로 응답한다** — 가짜 모뎀이 FILE 에도 `new_ver − old = 1` 검사를 해서, GAP 으로 이미 버전이 맞은 뒤 같은 버전(3→3)으로 오는 FILE 을 GAP 으로 본다. 서버는 FILE 의 GAP 을 재동기 트리거로 쓰지 않아(`api.py` "v2 §3.3 보강 예정") 반복은 없다. **FILE 의 버전 규칙(같거나 앞선 버전이면 OK)을 v2 §3.3 에 정하고 가짜 모뎀·노드(S8)에 반영** — cw 후속.
3. **버그: 서버 config 의 `net_id` 가 `null` 이면 모뎀Pi 서비스가 죽는다.** 건물을 배정하기 전에 모뎀Pi 를 붙이면 서버가 `net_id: null` 을 보낸다(`topology.net_id` 가 건물을 거쳐 학교를 찾음). 모뎀Pi 는 TIME 프레임 인코딩에서 죽고, 다시 켜면 저장된 config 를 읽다 `FakeModem.apply_config` 에서 또 죽는다. → 모뎀Pi(cw): `net_id` 가 없으면 송신을 멈추고 기다리게 방어. 서버(wj): 모뎀의 `school_id` 로 `net_id` 를 주도록 제안.
4. **#43(연결 중 저장 16~20 s·결과 유실)은 이번 구성에서 재현되지 않았다** — 2회 모두 즉시 응답·`acked`. 9/23 이후 서버 변경(#47 S2c 원자화·#53 커밋 순서 등)으로 사라졌을 수 있다. 노트북 재현 조건과 비교해 닫을지 정한다(wj).
5. **가이드 보정** — 이 PR 에 같이 반영: `STUDENT_WEB_URL` 은 웹 컨테이너 주소(`http://ESC-main.local`, :80), Windows PowerShell 에서 `ssh … ~/…` 는 `~` 가 노트북 경로로 바뀌므로 따옴표 안 절대 경로, 모뎀Pi 유닛 `After=` 에 `tailscaled.service`, 부팅 직후 첫 접속 실패는 정상(재시도로 붙음).
