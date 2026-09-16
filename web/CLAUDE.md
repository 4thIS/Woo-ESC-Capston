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

## 계약(Contract) 규칙

- 이 영역은 계약을 **소비**한다. 서버 응답을 임의 변환하지 않는다 — 형태를 바꿔야 하면 `server/`를 바꾸고 계약을 그쪽에 반영한다. (소비 쪽에서 맞추면 계약이 두 곳에 생겨 어긋난다.)
- 서버가 아직 안 만든 필드를 가정하고 화면을 먼저 만들지 않는다. 서버(additive) 머지가 **먼저**다(lockstep).

## 절대 하지 말 것

- 다른 영역 디렉토리(`firmware/`, `server/`, `modempi/`) 수정 금지 — 필요 시 이슈로 요청.
- `docs/design/`에 없는 토큰 값·컴포넌트 variant를 코드에서 먼저 만들지 않는다 — 스펙부터(mh).
- 패키지 매니저·Node 버전 설정 임의 변경 금지.
- 서버 응답 스키마가 불편하다고 프론트에서 변환·보정 금지 — 서버를 고친다.
