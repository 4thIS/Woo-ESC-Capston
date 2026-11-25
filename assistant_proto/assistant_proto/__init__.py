"""관리자 AI 비서 양식 규격 v1 — 단일 진실원 (spec 2026-11-25 §3, 공통 부록 §1~§3).
서버(server/app/assistant)·학습(ml/)이 경로 의존성으로 쓴다. DB·네트워크 없음."""

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

__all__ = [
    "FIELD_ORDER",
    "INTENTS",
    "SCHEMA_VERSION",
    "TYPE_LABELS",
    "Fields",
    "Form",
    "FormError",
    "canonical_json",
    "form_to_dict",
    "json_schema",
    "parse_form",
    "type_code",
]
