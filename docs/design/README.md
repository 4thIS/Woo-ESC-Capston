# docs/design — 디자인 스펙 (mh → wj 계약)

> mh(@jmh7706jmh-ops)가 시안을 만들고 **이 폴더의 문서로 스펙을 확정**하면, wj(@leemonta9482)가 그대로 `web/` 코드로 구현한다.
> 문서가 원본이고 코드는 구현이다. 코드 리뷰에서 디자인을 바꾸지 않고, 스펙 없이 UI를 먼저 만들지 않는다.

## 파일 구성

```
docs/design/
├── README.md          ← 이 문서 (규칙·템플릿)
├── tokens.md          ← 디자인 토큰: 원시·시맨틱·도메인 3층 + 치수 (→ web/src/styles/)
├── components.md      ← 컴포넌트 카탈로그: variant·size·상태 (→ web/src/components/ ui/ · domain/ · chart/)
├── screens/
│   ├── auth.md             ← 가입·로그인·재설정 (학생·관리자 공용 흐름)
│   ├── admin-rooms.md      ← 페이지1: 건물 전체 시간표·예약·시험기간 설정 (→ web/src/views/)
│   ├── admin-schedule.md   ← 페이지2: 강의실 하나의 주간 시간표 + 셀 편집
│   ├── admin-dashboard.md  ← 분석 대시보드 (차트 규칙은 tokens.md 의 chart.* 를 따른다)
│   ├── admin-nodes.md      ← 노드 상태·모뎀Pi·등록 대기
│   ├── admin-users.md      ← 회원 승인 (S4a)
│   ├── student-room.md     ← 학생 웹 (S10, 모바일 우선, 라우트 3개)
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
# 디자인 토큰 v2 (시안: <링크>)

토큰은 **원시 → 시맨틱 → 도메인 3층**이다. 화면(`views/`)은 3층과 2층만 참조하고 1층을 직접 쓰지 않는다.

## 1층 — 원시 팔레트
| 토큰 | 값 | 흰 바탕 대비 |
|---|---|---|
| gray.0 … gray.800 | #FFFFFF … #262626 | (gray.400 이하는 텍스트 금지) |
| blue.600 / red.700 | #0B5ED7 / #B42318 | 5.84 / 6.57 |
…

## 2층 — 시맨틱 (wj 가 쓰는 이름)
| 토큰 | = | 용도 |
|---|---|---|
| bg / surface / sunken | gray.0 / gray.0 / gray.25 | 면 |
| line.1 / line.2 / line.3 | gray.100 / gray.200 / gray.300 | 헤어라인 / 경계 / 입력 |
| text.1 / text.2 / text.3 | gray.800 / gray.600 / gray.500 | 본문 / 부차 / 보조 |
| brand / danger / focus | blue.600 / red.700 / blue.600 | 1차 액션 · 파괴 · 포커스 |

## 3층 — 도메인
| 토큰 | = | 용도 |
|---|---|---|
| room.busy.fill / .line / .label | red.50 / red.100 / red.700 | 사용중 (e-Paper RED, layout 1·5·6·7) |
| room.free.text / .line | text.3 / line.3 | 비어있음·휴강 (e-Paper BLACK) |
| chart.series.1 / .2 / .3 | blue.600 / teal.600 / gold.600 | 분석 대시보드 계열색 |

## 타이포
| 토큰 | 값 |
|---|---|
| font.family | "Pretendard Variable", Pretendard, system-ui, sans-serif |
| font.weight.regular / medium / bold | 400 / 500 / 700 |

## 치수 — admin / student 로 갈린다
| 토큰 | admin | student |
|---|---|---|
| font.size.xs … xl | 11 / 12 / 13 / 16 / 22 px | 12 / 13 / 15 / 18 / 20 px |
| control.height.md | 32px | 48px (터치 하한) |
| radius.sm / md / lg | 4 / 6 / 8 px | 6 / 8 / 12 px |

## 간격 · 보더 · 브레이크포인트
| 토큰 | 값 |
|---|---|
| space.1 … space.7 | 4 / 8 / 12 / 16 / 24 / 32 / 48 px |
| border.thin / thick | 1 / 2px |
| bp.mobile / bp.desktop | < 640px / ≥ 1024px |
```

토큰 이름은 그대로 CSS 변수가 된다: `room.busy.fill` → `--room-busy-fill`.

**색은 두 웹 공용, 치수만 갈린다.** `--font-size-md` 를 루트에서 admin 값으로 두고 학생 웹 진입점(`<html data-surface="student">`)에서 재정의한다 — 이름은 같고 값만 바뀌므로 컴포넌트는 어느 웹에 있는지 몰라도 된다.

**그림자 토큰은 없다.** 층은 면(`surface` vs `sunken`)과 테두리(`line.2`)로 나눈다. 다크 모드는 v2 범위 밖이다.

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

상태별 색: primary = brand 배경 + 흰 글자, hover 10% 어둡게, disabled 불투명도 .5 …
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
- 슬롯 셀에 표시: subject, professor, s_h:s_m–e_h:e_m. 셀 색 = room.* (type 별로 색을 나누지 않고 Badge 라벨로 나눈다)

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
- 강의실 상태는 e-Paper 의 RED/BLACK 이분법과 1:1이다: 사용중(수업중·시험중·특강·대여중) = `room.busy`, 나머지 = `room.free`. **넷을 색으로 나누지 않고 Badge 라벨 텍스트로 나눈다** — 같은 적색 계열 안에서 갈라 봤자 서로의 대비가 1.02~1.88이라 나뉘지 않는다.
- **유채색은 브랜드 파랑과 상태 적색 둘뿐이다.** 구조(바탕·선·보조 텍스트)는 전부 무채색이고, 위계는 크기·굵기·면으로 만든다. `brand` 는 1차 액션과 활성 상태 전용이라 화면당 채워진 brand 버튼은 하나다.
- **적색은 면이 아니라 라벨에 쓴다.** 셀을 통째로 적색으로 채우지 않는다 — 하루치만 차도 화면이 경고판으로 읽힌다.
- 차트 색은 `tokens.md` 의 `chart.*` 를 그대로 쓴다. 계열은 고정 순서로 배정하고 **4계열 이상 금지**, `danger` 적색은 계열색으로 재사용하지 않는다. 임의로 고른 색은 색각이상 검증을 통과하지 않는다.
- **관리자 웹은 데스크톱(`bp.desktop` ≥ 1024px) 전용이다.** 태블릿·모바일 전용 레이아웃을 설계하지 않는다 — 관리자는 PC에서 쓰고, 그 폭에 따로 시간을 쓰느니 학생 웹에 쓴다. 대신 **막지는 않는다**: 콘텐츠 컨테이너에 `min-width: 1024px` 를 두고 그보다 좁으면 데스크톱 레이아웃 그대로 가로 스크롤시킨다. 좁은 폭에서 처음 열면 닫을 수 있는 안내 배너를 한 번 띄운다("관리자 화면은 1024px 이상에서 쓰도록 만들어졌습니다"). 학생 웹은 반대로 모바일 우선이고 넓은 폭에서도 동작해야 한다.
- 접근성 최소: 텍스트 대비 4.5:1, 포커스 링 토큰 1개, 상태를 색으로만 구분하지 않기(아이콘·텍스트 병기). 학생 웹 터치 타깃 48px 이상.
- 커밋 scope: `docs(design): …`. 브랜치 `mh`. PR은 wj 리뷰 → 팀장 머지.
