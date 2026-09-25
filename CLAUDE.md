# Woo-ESC-Capston — 협업 가이드 (CLAUDE.md)

> 이 파일은 **이 프로젝트에 참여하는 모든 사람과 모든 AI**가 최우선으로 읽는 협업 헌법입니다.
> 개인 글로벌 설정(`~/.claude/CLAUDE.md` 등)보다 이 파일이 우선합니다.
> 큰 원칙만 여기 두고, 세부는 영역별 `CLAUDE.md`와 `docs/` 하위로 위임합니다(Progressive Disclosure).

## 프로젝트 개요

- 목적: e-Paper와 LoRa 통신을 활용한 저전력 강의실 시간표·예약 게시 시스템 (캡스톤디자인). 단말은 딥슬립 상태로 대기하다 LoRa 웨이크로 갱신 프레임을 받아 7.5" 3색 e-Paper에 강의실 상태를 표시한다.
- 장비 명칭: **메인Pi**(웹서버·DB 원본, 전체 1대) · **모뎀Pi**(학교 건물당 1대, Heltec 모뎀 USB 연결, 메인Pi에 WebSocket 접속) · **ESP노드**(강의실 문마다, Heltec V3 + e-Paper). 이 세 이름만 쓴다.
- 스택: 노드·모뎀 펌웨어 = PlatformIO / C++ (ESP32-S3 + SX1262, RadioLib + GxEPD2) · 메인Pi 서버 = FastAPI / Python(uv) · 모뎀Pi 서비스 = Python asyncio(uv) · 웹 = Vue 3 / TypeScript(pnpm) · 프로토콜 계약 = `lora_proto/` (C++ 헤더 + Python 미러)
- 호스팅: https://github.com/4thIS/Woo-ESC-Capston
- 배포: 메인Pi·모뎀Pi 모두 Raspberry Pi(보유). 개발·데모는 노트북, 4주차 Pi↔Pi 통합부터 실기. **메인Pi 서버는 Docker Compose**(루트 `compose.yaml` + `server/Dockerfile`, 2026-09-23 팀 결정) — 노트북에서도 같은 명령(`docker compose up -d --build`)으로 똑같이 띄운다. **모뎀Pi 는 systemd**(USB 시리얼·시계 동기에 직접 붙어야 해서). 자동 배포 파이프라인은 S11 시점에 확정한다. 현재 CI는 검증까지만 수행한다.

## 역할 분담

| 사람 | 계정 | 영역 | 책임 |
|------|------|------|------|
| cw | @ssenu (Owner) | 전 영역 총괄 + `lora_proto/` + `firmware/` 무선·스케줄링 + `modempi/lora/` | 설계(spec/plan)·계약·인프라·최종 승인. LoRa 파이프라인(전처리→송신) |
| dh | @Hyeon02-kr | `firmware/src/terminal/render*`, `firmware/src/fonts/`, `firmware/lib/host_gfx/`·`lib/fixture_parse/`·`lib/adafruit_gfx_vendor/`, `firmware/tools/` | e-Paper 렌더링·화면 레이아웃 구현, 호스트 렌더 프리뷰 인프라. 모뎀 펌웨어 지원 |
| wj | @leemonta9482 | `server/`, `web/` **전체**, `modempi/link/` | 메인Pi 서버·관리자/학생 웹 풀스택(디자인 스펙을 Vue 코드로 구현), 메인Pi↔모뎀Pi WebSocket 링크 |
| mh | @jmh7706jmh-ops | `docs/design/` | 웹 디자인 — 시안 제작 → **디자인 스펙 문서**(토큰·컴포넌트·화면) 작성, 구현물 디자인 QA(리뷰). 코드는 쓰지 않는다 |

### 계층 규율 (고비용 계층 보호)

아래 경로는 함부로 고치지 않는다. 흔들리면 파급이 커 품질이 무너지는 계층이다.

| 경로 | 내용 | 고칠 때 |
|------|------|---------|
| `lora_proto/` | 공중 프레임 규격·무선 파라미터의 **단일 진실원**. C++ 헤더와 Python 미러가 같은 상수를 공유하고 `test_vectors.json`으로 교차 검증된다 | PM(@ssenu) 전담. 상수 1개를 바꿔도 펌웨어·서버가 동시에 깨진다. 반드시 헤더·미러·벡터를 한 커밋에서 함께 갱신하고, 그 PR을 **단독으로 먼저** 머지한다(lockstep) |
| `firmware/lib/lora_codec/` | 프레임 인코딩/디코딩. 단말·모뎀이 공용으로 링크 | 단말만 보고 고치지 말 것 — 모뎀 쪽 동작을 함께 확인하고 `pio test`의 벡터 테스트를 통과시킨다 |
| `server/lora_service/` | outbox·버전 벡터·`api.py`·WS 허브(메인Pi ↔ 모뎀Pi 계약 ⑥의 제공 측) | wj가 구현하되 **PM(@ssenu)이 필수 리뷰**. 여기가 웹·모뎀Pi 양쪽 계약의 접점이다. 메시지·시그니처를 바꾸면 로드맵 스펙 §4.2 갱신 + BREAKING CHANGE 명시 |
| `modempi/store.py` | 모뎀Pi 내부 계약 ⑦ — 링크(wj)와 파이프라인(cw)이 만나는 SQLite 스키마 | 양쪽 협의 + 양쪽 리뷰. 컬럼은 additive만 |
| `docs/design/` ↔ `web/src/styles/`, `web/src/components/ui/` | 디자인 스펙(문서, mh) ↔ 디자인 토큰·디자인시스템(코드, wj) | **스펙이 원본, 코드는 구현.** 토큰 값·컴포넌트 variant를 바꾸려면 mh가 `docs/design/` PR을 먼저 머지하고 wj가 코드 PR로 따라간다(lockstep). 화면(`views/`)에서 토큰을 우회한 하드코딩 색·간격 금지. mh는 이 두 코드 경로의 CODEOWNERS 리뷰어로 디자인 일치를 검수한다 |

## 폴더 구조 요약

```
Woo-ESC-Capston/
├── lora_proto/   ← 프로토콜 계약: C 헤더 원본 + Python 미러·codec + test_vectors.json (Owner 전담, README 의 lockstep 절차)
├── firmware/     ← 노드·모뎀 펌웨어 (PlatformIO, C++)
├── server/       ← 메인Pi: FastAPI 백엔드 + outbox·버전·WS 허브
├── modempi/      ← 모뎀Pi: WS 링크(wj) + LoRa 파이프라인(cw)
├── web/          ← Vue 3 학생/관리자 웹 (wj 전체)
├── compose.yaml  ← 메인Pi 배포(Docker). 서버 이미지는 server/Dockerfile
└── docs/         ← 사람·AI 공용 문서 (specs/·plans/·design/ 포함. design/ 은 mh의 디자인 스펙)
```

## 브랜치 전략

- `main`은 protected. **직접 push 금지.**
- 담당자별 상시 작업 브랜치: `cw` / `dh` / `wj` / `mh`. 각자 자기 브랜치에서 작업하고 `main`으로 PR을 연다.
- 한 브랜치에 작업이 겹쳐 커지면 자기 브랜치에서 `feature/<slug>`를 분기해 PR 단위를 쪼갠다.
- 머지는 **Squash merge**. 리뷰 반영은 추가 커밋으로 — force push 금지.

## 작업 흐름

### 새 기능

1. brainstorming → `docs/specs/`에 spec 작성·커밋 (PM)
2. writing-plans → `docs/plans/`에 plan 작성·커밋 (Task 단위, PM)
3. 이슈 생성 → 담당자 할당 (spec·plan 링크 첨부)
4. 담당자: 자기 브랜치에서 plan대로 구현. 매 Task TDD (실패 테스트 먼저)
5. PR 전 로컬 게이트(lint·test) 통과 확인 → PR 생성
6. 리뷰 → Squash merge

### 버그 수정

1. 근본 원인 진단(증상 아님) → 진단 결과를 PR 설명에 첨부
2. 실패 재현 테스트 작성 → 수정 → PR

### Trivial 예외

오타·문서·한 줄 수정은 spec/plan 생략 가능. 단 **PR·리뷰는 반드시 거침**.

## 커밋 규칙 — Conventional Commits

```
feat(firmware): ...     # 단말·모뎀 펌웨어 기능
feat(server): ...       # 메인Pi 백엔드 기능
feat(modempi): ...      # 모뎀Pi 링크·파이프라인
feat(web): ...          # 웹 기능
feat(proto): ...        # 프로토콜 계약 변경 (펌웨어·모뎀Pi 양쪽 영향)
feat(backhaul): ...     # 메인Pi↔모뎀Pi WS 계약 변경 (server·modempi 양쪽 영향)
fix(<area>): ...        # 버그
style(web): ...         # 퍼블리싱·스타일
chore(infra): ...       # 인프라·CI
docs: ...               # 문서
```

## PR 규칙

1. PR 1개 = 작은 작업 1개. 거대 변경은 분할.
2. 제목은 Conventional Commits 형식(Squash 시 커밋 메시지).
3. 템플릿 체크리스트를 모두 채운다.
4. CI 통과 필수.
5. 자기 영역만 수정 — 타 영역이 필요하면 코드로 침범하지 말고 이슈로 요청.
6. **머지는 팀장(cw @ssenu)만 한다.** 영역 담당자의 승인(CODEOWNERS 리뷰)은 "머지해도 된다"는 신호이지 머지 자체가 아니다. 승인이 끝난 PR은 팀장에게 알리고 기다린다. 팀장 본인의 PR도 영역 담당자 승인을 받은 뒤 스스로 머지한다.
   - 왜: `main`에 무엇이 언제 들어가는지를 한 사람이 알고 있어야 계약(lockstep) 순서와 릴리스 시점을 통제할 수 있다.
   - 강제: GitHub 브랜치 보호에서 *Restrict who can push to matching branches*를 `ssenu`로 제한한다(PR 머지도 push 권한을 따른다).

## 절대 하지 말 것

1. 비밀키·`.env`·인증서 커밋 금지 (pre-commit 훅이 차단)
2. `main` 직접 push 금지 (Protected Branch). **PR 머지도 팀장(@ssenu) 외에는 금지** — 승인 버튼까지가 담당자의 역할이다.
3. 계약(`lora_proto/`) 변경과 그 계약에 의존하는 코드를 같은 PR에 섞지 않음 — **계약 먼저 머지 후 코드**(lockstep)
4. 계층 규율 경로를 기준 대조 없이 수정 금지
5. `git push --force`, `git reset --hard` 금지
6. 파괴적 명령 임의 실행 금지 — 막히면 이슈로 남김

## 문서 인덱스

| 문서 | 내용 |
|------|------|
| `docs/specs/2026-09-09-lora-v2-wor-design.md` | **v2 시스템 설계 스펙** — 하드웨어·공중 프로토콜·펌웨어·백엔드·구현 단계(P0~P8). 구현 전 반드시 정독 |
| `docs/specs/2026-09-09-roadmap-design.md` | **진행 로드맵** — 메인Pi/모뎀Pi/ESP노드 토폴로지, 서브프로젝트 S1~S11, 영역 간 계약 7개(WS 백홀·JobStore 포함), 주차별 산출물, 마일스톤 완료 기준. **v2 §8을 대체** |
| `docs/specs/`·`docs/plans/` | 설계서·작업지시서 (템플릿 포함) |
| `firmware/CLAUDE.md` | 펌웨어 영역 규칙 |
| `server/CLAUDE.md` | 메인Pi 서버 영역 규칙 |
| `modempi/CLAUDE.md` | 모뎀Pi 영역 규칙 (링크/파이프라인 분할) |
| `web/CLAUDE.md` | 웹 영역 규칙 |
| `docs/design/README.md` | 디자인 스펙 작성 규칙·템플릿 (mh → wj 계약) |
