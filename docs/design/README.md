# docs/design — 디자인 스펙 (mh → wj 계약)

> mh(@jmh7706jmh-ops)가 시안을 만들고 **이 폴더의 문서로 스펙을 확정**하면, wj(@leemonta9482)가 그대로 `web/` 코드로 구현한다.
> 문서가 원본이고 코드는 구현이다. 코드 리뷰에서 디자인을 바꾸지 않고, 스펙 없이 UI를 먼저 만들지 않는다.

## 파일 구성

```
docs/design/
├── README.md          ← 이 문서 (규칙·템플릿)
├── tokens.md          ← 디자인 토큰: 색·타이포·간격·라운드 (→ web/src/styles/)
├── components.md      ← 컴포넌트 카탈로그: variant·size·상태 (→ web/src/components/ui/)
├── screens/
│   ├── admin-schedule.md   ← 화면 1장 = 문서 1개 (→ web/src/views/)
│   ├── admin-nodes.md
│   ├── student-week.md
│   └── terminal-epaper.md  ← 단말 e-Paper 화면 (→ firmware/src/terminal/, 소비자는 dh)
└── assets/            ← 시안에서 뽑은 아이콘·이미지 원본 (wj가 web/src/assets/ 로 복사)
```

시안 자체(Figma 링크·PNG)는 각 문서 상단에 링크한다. 저장소에는 **값과 규칙**만 남긴다 — 코드가 읽을 수 있어야 한다.

## 순서 (lockstep)

1. mh: 시안 → 스펙 문서 PR (`docs(design): …`). CODEOWNERS로 mh가 소유. wj가 리뷰(구현 가능한지·서버 필드와 맞는지).
2. 머지 후 wj: 코드 PR (`feat(web): …` / `style(web): …`). `src/styles/`·`src/components/ui/`는 mh가 CODEOWNERS 리뷰어로 **디자인 일치**를 검수한다.
3. 바꾸고 싶으면 1부터 다시. 스펙 변경은 additive를 우선한다(기존 토큰 이름·컴포넌트 props는 유지, 새 것 추가).

단말 e-Paper 화면(`screens/terminal-epaper.md`)은 같은 절차를 **dh**와 돈다 — mh가 스펙 PR, dh가 리뷰(렌더 가능한지·자산이 있는지), 머지 후 dh가 `firmware/src/terminal/` 구현.

## 템플릿

### tokens.md

```markdown
# 디자인 토큰 v1 (시안: <링크>)

## 색
| 토큰 | 값 | 용도 |
|---|---|---|
| color.ink | #111111 | 글자·선·반전 바탕 |
| color.paper | #F7F6F3 | 모든 바탕 — 카드도 같다. 구분은 ink 1px 선이 한다 |
| color.signal | #C8102E | 적색 — 사용중 상태·파괴적 동작·포커스 링 |
| color.status.busy | = signal | 사용중 — 수업·시험·특강·대여 (e-Paper RED) |
| color.status.free | = ink | 비어있음 — 휴강·빈강의실·쉬는시간·설정 대기 (e-Paper BLACK) |
…

## 타이포
| 토큰 | 값 |
|---|---|
| font.family | "Pretendard", system-ui, sans-serif |
| font.size.sm / md / lg / xl | 12 / 14 / 16 / 20 px |
| font.weight.regular / bold | 400 / 700 |

## 간격 · 라운드 · 보더
| 토큰 | 값 |
|---|---|
| space.1 … space.6 | 4 / 8 / 12 / 16 / 24 / 32 px |
| radius.sm / md | 4 / 8 px |
| border.thin / thick | 1 / 2px |

## 브레이크포인트
| 토큰 | 값 |
|---|---|
| bp.mobile | < 640px |
| bp.desktop | ≥ 1024px |
```

토큰 이름은 그대로 CSS 변수가 된다: `color.status.class` → `--color-status-class`.

다크 모드는 v1 범위 밖이다. 필요해지면 이 표에 `다크` 열을 더하는 방식(additive)으로 넣고, 토큰 이름은 그대로 둔다.

### components.md

컴포넌트마다 한 절. **props와 상태를 표로** — wj는 이 표가 곧 Vue 컴포넌트의 인터페이스다.

```markdown
## Button (시안: <링크>)
| prop | 값 | 기본 |
|---|---|---|
| variant | primary / secondary / danger / ghost | primary |
| size | sm / md | md |
| disabled | boolean | false |
| loading | boolean | false |

상태별 색: primary = color.primary 배경 + 흰 글자, hover 10% 어둡게, disabled 불투명도 .5 …
높이: sm 28px / md 36px. 패딩: space.2 space.4. 라운드: radius.md.

## Input / Select / Table / Badge / Modal / Toast …
```

### screens/<name>.md

```markdown
# 관리자 — 시간표 (시안: <링크>)

## 목적 · 진입
관리자가 강의실을 골라 주간 시간표를 보고 슬롯을 추가·수정·삭제한다. 진입: 사이드 메뉴 "시간표".

## 레이아웃
- 데스크톱: 좌 강의실 목록(240px) + 우 주간 그리드. 모바일: 상단 셀렉트 + 그리드 세로 스크롤.
- 그리드: 요일 7열 × 09:00~21:00, 30분 단위 행.

## 사용하는 컴포넌트
Select(강의실), Button(추가), Table 아님 — 커스텀 그리드, Badge(type: 수업/휴강/특강), Modal(슬롯 편집 폼)

## 데이터 (서버 계약)
- `GET /api/rooms`, `GET /api/rooms/{id}/slots`, `PUT /api/rooms/{id}/slots`, `DELETE …`
- 슬롯 셀에 표시: subject, professor, s_h:s_m–e_h:e_m. type 별 Badge 색 = color.status.*

## 상태
- 로딩: 그리드 자리에 스켈레톤
- 빈 상태: "이 강의실에 등록된 시간표가 없습니다" + 추가 버튼
- 에러: 상단 Toast(danger), 재시도 버튼
- 저장 후: outbox 상태(queued → dispatched → acked)를 셀 우상단 점으로 — 색이 아니라 채움 정도 ○ ◐ ●

## 상호작용
- 셀 클릭 → 편집 Modal. 빈 셀 클릭 → 추가 Modal(시간 미리 채움).
- 삭제는 Modal 안 danger 버튼 + 확인.
```

## 규칙

- 값은 **숫자·색상코드·이름**으로 쓴다. "적당히", "약간 어둡게" 금지 — 코드로 옮길 수 없다.
- 서버 필드명은 `server/app/schemas.py`(OpenAPI `/docs`)를 그대로 쓴다. 화면이 서버에 없는 필드를 요구하면 wj에게 이슈 — 서버(additive)가 먼저다.
- 웹 팔레트는 값이 셋뿐이다 — 흑·백·적 각 하나. 회색을 만들지 않는다(옅은 선도, 중간 보조 텍스트도). 위계는 크기·굵기·면적·반전으로 만든다. 강의실 상태는 사용중 = 적, 나머지 = 흑이고, 넷을 색으로 나누지 않고 라벨 텍스트로 구분한다.
- 접근성 최소: 텍스트 대비 4.5:1, 포커스 링 토큰 1개, 상태를 색으로만 구분하지 않기(아이콘·텍스트 병기).
- 커밋 scope: `docs(design): …`. 브랜치 `mh`. PR은 wj 리뷰 → 팀장 머지.
