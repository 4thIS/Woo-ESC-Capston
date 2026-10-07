# 메인Pi 원격 접속 가이드 — Tailscale 설치·팀원 공유

- 작성: 2026-09-29 · cw
- 목표: **메인Pi(`ESC-main`)에 학교·집 어디서든 SSH·웹으로 붙는다.** 팀원은 **각자 자기 Tailscale 계정**으로 접속한다.
- 방식: 메인Pi를 cw 의 Tailscale 네트워크(tailnet)에 넣고, 팀원에게는 **기기 공유(Share)** 로 그 한 대만 연다. 팀원을 cw 의 tailnet 에 초대하지 않는다 — 공유받은 사람은 메인Pi 하나만 보이고, cw 의 다른 기기에는 못 간다.
- 포트를 공유기에 열지 않는다. 통신은 Tailscale(WireGuard)로 암호화된다.
- 모뎀Pi(`ESC-modem`)도 같은 절차(§2~§5)를 그대로 따르면 된다. 호스트명만 `esc-modem` 으로.

> **리포는 공개(public)다.** 초대 링크·tailnet 이름·IP·비밀번호를 이 문서나 이슈·PR 에 적지 않는다. 링크는 **개인 메시지로 한 사람에게 하나씩** 보낸다.

---

## 목차

| # | 단계 | 누가 | 시간 |
|---|---|---|---|
| 1 | [준비물](#1-준비물) | 모두 | — |
| 2 | [cw 노트북에 Tailscale 로그인](#2-cw-노트북에-tailscale-로그인) | cw | 3분 |
| 3 | [메인Pi에 Tailscale 설치·로그인](#3-메인pi에-tailscale-설치로그인) | cw | 5분 |
| 4 | [연결 확인](#4-연결-확인) | cw | 2분 |
| 5 | [메인Pi 키 만료 끄기](#5-메인pi-키-만료-끄기) | cw | 1분 |
| 6 | [팀원에게 메인Pi 공유(초대 보내기)](#6-팀원에게-메인pi-공유초대-보내기) | cw | 2분/명 |
| 7 | [팀원: Tailscale 가입·설치](#7-팀원-tailscale-가입설치) | dh·wj·mh | 5분 |
| 8 | [팀원: 초대 수락](#8-팀원-초대-수락) | dh·wj·mh | 1분 |
| 9 | [팀원: SSH 키 만들고 공개키 보내기](#9-팀원-ssh-키-만들고-공개키-보내기) | dh·wj·mh | 2분 |
| 10 | [cw: 팀원 공개키 등록](#10-cw-팀원-공개키-등록) | cw | 1분/명 |
| 11 | [팀원: 접속 확인](#11-팀원-접속-확인) | dh·wj·mh | 2분 |
| 12 | [접근 해제(팀원이 빠질 때)](#12-접근-해제팀원이-빠질-때) | cw | — |
| 13 | [막히면](#13-막히면) | 모두 | — |

---

## 1. 준비물

| 누가 | 필요한 것 |
|---|---|
| cw | 메인Pi 에 SSH 로 붙는 노트북(같은 공유기에서 `ssh admin@ESC-main.local` 이 되는 상태), 메인Pi `admin` 비밀번호(설치에 `sudo` 가 필요), Tailscale 계정(Google·GitHub·Microsoft 로그인이면 된다) |
| 팀원 | 노트북, 자기 Tailscale 계정(§7 에서 만든다), 터미널(Windows 는 PowerShell, macOS 는 터미널) |

- 메인Pi 는 **인터넷이 되는 네트워크**에 붙어 있어야 한다(Tailscale 이 바깥 서버를 통해 길을 찾는다).
- 요금: 무료(Personal) 요금제로 된다. 기기 공유는 모든 요금제에서 쓸 수 있다.

---

## 2. cw 노트북에 Tailscale 로그인

1. https://tailscale.com/download 에서 OS 에 맞는 앱 설치(이미 깔려 있으면 건너뛴다).
2. 트레이(작업 표시줄 오른쪽 아래)의 Tailscale 아이콘 → **Log in** → 브라우저에서 계정 선택.
3. 로그인한 계정을 기억한다 — **§3 에서 메인Pi 도 이 계정으로 승인해야 한다.**
4. 확인 (PowerShell):
   ```powershell
   tailscale status
   ```
   첫 줄에 내 노트북 이름과 `100.x.y.z` 주소가 나오면 된다. `NoState`·`Logged out` 이면 2번을 다시 한다.

---

## 3. 메인Pi에 Tailscale 설치·로그인

노트북 터미널에서 (메인Pi 와 **같은 공유기**에 있을 때 1회):

```bash
ssh -t admin@ESC-main.local
```

접속된 메인Pi 에서:

```bash
# 3-1. 설치 — 공식 스크립트. 부팅 시 자동 시작(systemd tailscaled)까지 등록된다
curl -fsSL https://tailscale.com/install.sh | sh
#   → sudo 비밀번호를 물으면 admin 비밀번호

# 3-2. 로그인 — 이름을 esc-main 으로
sudo tailscale up --hostname=esc-main
#   → "To authenticate, visit: https://login.tailscale.com/a/xxxxxxxx" 가 나온다
```

3-3. 그 주소를 **노트북 브라우저**에 붙여 넣고, §2 와 **같은 계정**으로 로그인 → **Connect**.
Pi 터미널에 `Success.` 가 나오면 끝.

```bash
# 3-4. 부팅 자동 시작 확인
systemctl is-enabled tailscaled        # enabled
tailscale ip -4                        # 100.x.y.z — 메인Pi 의 Tailscale 주소
exit
```

---

## 4. 연결 확인

cw 노트북에서, **같은 공유기가 아니어도**(휴대폰 핫스팟 등으로 바꿔서 해 보면 확실하다):

```bash
tailscale status                       # esc-main 이 목록에 있고 active/idle
ssh admin@esc-main                     # 내 tailnet 안에서는 짧은 이름으로 된다(MagicDNS)
```

- 짧은 이름이 안 되면 `ssh admin@100.x.y.z`(§3-4 주소)로 해 본다.
- 전체 이름(팀원이 쓸 주소)은 관리 콘솔 https://login.tailscale.com/admin/machines 에서 `esc-main` 을 누르면 나온다 — `esc-main.<tailnet 이름>.ts.net` 꼴. §6 에서 팀원에게 이 이름을 **개인 메시지로** 알려 준다.

---

## 5. 메인Pi 키 만료 끄기

Tailscale 은 기기 로그인을 기본 **180일**마다 다시 하게 한다. 메인Pi 는 화면 없이 도는 서버라 만료되면 원격으로 못 붙으므로 끈다.

1. https://login.tailscale.com/admin/machines
2. `esc-main` 줄 맨 오른쪽 **⋯** → **Disable key expiry**
3. 줄에 "Expiry disabled" 표시가 붙으면 끝.

---

## 6. 팀원에게 메인Pi 공유(초대 보내기)

1. https://login.tailscale.com/admin/machines
2. `esc-main` 줄 맨 오른쪽 **⋯** → **Share…**
3. 둘 중 하나:
   - **Email**(권장) — 팀원이 Tailscale 에 가입할 **그 이메일**을 넣는다. 한 사람에 한 번만 쓰는 링크가 메일로 간다.
   - **Link** — **1회용(single-use)** 링크를 사람마다 따로 만든다. 여러 번 쓰는 링크는 만들지 않는다(누구에게 퍼져도 들어온다).
4. 링크를 쓰는 경우 **개인 메시지로 그 사람에게만** 보낸다. 단톡방·이슈·PR 에 붙이지 않는다.
5. 같이 알려 줄 것: 메인Pi 전체 이름(§4), 이 문서 §7~§11.

> 공유받은 팀원은 메인Pi **한 대로만** 연결을 시작할 수 있다. 메인Pi 쪽에서 팀원 기기로는 연결을 시작하지 못하고(기본 격리), cw 의 다른 기기도 보이지 않는다.

---

## 7. 팀원: Tailscale 가입·설치

1. https://tailscale.com/download 에서 OS 에 맞는 앱 설치.
2. 앱에서 **Log in** → Google·GitHub·Microsoft 중 하나로 가입. 처음 가입하면 **내 tailnet 이 새로 생기고 나는 그 Owner** 가 된다(공유를 받으려면 Owner·Admin 이어야 하는데, 개인 가입이면 자동으로 Owner 다).
3. §6 에서 **Email** 로 받을 거면 cw 에게 알려 준 그 이메일 계정으로 가입한다.
4. 확인: PowerShell/터미널에서 `tailscale status` → 내 노트북 이름과 `100.x.y.z` 가 나온다.

---

## 8. 팀원: 초대 수락

1. cw 가 보낸 초대(메일 또는 링크)를 연다 — §7 의 계정으로 로그인된 브라우저에서.
2. 초대 내용(`esc-main` 공유)을 확인하고 **Accept**.
3. 확인:
   ```bash
   tailscale status                    # 목록에 esc-main 이 보인다 (공유받은 기기)
   ping esc-main.<tailnet 이름>.ts.net  # cw 가 알려 준 전체 이름. Windows 는 ping 그대로, 응답이 오면 OK
   ```
   - 공유받은 기기는 **짧은 이름(`esc-main`)으로 안 될 수 있다** — 전체 이름이나 `100.x.y.z` 를 쓴다.

---

## 9. 팀원: SSH 키 만들고 공개키 보내기

메인Pi 는 `admin` 계정 하나를 같이 쓴다. 비밀번호를 돌리지 않고 **각자 SSH 키**로 들어간다.

**Windows (PowerShell)**
```powershell
ssh-keygen -t ed25519 -C "dh@노트북"          # 이름 부분은 자기 것으로. 질문은 모두 Enter
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub
```

**macOS / Linux**
```bash
ssh-keygen -t ed25519 -C "wj@노트북"
cat ~/.ssh/id_ed25519.pub
```

- 이미 `id_ed25519` 가 있으면 새로 만들지 말고(덮어쓰기 질문에 `n`) 있는 `.pub` 를 쓴다.
- 출력된 **한 줄**(`ssh-ed25519 AAAA… dh@노트북`)을 cw 에게 보낸다. 이건 **공개키**라 보내도 된다.
- **`.pub` 가 없는 파일(`id_ed25519`)은 비밀키다 — 절대 보내지 않는다.**

---

## 10. cw: 팀원 공개키 등록

cw 노트북에서 (팀원이 보낸 한 줄을 따옴표 안에 그대로):

```bash
ssh admin@esc-main "echo 'ssh-ed25519 AAAA…(팀원이 보낸 줄 전체)… dh@노트북' >> ~/.ssh/authorized_keys"
ssh admin@esc-main "cat ~/.ssh/authorized_keys | awk '{print \$3}'"   # 등록된 키 이름 목록 — dh@노트북 이 보이면 OK
```

- 한 사람에 한 줄. 끝의 이름(`dh@노트북`)으로 누구 키인지 구분한다(§12 에서 지울 때 쓴다).
- `>>` (두 개)로 **덧붙인다**. `>` 하나면 기존 키가 다 지워져 cw 도 못 들어간다.

---

## 11. 팀원: 접속 확인

```bash
ssh admin@esc-main.<tailnet 이름>.ts.net
#   처음이면 "Are you sure you want to continue connecting" → yes
```

- `admin@ESC-main:~ $` 프롬프트가 나오면 성공. 학교 밖(집·핫스팟)에서도 같은 명령으로 된다.
- 웹도 같은 주소로 열린다(메인Pi 에 서버를 띄운 뒤, Pi↔Pi 통합 가이드 §3):
  - 서버 API: `http://esc-main.<tailnet 이름>.ts.net:8000/api/health`
  - 웹: `http://esc-main.<tailnet 이름>.ts.net` (웹 컨테이너 :80)
- `sudo` 가 필요한 작업(패키지 설치 등)은 `admin` 비밀번호가 필요하다 — cw 에게 요청한다. Docker 명령은 `docker` 그룹이라 `sudo` 없이 된다(Docker 설치 후).

---

## 12. 접근 해제(팀원이 빠질 때)

두 가지를 **모두** 한다.

1. **공유 취소** — https://login.tailscale.com/admin/machines → `esc-main` **⋯** → **Share…** → 그 사람 초대의 **⋯** → **Revoke invite**. 즉시 연결이 끊긴다.
2. **SSH 키 삭제** — cw 노트북에서:
   ```bash
   ssh admin@esc-main "sed -i '/ dh@노트북$/d' ~/.ssh/authorized_keys"   # 이름 부분만 바꾼다
   ssh admin@esc-main "cat ~/.ssh/authorized_keys | awk '{print \$3}'"  # 목록에서 빠졌는지
   ```

---

## 13. 막히면

| 증상 | 원인·해결 |
|---|---|
| `tailscale status` 가 `NoState`·`Logged out` | 앱 로그인이 안 됐다 — 트레이 아이콘 → Log in |
| §3-2 뒤 주소를 열었는데 Pi 가 `Success.` 를 안 띄움 | 다른 계정으로 승인했다 — §2 와 같은 계정인지 확인. Pi 에서 `sudo tailscale up --hostname=esc-main` 다시 |
| `curl: … Could not resolve host` (§3-1) | 메인Pi 인터넷이 안 된다 — `ping -c 3 8.8.8.8` |
| 팀원 목록에 `esc-main` 이 없다 | 초대를 다른 계정으로 수락했다 — §7 의 계정으로 로그인한 브라우저에서 초대 다시 열기. 1회용 링크를 이미 썼으면 cw 가 새로 만든다 |
| `ssh: Could not resolve hostname esc-main` | 공유받은 쪽은 짧은 이름이 안 될 수 있다 — 전체 이름(`esc-main.<tailnet>.ts.net`)이나 `100.x.y.z` |
| `Permission denied (publickey,password)` | 공개키가 등록 안 됐거나 다른 키로 접속 — §10 목록에 내 이름이 있는지, `ssh -i ~/.ssh/id_ed25519 admin@…` |
| 한동안 잘 되다 갑자기 안 됨 | §5 키 만료를 안 껐다 — 관리 콘솔에서 `esc-main` 이 "Expired" 면 Pi 에서 `sudo tailscale up` 다시 + §5 |
| 학교 Wi-Fi 에서만 안 됨 | 학교망이 UDP 를 막아도 Tailscale 은 중계(DERP)로 붙는다(느릴 뿐). `tailscale ping esc-main.<tailnet>.ts.net` 로 경로 확인 |
