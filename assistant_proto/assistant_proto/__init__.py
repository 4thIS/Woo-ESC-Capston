"""관리자 AI 비서 양식 규격 v1 — 단일 진실원 (spec 2026-11-25 §3, 공통 부록 §1~§3).
서버(server/app/assistant)·학습(ml/)이 경로 의존성으로 쓴다. DB·네트워크 없음."""

from assistant_proto import rules
from assistant_proto.form import (
    FIELD_ORDER,
    INTENTS,
    SCHEMA_VERSION,
    TYPE_LABELS,
    Fields,
    Form,
    FormError,
    canonical_json,
    form_to_dict,
    json_schema,
    parse_form,
    type_code,
)
from assistant_proto.prompt import FIRST_PREFIX, SYSTEM_PROMPT, render_prefix
from assistant_proto.resolve import (
    TimeSpan,
    When,
    normalize_room,
    resolve_time,
    resolve_weekdays,
    resolve_when,
)

__all__ = [
    "FIELD_ORDER",
    "FIRST_PREFIX",
    "INTENTS",
    "SCHEMA_VERSION",
    "SYSTEM_PROMPT",
    "TYPE_LABELS",
    "Fields",
    "Form",
    "FormError",
    "TimeSpan",
    "When",
    "canonical_json",
    "form_to_dict",
    "json_schema",
    "normalize_room",
    "parse_form",
    "render_prefix",
    "resolve_time",
    "resolve_weekdays",
    "resolve_when",
    "rules",
    "type_code",
]
