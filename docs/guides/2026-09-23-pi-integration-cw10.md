# Pi↔Pi 통합 가이드 (cw-10 · wj-08)

- 작성: 2026-09-23 · cw
- 목표(진행표 cw-10 DoD): **메인Pi에서 저장 → 모뎀Pi(가짜 모뎀)로 전달 → 결과가 메인Pi에 `acked`로 돌아온다.** "끊고 붙이기"도 통과. 결과를 PR에 첨부.
- 부품(Heltec·e-Paper)은 필요 없다. 모뎀Pi는 `--fake`(가짜 모뎀)로 돈다. 실물 모뎀은 S7 이후 `--port`로 바꾸기만 하면 된다.
- 근거: 로드맵 §4.2(계약 ⑥)·§4.3(계약 ⑦), `server/README.md`, S6 spec §3·§4.6, S5 spec §4.4.

---

## 0. 준비물 (시작 전 10분)

| 항목 | 확인 |
|---|---|
| Raspberry Pi 2대 + 전원 어댑터 + microSD 2장(16 GB 이상) | 64비트 지원 모델(Pi 3B+/4/5) |
| 두 Pi와 노트북이 **같은 네트워크**(같은 Wi-Fi 또는 공유기) | 인터넷도 되는 곳이 편하다 — 시각 동기(NTP)·패키지 설치 때문 |
| 노트북에 Raspberry Pi Imager | https://www.raspberrypi.com/software/ |
| GitHub 접근 | 리포가 **비공개**라 Pi에서 clone하려면 인증이 필요하다(아래 §2-4) |

이 문서의 이름(팀 확정, 2026-09-23): 메인Pi 호스트명 **`ESC-main`**, 모뎀Pi 호스트명 **`ESC-modem`**, 두 Pi 모두 사용자 **`admin`**. 접속 주소는 `ESC-main.local` / `ESC-modem.local`(mDNS 는 대소문자를 가리지 않는다).

---

## 1. OS 굽기 (Pi마다 1회, 약 15분)

Raspberry Pi Imager에서:
1. **OS**: Raspberry Pi OS **Lite (64-bit)** — 화면이 필요 없다.
2. **설정(톱니바퀴 / "설정 편집")**:
   - 호스트 이름: `ESC-main` / `ESC-modem`
   - 사용자: `admin` + 비밀번호 (두 Pi 같은 이름)
   - Wi-Fi: SSID·비밀번호, 국가 `KR`
   - 로캘: 시간대 `Asia/Seoul`
   - **서비스 → SSH 사용** 체크
3. 굽고 Pi에 꽂아 부팅(첫 부팅 1~2분).

노트북에서 접속 확인:
```bash
ssh admin@ESC-main.local
ssh admin@ESC-modem.local
```
`.local`로 안 되면 공유기 관리 페이지에서 IP를 찾아 `ssh admin@192.168.x.x`.

---

## 2. 두 Pi 공통 설정 (Pi마다, 약 15분)

```bash
# 2-1. 업데이트 + git
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y git

# 2-2. 시계 — 모뎀Pi 는 NTP 동기가 확인돼야 TIME 을 방송한다(S6 spec §3)
timedatectl status                 # "System clock synchronized: yes" 가 떠야 한다
ls /run/systemd/timesync/synchronized   # 파일이 있어야 한다 (모뎀Pi 의 시계 신뢰 기준)

# 2-3. uv (Python 3.12 는 uv 가 알아서 받는다 — OS 기본 3.11 은 안 씀)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version
```

**2-4. 리포 받기 (비공개 리포 인증)** — 둘 중 하나:
```bash
# (가) SSH 키 — Pi 에서 키를 만들고 GitHub 계정 Settings → SSH keys 에 공개키를 등록
ssh-keygen -t ed25519 -C "admin@$(hostname)" -N "" -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub          # 이 한 줄을 GitHub 에 붙여 넣는다
git clone git@github.com:4thIS/Woo-ESC-Capston.git ~/Woo-ESC-Capston

# (나) gh CLI
sudo apt install -y gh && gh auth login   # 브라우저 코드 인증
gh repo clone 4thIS/Woo-ESC-Capston ~/Woo-ESC-Capston
```
Pi 에서는 **`main` 만 받는다**(작업 브랜치 체크아웃 금지 — Pi 는 배포 대상이다).

---

## 3. 메인Pi — 서버 띄우기: Docker (약 15분)

> **2026-09-23 팀 결정: 메인Pi 서버는 Docker(Compose)로 돌린다.** 모뎀Pi 는 Docker 를 쓰지 않는다(USB 시리얼·시계 동기 상태에 직접 붙어야 해서 §8 의 systemd). 이미지는 amd64(노트북)·arm64(Pi) 둘 다 빌드된다.

```bash
ssh admin@ESC-main.local

# 3-1. Docker 설치 (1회) — 공식 설치 스크립트
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker admin
exit                                   # 그룹 반영을 위해 한 번 나갔다가
ssh admin@ESC-main.local               # 다시 접속
docker run --rm hello-world            # "Hello from Docker!" 가 나오면 OK

# 3-2. 서버 설정 파일 server/.env (1회) — 비밀값이라 커밋하지 않고 이미지에도 안 들어간다
cd ~/Woo-ESC-Capston
git pull
cp server/.env.example server/.env
nano server/.env
#   JWT_SECRET=<아래 명령 출력 — 32자 이상>     python3 -c "import secrets;print(secrets.token_urlsafe(48))"
#   STUDENT_WEB_URL=http://ESC-main.local:5173   (학생 웹 주소 — 아직 없으니 이 값으로 둔다)
#   MAIL_BACKEND=console                         (통합 단계는 메일을 로그로 — SMTP 불필요)
#   DEBUG=1                                      (통신 확인 페이지·/docs 를 연다. 운영(S11)에서는 0)
chmod 600 server/.env

# 3-3. 서버 빌드·기동 — 리포 루트에서 (compose.yaml 이 루트에 있다)
docker compose up -d --build           # 첫 빌드는 Pi 에서 수 분
docker compose ps                      # STATUS 가 "healthy" 가 될 때까지 (약 20 s)
docker compose logs -f server          # 로그 보기 (Ctrl+C 로 빠져나옴 — 서버는 계속 돈다)
```
- DB 는 Docker 볼륨(`woo-esc_server-data`)에 있다. `docker compose down` 해도 남고, **`down -v` 는 DB 까지 지운다** — 쓰지 않는다.
- 코드가 바뀌면: `git pull && docker compose up -d --build`
- 마이그레이션(`alembic upgrade head`)은 컨테이너가 시작할 때마다 자동으로 돈다. 워커는 1 개로 고정돼 있다.
- 서버가 `healthy` 가 안 되고 재시작만 하면 `docker compose logs server` — 대개 `server/.env` 의 필수값(`JWT_SECRET` 32자 이상·`STUDENT_WEB_URL`, `MAIL_BACKEND=console` 이면 `DEBUG=1`)이 빠진 것이다.
- **이미 §3 을 `uv run uvicorn` 으로 해 두었다면**: 그 터미널에서 `Ctrl+C` 로 끄고(포트 8000 을 비워야 한다) 위를 한다. 그 DB(`~/data/main.db`)는 쓰지 않으므로 **§4 데이터 등록을 한 번 더** 한다(5 분).

노트북 브라우저에서 확인:
- http://ESC-main.local:8000/api/health → `{"ok": true}`
- http://ESC-main.local:8000/docs → API 목록 (`DEBUG=1` 일 때만)
- http://ESC-main.local:8000/static/index.html → **"메인Pi — 통신 확인"** 페이지(로그인·모뎀 목록·outbox·시간표 저장 폼, `DEBUG=1` 일 때만). 이 문서의 "대시보드"는 이 페이지다. §4 에서 만든 관리자 계정으로 **먼저 로그인**한다.

아래 §4 는 **노트북(또는 새 SSH 창)** 에서 한다.

---

## 4. 메인Pi — 데이터 등록 (약 10분)

S4a(#42) 이후 `/api/health`·`/api/auth/*` 를 뺀 모든 API 는 **관리자 로그인 토큰**이 필요하다. 학교와 첫 관리자는 **CLI** 로 만든다.

**4-1. 학교·관리자 (메인Pi SSH 에서, 1회)**
```bash
cd ~/Woo-ESC-Capston
# 학교 — net_id 는 75(0x4B, lora_proto 기본값)로. 나중에 실물 ESP노드와 맞추기 위해서다
docker compose exec server python -m app.cli create-school --name 명지전문대 --net-id 75 --email-domain mjc.ac.kr
#   → school id=1 …
# 관리자 — 비밀번호(8자 이상)는 프롬프트로 입력한다(명령줄에 쓰지 않는다)
docker compose exec server python -m app.cli create-admin --school-id 1 --email admin@mjc.ac.kr --name 관리자
```

**4-2. 로그인 → 모뎀·건물·강의실 (노트북 터미널에서, Windows 면 Git Bash)**
```bash
H=http://ESC-main.local:8000
T=$(curl -s -X POST $H/api/auth/login -H 'content-type: application/json' \
      -d '{"email":"admin@mjc.ac.kr","password":"<4-1 의 비밀번호>"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
A="Authorization: Bearer $T"            # 이후 모든 요청에 붙인다 (토큰은 24 시간 유효)

# 모뎀Pi 등록 → 모뎀 토큰 (평문은 이때 한 번만 보인다 — 바로 적어 둔다)
curl -s -X POST $H/api/lora/modems -H "$A" -H 'content-type: application/json' \
     -d '{"modem_id":"mjc-eng"}'
#   → {"modem_id":"mjc-eng","token":"……"}   ← 이 token 을 §5 에서 쓴다 (로그인 토큰과 다르다)

# 건물 — 이 건물을 위 모뎀Pi 가 맡는다
curl -s -X POST $H/api/buildings -H "$A" -H 'content-type: application/json' \
     -d '{"school_id":1,"name":"공학관","bld":"E","modem_id":"mjc-eng"}'

# 강의실 — 이게 모뎀Pi config.nodes 에 들어가야 가짜 모뎀에 가상 노드가 생긴다
curl -s -X POST $H/api/rooms -H "$A" -H 'content-type: application/json' \
     -d '{"building_id":1,"room":301,"units":1}'
```
id 가 1 이 아니면 응답의 `id` 를 다음 명령에 넣는다. `401` 이 나오면 토큰이 없거나 만료된 것 — 로그인부터 다시.

---

## 5. 모뎀Pi — 서비스 띄우기 (약 10분)

```bash
ssh admin@ESC-modem.local
cd ~/Woo-ESC-Capston/modempi
uv sync
mkdir -p ~/data

export MODEMPI_MAIN_URL=ws://ESC-main.local:8000/ws/modem   # 같은 LAN 이라 ws:// (TLS 는 S11)
export MODEMPI_ID=mjc-eng
export MODEMPI_TOKEN=<§4-1 의 token>
export MODEMPI_STORE=~/data/jobs.db

uv run modempi --fake
```
로그에서 보여야 할 것:
1. 링크가 메인Pi 에 접속: `modem mjc-eng: hello (pending_results=0)` — 이 줄 없이 연결 종료·재시도만 반복하면 아래 "막히면" 참고
2. `lora.pipeline INFO 모뎀 cfg 전송: {'sf': 9, 'bw': 125.0, 'cr': 5, 'power': 14, 'freq': 922.5, 'wake_ms': 3000}` — 메인Pi config 를 받아 가짜 모뎀에 무선 설정을 보냈다
3. (시계가 동기돼 있으면) 곧바로 TIME 한 건: `lora.worker INFO job time-… → TIME ALL txn=0 frame=…`

통신 확인 페이지(로그인 후) 또는 `curl -s $H/api/lora/modems -H "$A"` 에서 **`mjc-eng` 가 `"connected": true`**, `modem_fw` 가 `"gw-2.0.0"` 이어야 한다.

---

## 6. 첫 왕복 — 저장 → acked (핵심, 약 5분)

통신 확인 페이지의 시간표 폼으로 저장하거나, 노트북에서:
```bash
curl -s -X PUT $H/api/rooms/1/slots -H "$A" -H 'content-type: application/json' \
     -d '{"day":1,"s_h":9,"s_m":0,"e_h":9,"e_m":50,"type":1,"subject":"자료구조","professor":"김교수"}'
#   → {"outbox_ids":[1]}

curl -s "$H/api/lora/outbox?limit=5" -H "$A"
```
`state` 가 **`queued` → `dispatched` → `acked`** 로 바뀌면 성공(보통 몇 초), `ack_status: 0`(OK). 노드 쪽 버전은 `curl -s $H/api/lora/status -H "$A"` 에서 E301-1 의 `sched_ver: 1` 로 확인한다.

모뎀Pi 로그에는 이렇게 세 줄이 찍힌다(프레임 hex 가 합격 기준의 "모뎀Pi 로그의 프레임"):
```
lora.worker INFO job 1 → SLOT_SET E301-1 txn=1 frame=214b0245012d01…
lora.worker INFO job 1 ← acked OK rssi=-94 snr=6.0
lora.worker INFO job 1 끝: acked
```

> ⚠ **알려진 버그 #43 (서버, 수정 중)** — 모뎀Pi 가 **붙어 있는 동안** 저장하면 요청이 16~20 s 걸리고 결과가 `dispatched` 에서 멈출 수 있다(DB 잠금 교착). 수정 전까지는 **모뎀Pi 를 `Ctrl+C` 로 잠시 끄고 저장 → 다시 켜기**로 확인한다(그 순서면 `acked` 까지 정상 — §7-1 과 같은 흐름). outbox 가 `dispatched` 에서 멈췄다면 이 버그다.

**여기까지 되면 4주차 마일스톤의 핵심은 통과다.** 이 화면(outbox JSON + 두 Pi 로그)을 캡처해 둔다.

---

## 7. 끊고 붙이기 (약 10분)

**7-1. 모뎀Pi 가 잠시 죽었을 때**
1. 모뎀Pi 에서 `Ctrl+C` 로 `modempi` 를 멈춘다.
2. 노트북에서 시간표를 2건 더 저장한다(§6 명령을 `s_h` 만 바꿔서).
3. outbox 는 `queued` 에 머문다(정상 — 받을 모뎀Pi 가 없다).
4. 모뎀Pi 에서 다시 `uv run modempi --fake`.
5. 재접속 즉시 몰아 받아 → 두 건 모두 `acked`.

**7-2. 메인Pi 서버가 재시작됐을 때**
1. 모뎀Pi 는 켜 둔 채 메인Pi 에서 `docker compose restart server`.
2. 모뎀Pi 로그에 재접속(백오프 뒤 `hello`)이 찍히고, 그 사이 못 올린 결과가 있으면 몰아 올린다(`hello.pending_results`).
3. 새로 저장한 시간표도 `acked`.

---

## 8. systemd 로 자동 기동 (약 15분)

지금까지는 터미널에 띄워 확인했다. 전원만 켜면 뜨게 한다.

**8-1. 메인Pi** — 따로 할 것이 없다. `compose.yaml` 의 `restart: unless-stopped` 와 Docker 서비스(설치 스크립트가 부팅 자동 시작으로 등록)가 재부팅 뒤 서버를 다시 띄운다. 확인만 한다:
```bash
systemctl is-enabled docker            # enabled
```

**8-2. 모뎀Pi** — 비밀값은 파일로 분리한다(권한 600).
```bash
sudo tee /etc/modempi.env >/dev/null <<'EOF'
MODEMPI_MAIN_URL=ws://ESC-main.local:8000/ws/modem
MODEMPI_ID=mjc-eng
MODEMPI_TOKEN=<토큰>
MODEMPI_STORE=/home/admin/data/jobs.db
EOF
sudo chmod 600 /etc/modempi.env
```
`/etc/systemd/system/modempi.service`
```ini
[Unit]
Description=Woo-ESC 모뎀Pi (링크 + LoRa 파이프라인)
After=network-online.target time-sync.target
Wants=network-online.target

[Service]
User=admin
WorkingDirectory=/home/admin/Woo-ESC-Capston/modempi
EnvironmentFile=/etc/modempi.env
ExecStart=/home/admin/Woo-ESC-Capston/modempi/.venv/bin/modempi --fake
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
> S7 이후 실물 모뎀: `--fake` 를 `--port /dev/lora-modem` 으로 바꾸고, udev 규칙으로 `/dev/lora-modem` 심볼릭 링크를 만든다(별도 가이드).

**8-3. 켜기 + 재부팅 시험**
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now modempi        # 모뎀Pi
journalctl -u modempi -f                   # 로그 보기 (Ctrl+C 로 빠져나옴)
```
두 Pi 를 `sudo reboot` 하고, 1~2분 뒤 메인Pi 에서 `docker compose ps` 가 healthy, 모뎀Pi 에서 `systemctl status modempi` 가 active 인지 본 다음 §6 을 다시 해서 `acked` 가 나오면 끝.

---

## 9. 기록 · PR

- 캡처: §6·§7 의 outbox JSON, 두 Pi 로그(메인Pi `docker compose logs --since 10m server`, 모뎀Pi `journalctl -u modempi --since "10 min ago"`), 통신 확인 페이지 스크린샷
- 진행표 `docs/progress.html` 의 cw-10·wj-08 체크 + PR 번호
- PR 본문에 위 캡처 첨부 (cw-10 DoD "결과를 PR에 첨부")

---

## 막히면

| 증상 | 확인 |
|---|---|
| `ssh …local` 안 됨 | 공유기에서 IP 확인. 같은 네트워크인지(게스트 Wi-Fi 는 기기끼리 막힌 경우가 많다) |
| 모뎀Pi 로그에 연결 거부·재시도 반복 | 노트북에서 `http://ESC-main.local:8000/api/health` 가 되는지. URL 이 `ws://`, 경로 `/ws/modem`, 포트 8000 |
| 연결 직후 바로 끊김(토큰) | `MODEMPI_ID`·`MODEMPI_TOKEN` 오타. 토큰을 잃어버렸으면 `POST /api/lora/modems/mjc-eng/token` 으로 재발급 |
| `MODEMPI_* 누락` 으로 바로 종료 | env 4개가 모두 있는지(`EnvironmentFile` 경로·권한) |
| outbox 가 계속 `queued` | 모뎀 목록에서 `mjc-eng` 가 `"connected": true` 인지, 건물의 `modem_id` 가 `mjc-eng` 인지 |
| `dispatched` 에서 멈추고 결국 `failed(no_ack)` | 강의실이 등록돼 `config.nodes` 에 들어갔는지(가짜 모뎀은 config 의 노드만 가상으로 만든다). 모뎀Pi 로그의 `job … ← no_ack` 줄로 확인 |
| TIME 이 안 나감(로그에 "시계를 믿을 수 없다") | `timedatectl status` 가 synchronized 인지. 인터넷 없는 직결이면 메인Pi 를 NTP 서버로(S6 spec §3) — 이번 통합의 합격 기준은 아니다 |
| `uv sync`·`docker compose up --build` 가 오래 걸림 | Pi 의 첫 빌드는 수 분 걸릴 수 있다. 정상. 두 번째부터는 캐시로 빠르다 |
| API 가 `401` | 로그인 토큰이 없거나 24 시간이 지났다 — §4-2 로그인부터 다시(`A=…` 도 다시) |
| `/static`·`/docs` 가 `404` | `server/.env` 의 `DEBUG=1` 확인 후 `docker compose up -d` |
| `docker: permission denied` | `usermod -aG docker admin` 뒤 SSH 를 다시 접속했는지 |
| `port is already allocated` (8000) | 예전 `uv run uvicorn` 이 아직 돌고 있다 — 그 터미널에서 `Ctrl+C` |
| outbox 가 `dispatched` 에서 멈춤 | 버그 #43 — §6 의 우회(모뎀Pi 끄고 저장 → 켜기) |
