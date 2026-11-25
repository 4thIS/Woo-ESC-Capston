"""모델 입력 (공통 부록 §2). 시스템 메시지 = SYSTEM_PROMPT, 사용자 메시지 = 접두어 + 관리자 문장.
첫 턴 접두어는 FIRST_PREFIX, 이어지는 턴은 서버가 render_prefix 로 만들어 준다."""

from __future__ import annotations

from assistant_proto.form import ROOT

FIRST_PREFIX = "관리자: "
SYSTEM_PROMPT: str = (ROOT / "prompt" / "system.v1.txt").read_text(encoding="utf-8").strip()


def render_prefix(intent: str, items: list[tuple[str, str | None]], question: str) -> str:
    parts = [intent, *(f"{label} {'?' if value is None else value}" for label, value in items)]
    return f"상태: {' | '.join(parts)}\n질문: {question}\n{FIRST_PREFIX}"
