# 컴포넌트 카탈로그 v2

- 시안: https://claude.ai/artifact/NLQyYEEdt4Rv6Dn7JZZuHi
- 소비자: wj → `web/src/components/`
- 전제: `tokens.md` v2. **값은 여기서 다시 적지 않고 토큰 이름으로만 쓴다.** 치수는 `admin` 세트 기준이고, 학생 웹에서 달라지는 것만 따로 적는다
- 대체: v1(mh-03, 미머지)을 폐기하고 대신한다

각 절의 **props 표가 곧 Vue 컴포넌트의 인터페이스**다.

## v1에서 무엇이 바뀌었나

v1 카탈로그는 첫 절 「색이 없을 때 상태를 어떻게 말하는가」의 다섯 수단(반전·테두리·크기굵기·채움정도·opacity)에 통째로 얹혀 있었다. `tokens.md` v2가 무채색 램프와 브랜드 색을 도입하면서 그 전제가 사라졌다.

| | v1 | v2 |
|---|---|---|
| 주 버튼 | `ink` 채움 (흑 반전) | `brand` 채움 |
| 표 선택 행 | 반전 (흑 채움 + 백 글자) | `brand.tint` 바탕 |
| 유형 배지 | `signal` 채움 | 연한 틴트 + 진한 라벨 |
| 스켈레톤 | **금지** (회색 의존이라) | 허용 |
| 비활성 | `opacity: .4` | `text.disabled` + `opacity: .6` |

살아남은 것: OutboxDot의 채움 정도 · "선을 덜 긋는다" · `danger`는 확인 모달 안에서만 · 네이티브 `<select>` 사용 · 상태를 색으로만 구분하지 않기.

## 어디에 두나

| 폴더 | 기준 | 예 |
|---|---|---|
| `components/ui/` | 도메인을 **모른다.** 강의실·슬롯·전송을 몰라도 동작한다 | Button, Table, Modal, Badge |
| `components/domain/` | 도메인을 **안다.** 서버 필드명과 업무 규칙이 들어 있다 | OutboxDot, TypeBadge, SlotForm |
| `views/` 옆 | 한 화면에만 있다 | WeekGrid (페이지2 격자) |

경계가 헷갈리면 **"이 컴포넌트가 `schemas.py`를 알아야 하나"**로 가른다. 알아야 하면 `domain/`이다.

## 위계를 만드는 수단

v2에서 쓸 수 있는 수단은 다섯이고, 이 밖으로 나가지 않는다.

| 수단 | 쓰는 곳 |
|---|---|
| **면** (`surface` vs `sunken`) | 사이드바·표 헤더를 본문에서 떼어낼 때 |
| **선** (`line.1` / `.2` / `.3`) | 행 구분 / 컨테이너 경계 / 입력 테두리 — 굵기가 아니라 **단계**로 고른다 |
| **크기·굵기** | 본문 안의 위계. `text.2`·`text.3`로 내리기 전에 크기부터 내린다 |
| **`brand` 1색** | 1차 액션과 활성 상태 **전용**. 화면당 채워진 brand 버튼은 하나 |
| **적색 라벨** | 사용중·파괴적 동작. 면이 아니라 라벨에 |

**회색을 색으로 쓰지 않는다.** `gray.400` 이하는 텍스트에 못 쓴다(`tokens.md` 대비표). 흐리게 보이길 원하면 크기와 굵기를 먼저 내린다.

---

# 기본 — `components/ui/`

## Button

| prop | 값 | 기본 |
|---|---|---|
| `variant` | `primary` / `secondary` / `danger` / `ghost` | `primary` |
| `size` | `sm` / `md` | `md` |
| `disabled` | boolean | `false` |
| `loading` | boolean | `false` |
| `loadingLabel` | string | — |
| `type` | `button` / `submit` | `button` |

| variant | 평상시 | hover | 용도 |
|---|---|---|---|
| `primary` | `brand` 채움 + `gray.0` 글자 | 10% 어둡게 | 저장·추가 — **화면당 하나** |
| `secondary` | `surface` + `line.3` 1px + `text.1` | 바탕 `sunken` | 취소·CSV·동기화 |
| `danger` | `danger` 채움 + `gray.0` 글자 | 10% 어둡게 | 삭제 — **확인 모달 안에서만** |
| `ghost` | 바탕·테두리 없음, `text.1` | 바탕 `sunken` | 표 행의 인라인 동작 |

- 높이 `control.height.sm` / `.md`. 패딩 `space.2` `space.4`. 라운드 `radius.md`. 굵기 `medium`.
- `disabled`: 글자 `text.disabled`, 바탕은 `opacity: .6`, `cursor: not-allowed`. **색상(hue)을 바꾸지 않는다.**
- `loading`: 라벨을 유지한 채 앞에 회전 마크를 붙이고 `disabled`처럼 잠근다. 라벨을 "저장 중…"으로 바꾸지 않는다 — 버튼 너비가 흔들린다. 다만 **진행도가 있으면** `loadingLabel`로 바꾼다("3/7 적용 중"). 이때 너비는 가장 긴 문자열 기준으로 미리 잡는다.
- 포커스: `outline: 2px solid var(--focus); outline-offset: 2px`.
- **`danger`를 목록이나 표에 바로 노출하지 않는다.** 표의 삭제는 `ghost`이고, 적색은 확인 모달에서만 나온다. 적색이 화면에 흔해지면 "사용중" 상태와 섞인다.

## Select

| prop | 값 | 기본 |
|---|---|---|
| `modelValue` | string \| number | — |
| `options` | `{ value, label, disabled? }[]` | — |
| `label` | string | — |
| `placeholder` | string | — |
| `disabled` | boolean | `false` |
| `size` | `sm` / `md` | `md` |

**네이티브 `<select>`를 쓴다.** 커스텀 드롭다운을 만들지 않는다 — 키보드·스크린리더·모바일 휠 피커를 공짜로 얻는다. 화살표만 배경 이미지로 갈아 끼운다.

높이·라운드·테두리는 Input과 같다. 옵션이 30개를 넘으면(건물의 강의실 목록 등) Select 대신 검색 가능한 목록을 쓸 것 — 그건 별도 컴포넌트이고 필요해질 때 추가한다.

## Input · Textarea

| prop | 값 | 기본 |
|---|---|---|
| `modelValue` | string \| number | — |
| `label` | string | — |
| `hint` | string | — |
| `error` | string | — |
| `required` | boolean | `false` |
| `disabled` | boolean | `false` |
| `size` | `sm` / `md` | `md` |
| `maxBytes` | number | — |

- 높이 `control.height.*`. 테두리 `line.3` 1px, 라운드 `radius.sm`.
- `label`: 위에 `font.size.sm` + `regular`, `text.2`. `required`면 라벨 뒤에 `*` (`danger`).
- `hint`: 아래 `font.size.xs`, `text.3`.
- `error`: `hint` 자리를 **대체**하고 글자 `danger`, 테두리 `danger` 2px. hint와 error를 동시에 보이지 않는다 — 자리가 하나다.
- 포커스: `focus` 2px outline. 에러와 겹치면 outline만 남긴다.
- **`maxBytes`는 글자 수가 아니라 UTF-8 바이트를 센다.** `subject`·`professor`가 바이트 상한(`P.SUBJ_MAX`/`P.PROF_MAX`)이라 글자 수로 세면 한글에서 서버가 튕긴다. 남은 양을 `12 / 24 B`로 hint 자리에 우측 정렬해 보여주고, 넘으면 입력을 막는다.
- 시각 입력(`s_h`/`s_m`)은 `font-variant-numeric: tabular-nums`.

## Checkbox

| prop | 값 | 기본 |
|---|---|---|
| `modelValue` | boolean \| array | — |
| `value` | any | — |
| `label` | string | — |
| `indeterminate` | boolean | `false` |
| `disabled` | boolean | `false` |

16px 사각, 라운드 `radius.sm`, 테두리 `line.3`. 체크되면 `brand` 채움 + `gray.0` 체크. `indeterminate`는 `brand` 채움 + 가로 막대(전체 선택이 부분일 때).

클릭 영역은 라벨까지 포함하고 세로로 최소 28px를 잡는다. 학생 웹에서는 48px.

## Table

| prop | 값 | 기본 |
|---|---|---|
| `columns` | `{ key, label, align?, width?, sticky? }[]` | — |
| `rows` | `object[]` | — |
| `rowKey` | string | `'id'` |
| `selected` | `string[]` | `[]` |
| `loading` | boolean | `false` |
| `empty` | string | `'항목이 없습니다'` |
| `expandable` | boolean | `false` |

- **선을 덜 긋는다.** `thead` 아래에 `line.2` 2px, 행 사이 `line.1` 1px. **세로 구분선은 긋지 않는다** — 열은 정렬과 `space.3` 이상의 여백으로 나뉜다.
- 헤더: `font.size.xs` + `bold`, `text.2`, 자간 `.06em`. 바탕 `sunken`.
- 본문: `font.size.sm`, `text.1`. 숫자 열은 `tabular-nums` + 우측 정렬.
- 행 높이 32px. 두 줄 셀이 있으면 44px.
- **선택된 행: `brand.tint` 바탕.** (v1의 반전을 버렸다 — 반전은 행이 많을 때 화면을 뒤덮는다)
- hover: 바탕 `sunken`.
- `loading`: 헤더는 그대로 두고 본문 자리에 Skeleton 행 5개.
- 행이 없으면 EmptyState.
- `expandable`: 행 좌측에 펼침 삼각형. 펼친 내용은 `sunken` 바탕으로 한 단 들여쓴다. 시험기간 표의 "같은 기간 묶기"가 이걸 쓴다.
- **모바일 대응을 넣지 않는다.** 관리자 웹은 데스크톱 전용이다(`README.md`). 학생 웹은 Table을 쓰지 않고 ListRow를 쓴다.

## Badge

| prop | 값 | 기본 |
|---|---|---|
| `variant` | `solid` / `tint` / `outline` | `tint` |
| `tone` | `neutral` / `busy` / `danger` / `brand` | `neutral` |
| `size` | `xs` / `sm` | `xs` |

| tone × variant | 바탕 | 테두리 | 글자 |
|---|---|---|---|
| `busy` + `tint` | `room.busy.fill` | `room.busy.line` | `room.busy.label` |
| `neutral` + `outline` | 없음 | `line.3` | `text.2` |
| `neutral` + `solid` | `sunken` | 없음 | `text.1` |
| `danger` + `outline` | 없음 | `danger` | `danger` |

`font.size.xs` + `bold`, 패딩 `2px space.2`, 라운드 `radius.sm`. 라벨 텍스트는 **반드시 있다** — 색칠된 점만으로 상태를 표현하는 배지를 만들지 않는다.

## Modal

| prop | 값 | 기본 |
|---|---|---|
| `open` | boolean | `false` |
| `title` | string | — |
| `size` | `sm` / `md` / `lg` | `md` |
| `closeOnBackdrop` | boolean | `true` |

- 배경: `gray.800` `opacity: .45`. **블러 없음.**
- 패널: `surface`, `radius.lg`, 최대 폭 `sm` 400 / `md` 560 / `lg` 800px. 그림자 없음(`tokens.md`) — 배경 딤이 층을 진다.
- 헤더(`title`, `font.size.lg` + `bold`) / 본문 / 푸터(버튼 우측 정렬, `space.2` 간격).
- Esc와 배경 클릭으로 닫힌다. 단 **입력값이 바뀐 폼은 배경 클릭으로 닫지 않는다** — `closeOnBackdrop: false`로 내리고 닫기 전 확인한다.
- 열릴 때 첫 입력에 포커스, 닫힐 때 열었던 버튼으로 되돌린다. 포커스는 패널 안에 가둔다.
- **확인 모달**은 `size: sm` + 본문에 지울 대상을 그대로 적고(“월 09:00 캡스톤디자인”) 푸터에 `secondary 취소` + `danger 삭제`.

## Toast

| prop | 값 | 기본 |
|---|---|---|
| `tone` | `neutral` / `danger` | `neutral` |
| `message` | string | — |
| `action` | `{ label, onClick }` | — |
| `duration` | number (ms) | `5000` |

- 바탕 `surface`, 테두리 `line.2` 1px, `radius.md`. 우상단에서 쌓인다(최대 3개, 넘으면 오래된 것부터 밀어낸다).
- `danger`만 왼쪽에 `danger` 3px 띠를 세운다. **성공에는 색을 쓰지 않는다** — 문구로 구분한다("저장했습니다").
- `danger`는 자동으로 사라지지 않는다(`duration: 0`). 에러를 놓치면 안 된다.
- `action`은 `ghost` 버튼("재시도", "실행 취소").
- **서버 에러 원문을 그대로 노출하지 않는다.** 409는 "이 슬롯은 웹에서 수정된 행입니다. CSV로 덮어쓸 수 없습니다."처럼 사람 문장으로 바꾼다(`screens/admin-rooms.md` §1).

## Banner

| prop | 값 | 기본 |
|---|---|---|
| `tone` | `neutral` / `danger` | `neutral` |
| `message` | string | — |
| `dismissible` | boolean | `true` |
| `storageKey` | string | — |

화면 상단 전체 폭. 바탕 `sunken`, 아래 `line.2` 1px. Toast와 달리 **페이지에 붙어 있고 스스로 사라지지 않는다.**

`storageKey`가 있으면 닫은 사실을 `localStorage`에 남겨 다시 띄우지 않는다. 관리자 웹의 좁은 폭 안내("관리자 화면은 1024px 이상에서 쓰도록 만들어졌습니다")가 이걸 쓴다.

## EmptyState

| prop | 값 | 기본 |
|---|---|---|
| `message` | string | — |
| `actions` | `{ label, variant, onClick }[]` | `[]` |

가운데 정렬, `text.2`, `font.size.sm`. 아래에 버튼 최대 2개. **일러스트·아이콘을 넣지 않는다.**

문구는 무엇이 없는지와 다음에 무엇을 할지를 같이 말한다: "이 건물에 등록된 시간표가 없습니다" + `CSV 가져오기` · `슬롯 추가`.

## Skeleton

| prop | 값 | 기본 |
|---|---|---|
| `variant` | `text` / `block` | `text` |
| `rows` | number | `1` |
| `width` | string | `'100%'` |

`gray.50` 바탕, `radius.sm`, 1.4s 펄스(`gray.50` ↔ `gray.100`). `text`는 높이 `font.size.md`, 줄 간격 `space.2`, 마지막 줄은 60% 폭.

**v1에서 금지했던 것을 되살렸다** — 회색이 생겨서 성립한다. 다만 로딩이 1초 미만으로 예상되는 자리에는 쓰지 않는다(깜빡임이 더 거슬린다).

## SidebarNav

| prop | 값 | 기본 |
|---|---|---|
| `items` | `{ to, label }[]` | — |
| `footer` | slot | — |

폭 220px, 바탕 `sunken`, 우측 `line.2` 1px. 항목 높이 32px, 라운드 `radius.md`, 패딩 `space.2` `space.3`, `font.size.md`.

- 평상시 `text.2`, hover 바탕 `gray.50`.
- **활성: 바탕 `brand.tint` + 글자 `brand` + `medium`.** 활성 표시는 `brand`를 쓰는 두 자리 중 하나다(다른 하나는 1차 버튼).
- `footer` 슬롯은 아래에 붙는다 — 모뎀Pi 연결 상태가 들어간다.

## StatTile

| prop | 값 | 기본 |
|---|---|---|
| `label` | string | — |
| `value` | string \| number | — |
| `unit` | string | — |
| `sub` | string | — |
| `tone` | `neutral` / `danger` | `neutral` |

테두리 `line.2` 1px, `radius.md`, 패딩 `space.4`. 라벨 `font.size.sm`/`text.3` → 값 `font.size.xl` + `bold` + `tabular-nums` → `sub` `font.size.xs`/`text.3`.

`unit`은 값보다 작고(`font.size.sm`) `text.2`다. `tone: danger`는 **값 글자만** `danger`로 바꾼다 — 타일을 통째로 칠하지 않는다.

`sub`에 비교값을 적는다("지난주 21.2초", "목표 95% · 미달"). **추세 화살표를 넣지 않는다** — 좋아진 건지 나빠진 건지는 지표마다 달라서 화살표 방향이 거짓말을 한다.

## Legend

| prop | 값 | 기본 |
|---|---|---|
| `series` | `{ label, color }[]` | — |

가로 나열, 9px 사각 마크(`radius.sm`) + `font.size.xs` `text.2` 라벨. **글자는 계열색을 입지 않는다**(`tokens.md` §chart 규칙 5).

계열이 2개 이상이면 항상 둔다. 1개면 두지 않는다 — 제목이 이름을 진다.

---

# 도메인 — `components/domain/`

## OutboxDot

| prop | 값 | 기본 |
|---|---|---|
| `state` | `queued` / `dispatched` / `acked` / `failed` / `cancelled` / `scheduled` | — |

8px 원, `radius.full`. 색이 아니라 **채움 정도**로 단계를 읽는다 — 표기와 색은 `tokens.md` §outbox 그대로.

`scheduled`는 서버 상태가 아니라 화면이 만드는 값이다. 예약이 7일 지평 밖이라 `outbox_ids`가 빈 배열로 왔을 때 쓴다 — 점 대신 `예정` Badge(`neutral`+`outline`)를 놓고 툴팁에 "7일 이내로 들어오면 자동 전송됩니다". **빈 `outbox_ids`를 실패로 그리지 않는다.**

모든 상태에 `title`(툴팁)을 단다. 점 하나는 색맹이 아니라도 의미를 알 수 없다.

## TypeBadge

| prop | 값 | 기본 |
|---|---|---|
| `type` | 1–6 (`SlotIn.type`) | — |

| type | 라벨 | tone |
|---|---|---|
| 1 `CLASS` | 수업중 | `busy` |
| 2 `EXAM` | 시험중 | `busy` |
| 5 `SPECIAL` | 특강 | `busy` |
| 6 `RENTAL` | 대여중 | `busy` |
| 3 `CANCELLED` | 휴강 | `neutral` + `outline` |
| 4 `EMPTY` | 빈강의실 | `neutral` + `outline` |

**넷을 색으로 나누지 않는다.** 1·2·5·6은 전부 같은 `busy`이고 구분은 라벨이 한다(e-Paper RED 이분법과 1:1). 이 매핑을 화면마다 다시 쓰지 않도록 컴포넌트가 진다.

## SourceBadge

| prop | 값 | 기본 |
|---|---|---|
| `source` | 1 / 2 / 3 (`SlotIn.source`) | — |

1 `포털`(`neutral`+`outline`) · 2 `수동`(`neutral`+`solid`) · 3 `긴급`(`danger`+`outline`).

이게 없으면 CSV 임포트 후 "왜 이 행만 안 바뀌지"를 설명할 수 없다(`screens/admin-rooms.md` §1).

## SlotForm

| prop | 값 | 기본 |
|---|---|---|
| `mode` | `create` / `edit` | `create` |
| `roomId` | number | — |
| `value` | `SlotIn \| null` | `null` |
| `existing` | `SlotOut[]` | `[]` |

Modal 안에 들어가는 폼. **페이지1 표와 페이지2 셀이 같은 것을 쓴다** — 편집 경로가 둘인데 검증이 갈라지면 같은 데이터가 경로마다 다르게 들어간다.

필드: `강의실` Select · `요일` Select(월~일) · `시작`·`종료`(시·분) · `과목명` Input(`maxBytes`) · `교수` Input(`maxBytes`) · `유형` Select(1–6).

컴포넌트가 지는 검증:

1. **겹침** — `existing` 중 같은 `day`에서 시간 구간이 겹치면 저장을 막는다. 서버는 같은 키(`day`+`s_h`+`s_m`)만 막으므로 09:00–11:00과 10:00–12:00이 둘 다 들어간다.
2. **종료 > 시작** — 자정을 넘기는 슬롯은 만들지 않는다.
3. **바이트 상한** — Input의 `maxBytes`가 진다.
4. **키 변경** — `mode: edit`에서 `day`·`s_h`·`s_m`이 바뀌면 `PUT`만으로는 옛 행이 남는다. **삭제 후 추가**로 처리하고, 그 사실을 사용자에게 알리지 않는다(내부 구현이다).
5. **`source` 상승 안내** — 기존 슬롯의 `source`가 1이면 hint에 "저장하면 이 슬롯은 수동 편집으로 바뀌어 CSV 임포트에 덮이지 않습니다."

저장은 `source: 2`로 보낸다.

## ResvForm

`SlotForm`과 같은 골격에 `요일` 대신 `날짜`가 들어간다. `요일`은 날짜에서 계산해 **읽기 전용으로 표시**한다 — 서버 필드가 아니다.

추가로 지는 것:

- **id 채번** — `ResvIn.id`(1–65535)는 화면이 채운다. 전역 PK라 사용 중이지 않은 최소값을 **전역 범위**에서 고른다. 목록을 못 받았으면 저장 버튼을 잠근다.
- **7일 지평 안내** — 날짜가 오늘+7일 밖이면 hint에 "7일 이내로 들어오면 자동 전송됩니다". **막지는 않는다.**

## ExamForm

| prop | 값 | 기본 |
|---|---|---|
| `buildingId` | number | — |
| `rooms` | `RoomOut[]` | — |
| `value` | `ExamIn \| null` | `null` |

필드: `강의실`(**다중 선택** Checkbox 목록 + 전체 선택) · `시작일` · `종료일`.

- 저장하면 고른 강의실 수만큼 `POST /rooms/{id}/exams`를 보낸다. 벌크 엔드포인트는 없다.
- **id는 강의실마다 따로 채번한다.** 전역 PK라 같은 번호를 여러 강의실에 쓰면 서로 덮어쓴다.
- 진행 중 버튼은 `loadingLabel`로 "3/7 적용 중".
- **일부 실패해도 되돌리지 않는다.** Toast에 "7개 중 5개 적용 · 402호, 405호 실패"로 알리고 실패분만 재시도로 남긴다.

---

# 차트 — `components/chart/`

## Histogram

| prop | 값 | 기본 |
|---|---|---|
| `buckets` | `{ label, values: number[] }[]` | — |
| `series` | `{ label }[]` | — |
| `marker` | `{ at: number, label: string }` | — |
| `yMax` | number | 자동 |

`tokens.md` §chart 규칙을 그대로 따른다.

- 계열색은 `chart.series.1~3`을 **고정 순서**로 배정한다. 필터로 계열 수가 바뀌어도 남은 계열의 색을 다시 칠하지 않는다.
- **4계열 이상 받지 않는다.** props에서 막는다 — 파랑↔보라가 적녹색약에서 ΔE 1.8로 붙는다.
- 막대: 폭 15px, 같은 bucket 안 계열 간격 2px, 상단만 `radius.sm`, 바닥은 축에 붙는다.
- 격자선 `chart.grid`, 축선 `chart.axis`, 눈금·라벨 `chart.text`.
- **값 라벨은 계열마다 가장 큰 막대에만** 붙인다. 모든 막대에 숫자를 적지 않는다.
- `marker`는 세로 점선(`line.3`) + `text.3` 라벨. SLA 30초 선이 이걸 쓴다.
- **축은 하나다.** 좌우 y축을 만들지 않는다.
- 계열이 2개 이상이면 Legend를 함께 둔다.

호버 툴팁은 필요해질 때 추가한다 — 지금 대시보드는 정적 요약이라 없어도 읽힌다.

---

# 미결

1. **폼 라이브러리를 쓸지** — 검증 규칙이 SlotForm·ResvForm·ExamForm에 겹친다. wj가 구현하며 판단한다. 이 문서는 인터페이스만 정하고 내부 구현을 지정하지 않는다
2. **Select 30개 초과** — 건물에 강의실이 많으면 네이티브 Select가 버겁다. 검색 가능한 목록이 필요해지면 그때 추가한다
3. **Histogram 호버** — 위 참고
4. 학생 웹 전용 컴포넌트(`RoomListRow`·`RoomNowCard`·`WeekBar`)는 `screens/student-room.md`에 정의돼 있다. 안정되면 이 문서로 옮긴다
