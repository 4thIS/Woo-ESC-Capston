## 무엇을

(이 변경이 한 일을 한 문장으로)

## 왜

(이슈 링크 또는 spec/plan 링크)

## 어떻게 검증했는지

- [ ] 로컬에서 실제 동작 확인
- [ ] 테스트 추가/수정 (커밋에 반영)
- [ ] 검증 명령 결과 첨부 (아래)

바꾼 영역의 명령만 남기고 나머지는 지웁니다.

```
# firmware
pio test -e native                        → ... passed
pio check -e terminal                     → clean

# server
uv run pytest -q                          → ... passed
uv run ruff check . && uv run ruff format --check .   → clean

# web
pnpm test                                 → ... passed
pnpm lint && pnpm exec vue-tsc --noEmit   → clean
```

하드웨어 동작(라디오 수신률·딥슬립 전류 등)을 건드렸다면 스펙 §10.2 벤치 결과를 첨부합니다.

## 체크리스트

- [ ] 담당자 브랜치(`cw`/`dh`/`wj`/`mh`) 또는 `feature/`·`fix/` 브랜치에서 작업 (`main` 직접 커밋 안 함)
- [ ] Conventional Commits 형식 (`feat(firmware)`, `fix(server)`, `style(web)` 등)
- [ ] 자기 영역만 수정 — 타 영역 수정 시 이유 명시
- [ ] 비밀키·`.env` 미포함
- [ ] pre-commit 훅 통과
- [ ] 계약(`lora_proto/` 프로토콜 정의, DB 마이그레이션, 서버 응답 스키마) 변경이 있다면: 계약 PR을 **먼저** 머지했는가(lockstep)

## BREAKING CHANGE?

- [ ] 있음 — 무엇이 깨지는지, 어떻게 대응할지 본문에 서술
- [ ] 없음
