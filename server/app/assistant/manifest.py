"""모델 안내 (공통 부록 §4.1). model.json 은 릴리스 PR 이 바꾸는 유일한 파일이다 —
runtime·repo·revision·files·generation 만 거기 있고, 지시문·출력 문법·접두어는 assistant_proto 에서 채운다."""

from __future__ import annotations

import json
import re
from pathlib import Path

from assistant_proto import FIRST_PREFIX, SCHEMA_VERSION, SYSTEM_PROMPT, json_schema

MODEL_FILE = Path(__file__).with_name("model.json")
RUNTIMES = ("webllm", "transformers", "litert", "wllama")
DEFAULT_GENERATION = {"temperature": 0, "max_tokens": 256}
_REV = re.compile(r"^[0-9a-f]{40}$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_REPO = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")


def _read(path: Path | None) -> dict:
    d = json.loads((path or MODEL_FILE).read_text(encoding="utf-8"))
    if not isinstance(d, dict):
        raise ValueError("model.json 은 객체여야 합니다")  # noqa: TRY004
    return d


def _safe_name(n: object) -> bool:
    """내려받을 파일 이름 — 상대 경로만, 위로 거슬러 오르지 않는다."""
    return (
        isinstance(n, str)
        and bool(n)
        and not n.startswith(("/", "\\"))
        and ":" not in n
        and ".." not in n.replace("\\", "/").split("/")
    )


def _valid_file(f: object) -> bool:
    return (
        isinstance(f, dict)
        and _safe_name(f.get("name"))
        and isinstance(f.get("size"), int)
        and not isinstance(f["size"], bool)
        and f["size"] > 0
        and isinstance(f.get("sha256"), str)
        and bool(_SHA.match(f["sha256"]))
    )


def load(path: Path | None = None) -> dict:
    d = _read(path)
    if d.get("enabled") is not True:
        if d.get("enabled") in (None, False):
            return {"enabled": False}
        raise ValueError("model.json 의 enabled 는 true/false 여야 합니다")
    ok = (
        d.get("runtime") in RUNTIMES
        and isinstance(d.get("repo"), str)
        and bool(_REPO.match(d["repo"]))
        and not {".", ".."} & set(d["repo"].split("/"))  # 경로 조각 '.'·'..' 금지
        and isinstance(d.get("revision"), str)
        and bool(_REV.match(d["revision"]))  # 브랜치 이름이 아니라 커밋 해시로 고정
        and isinstance(d.get("files"), list)
        and bool(d["files"])
        and all(_valid_file(f) for f in d["files"])
        and isinstance(d.get("generation", {}), dict)
    )
    if not ok:
        raise ValueError(
            "model.json 형식이 틀렸습니다 — runtime·repo·revision(40자)·files[name,size,sha256]"
        )
    return {
        "enabled": True,
        "schema_v": SCHEMA_VERSION,
        "runtime": d["runtime"],
        "repo": d["repo"],
        "revision": d["revision"],
        "files": d["files"],
        "system_prompt": SYSTEM_PROMPT,
        "first_prefix": FIRST_PREFIX,
        "json_schema": json_schema(),
        "generation": d.get("generation", DEFAULT_GENERATION),
    }


def current_revision(path: Path | None = None) -> str | None:
    """기록에 남길 모델 판. 안내가 없거나 틀렸거나 읽을 수 없으면 None — 절대 던지지 않는다."""
    try:
        m = load(path)
    except (OSError, ValueError):
        return None
    return m["revision"] if m.get("enabled") else None
