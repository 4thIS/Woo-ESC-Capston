# web — 영역 가이드

> 루트 `../CLAUDE.md`를 먼저 읽으십시오. 이 파일은 web 영역 특수 규칙만 다룹니다.
> 이 영역은 서버가 제공하는 계약(`server/lora_service/api.py`·HTTP 응답)의 **소비자**입니다.

## 스택

- 언어/런타임: TypeScript / Vue 3 (Vite)
- 패키지 매니저: **pnpm** (다른 매니저 사용 금지 — `pnpm-lock.yaml`을 커밋한다)
- 테스트: Vitest
- 린트·포맷: ESLint + Prettier + `vue-tsc` 타입 체크

## 폴더 규칙

```
web/
├── src/styles/          # 디자인 토큰 — docs/design/tokens.md 를 CSS 변수로 옮긴 것 (보호 계층)
├── src/components/ui/   # 디자인시스템 컴포넌트 — docs/design/components.md 의 구현 (보호 계층)
├── src/assets/          # 이미지·아이콘·폰트 — mh가 시안에서 뽑아 준 파일
├── src/views/           # 화면 — docs/design/screens/*.md 의 구현
├── src/router/          # 라우트
└── src/api/             # 서버 계약 소비 계층 (fetch 래퍼·타입)
```

## 계층 책임

- 서버 응답 타입은 `src/api/`에 한 번만 선언한다. 화면마다 응답을 재해석하지 않는다.
- `src/views/`는 `src/components/ui/`를 **조합**한다. 화면 안에서 새 버튼·입력을 직접 스타일링하지 않는다 — 스펙에 없는 컴포넌트가 필요하면 `docs/design/`에 이슈로 요청하고 mh가 스펙을 올린 뒤 구현한다.
- `src/styles/`의 토큰을 우회한 하드코딩 색상·간격 금지. 토큰 값은 `docs/design/tokens.md`가 원본이다.
- 공통 인프라 계층은 도메인을 import하지 않는다(의존 방향 단방향 유지).

## 역할 분담 — 디자인 스펙(문서) ↔ 코드

| 산출물 | 담당 |
|------|------|
| 시안(Figma 등) + `docs/design/` 디자인 스펙(토큰·컴포넌트·화면) | mh @jmh7706jmh-ops |
| `web/` 코드 전체 (`styles/`·`components/ui/`·`views/`·`api/`·라우팅·상태) | wj @leemonta9482 |
| 구현물 디자인 QA | mh — `src/styles/`·`src/components/ui/` PR의 CODEOWNERS 리뷰어 |

이 둘 사이의 내부 계약은 **디자인 스펙 문서**다(형식은 `docs/design/README.md`). 스펙 → 코드 순서(lockstep): 토큰·컴포넌트를 바꾸려면 mh가 스펙 PR을 먼저 머지하고, wj가 코드 PR로 따라간다. wj가 스펙 없이 UI를 먼저 만들지 않고, mh가 스펙 없이 코드 리뷰에서 디자인을 바꾸지 않는다.

## 커밋 scope

- `feat(web):`, `fix(web):`, `style(web):` (퍼블리싱·디자인시스템 변경은 `style(web):`)

## 테스트

- 새 코드는 테스트 동반(TDD: 실패 → 구현 → 통과).
- 서버 계약 소비 로직(`src/api/`)은 응답 픽스처로 테스트한다 — 서버가 필드를 바꾸면 여기가 먼저 빨개져야 한다.
- 통합 동작은 로컬 실행 환경에서 확인.

## 배포 (Docker)

- 루트 `compose.yaml` 의 `web` 서비스 — `web/Dockerfile` 이 `pnpm build` 결과(`dist/`)를 nginx(`web/nginx.conf`)로 내보낸다. 기본 포트 80(`WEB_PORT` 로 변경).
- nginx 가 맡는 것: `/admin/*` → `admin.html`, 나머지 → `index.html`(새로고침해도 그 앱), `/api/*` → `server:8000` 프록시, `/assets/*` 1년 캐시(해시 파일명), html 은 `no-cache`.
- 서버는 `X-Forwarded-For` 를 web 컨테이너(고정 IP `172.30.250.10`)가 준 것만 믿는다(compose 의 `FORWARDED_ALLOW_IPS`) — 로그인 상한이 사람마다 걸리게. nginx 는 이 헤더를 덮어쓴다.
- 웹만 다시: `docker compose up -d --build web`. 서버를 다시 만들어도 웹은 재시작할 필요가 없다(요청마다 `server` 를 다시 찾는다).

## E2E (Playwright)

- `pnpm e2e` — 임시 DB 로 메인Pi 서버(기본 `../server`)와 Vite dev 서버를 띄우고 `e2e/*.spec.ts` 를 돈다. 학교 둘(명지전문대학 id 1 · 타학교 id 2)과 관리자들을 CLI 로 심는다(`e2e/env.json`).
- **다른 서버 체크아웃으로 돌리기**: `E2E_SERVER_DIR` 에 서버 폴더(web/ 기준 상대 또는 절대 경로). 예: 아직 main 에 없는 API 를 가진 통합 워크트리.
  - PowerShell: `$env:E2E_SERVER_DIR = 'C:\path\to\server'; pnpm e2e`
  - bash: `E2E_SERVER_DIR='C:\path\to\server' pnpm e2e` (Windows 에서는 `/c/...` 가 아니라 `C:\...` 로)
- **다른 포트로 돌리기**(수동으로 띄운 서버가 8000·5173 을 쓰고 있을 때): `E2E_API_PORT`(기본 8000) · `E2E_WEB_PORT`(기본 5173). 예: `$env:E2E_API_PORT = '8100'; $env:E2E_WEB_PORT = '5273'; pnpm e2e`. dev 서버 프록시 대상은 `VITE_API_TARGET`(기본 `http://127.0.0.1:8000`)이고 E2E 는 이것을 자동으로 넘긴다. 기본 포트에서는 5173 에 이미 떠 있는 dev 서버를 재사용하므로(CI 제외) 그 서버의 프록시가 8000 을 가리켜야 한다.
- `e2e/helpers.ts` 의 `sql()` 은 **테스트 전용** — 무선 트래픽(STATUS·pending·ACK)으로만 생기는 행을 E2E DB 에 직접 넣는다. 관리자 REST 로 만들 수 있는 것(건물·방·모뎀)은 REST 로 만든다.
- 로그인 상한(IP 당 분당 30회) 때문에 새 spec 파일은 `beforeAll` 에서 컨텍스트·로그인을 한 번만 하고 화면 이동은 사이드 메뉴 클릭으로 한다(세션은 sessionStorage 라 `page.goto` 로도 남지만, 새로고침은 화면 상태·폴링을 새로 시작한다).

## 계약(Contract) 규칙

- 이 영역은 계약을 **소비**한다. 서버 응답을 임의 변환하지 않는다 — 형태를 바꿔야 하면 `server/`를 바꾸고 계약을 그쪽에 반영한다. (소비 쪽에서 맞추면 계약이 두 곳에 생겨 어긋난다.)
- 서버가 아직 안 만든 필드를 가정하고 화면을 먼저 만들지 않는다. 서버(additive) 머지가 **먼저**다(lockstep).

## 절대 하지 말 것

- 다른 영역 디렉토리(`firmware/`, `server/`, `modempi/`) 수정 금지 — 필요 시 이슈로 요청.
- `docs/design/`에 없는 토큰 값·컴포넌트 variant를 코드에서 먼저 만들지 않는다 — 스펙부터(mh).
- 패키지 매니저·Node 버전 설정 임의 변경 금지.
- 서버 응답 스키마가 불편하다고 프론트에서 변환·보정 금지 — 서버를 고친다.
