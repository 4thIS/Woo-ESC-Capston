"""릴리스 — 파일 목록·SHA-256, 모델 카드, HF 업로드(커밋 해시로 고정), 서버 model.json 값."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

RUNTIMES = ("webllm", "transformers", "litert", "wllama")  # 부록 §4.1
SKIP = {"README.md", ".gitattributes"}
_REV = re.compile(r"^[0-9a-f]{40}$")


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_manifest(folder) -> list[dict]:
    root = Path(folder)
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name not in SKIP)
    return [
        {"name": p.relative_to(root).as_posix(), "size": p.stat().st_size, "sha256": _sha256(p)}
        for p in files
    ]


def model_json(
    runtime: str,
    repo: str,
    revision: str,
    files: list[dict],
    temperature: float = 0,
    max_tokens: int = 256,
) -> dict:
    if runtime not in RUNTIMES:
        raise ValueError(f"runtime 은 {RUNTIMES} 중 하나: {runtime}")
    if not _REV.match(revision):
        raise ValueError("revision 은 40자 커밋 해시여야 한다 (브랜치·태그 이름 금지)")
    return {
        "enabled": True,
        "runtime": runtime,
        "repo": repo,
        "revision": revision,
        "files": files,
        "generation": {"temperature": temperature, "max_tokens": max_tokens},
    }


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def render_card(version: str, base_model: str, runtime: str, summary: dict, n_train: int) -> str:
    lat = summary.get("latency_mean_ms")
    return f"""---
license: apache-2.0
base_model: {base_model}
language: [ko]
tags: [gemma4, lora, structured-output]
---

# ESC 관리자 AI 비서 — 문장 → 양식 해석 모델 v{version}

대학 강의실 게시 시스템(ESC)의 관리자 채팅 문장을 정해진 양식(JSON) 한 줄로 옮기는 모델이다.
날짜 계산·검증·적용은 서버가 하고, 이 모델은 문장 속 표현을 칸에 옮기기만 한다.

- 기반: `{base_model}` + LoRA 파인튜닝, 병합 후 양자화 (실행 도구: {runtime})
- 라이선스: Apache-2.0 (기반 모델 라이선스를 따른다)
- 입력: 시스템 지시문 + `관리자: <문장>` (대화 중이면 서버가 준 상태 접두어). 출력: 양식 JSON 한 줄

## 학습 데이터

- 문장 틀 × **가상** 값(가상 건물·강의실·과목·교수·학생)으로 만든 예문과, 그 예문을 Claude 로 표현만 바꾼 변형 — 총 {n_train:,}문장
- 실제 사람·학교 이름, 실제 운영 기록은 들어 있지 않다.
- 시험 문장(사람이 쓴 약 300문장)은 학습에 쓰지 않았다.

## 평가 (사람 시험 문장 + 계약 예문 {summary["n"]}문장, 이 양자화 모델)

| 지표 | 값 |
|---|---|
| intent 정확도 | {_pct(summary["intent_acc"])} |
| 칸 정확도 | {_pct(summary["field_acc"])} |
| 양식 전체 일치 | {_pct(summary["exact_acc"])} |
| 형식 오류 | {_pct(summary["format_err"])} |
| 위험 오류(추가·수정 → 삭제) | {_pct(summary["danger_rate"])} |
| 평균 응답 (학과 관리자 PC) | {f"{lat:.0f} ms" if lat is not None else "—"} |

## 한계

- 정해진 18가지 작업 밖의 요청은 `unknown` 으로 낸다.
- 출력은 제안일 뿐이며, 서버 검증과 관리자 확인 화면을 거쳐서만 반영된다.
"""


def upload_model(folder, repo: str, tag: str) -> str:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(repo, repo_type="model", exist_ok=True)
    info = api.upload_folder(
        folder_path=str(folder), repo_id=repo, repo_type="model", commit_message=f"release {tag}"
    )
    api.create_tag(repo, tag=tag, revision=info.oid, repo_type="model")
    return info.oid


def upload_data(folder, repo: str) -> str:
    from huggingface_hub import HfApi

    api = HfApi()
    api.create_repo(repo, repo_type="dataset", private=True, exist_ok=True)
    info = api.upload_folder(
        folder_path=str(folder), repo_id=repo, repo_type="dataset", path_in_repo=Path(folder).name
    )
    return info.oid


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m esc_ml.release", description="릴리스 도우미")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest")
    m.add_argument("--folder", type=Path, required=True)
    c = sub.add_parser("card")
    c.add_argument("--version", required=True)
    c.add_argument("--base", default="google/gemma-4-E2B-it")
    c.add_argument("--runtime", required=True, choices=RUNTIMES)
    c.add_argument("--summary", type=Path, required=True)
    c.add_argument("--n-train", type=int, required=True)
    c.add_argument("--out", type=Path, required=True)
    um = sub.add_parser("upload-model")
    um.add_argument("--folder", type=Path, required=True)
    um.add_argument("--repo", required=True)
    um.add_argument("--tag", required=True)
    ud = sub.add_parser("upload-data")
    ud.add_argument("--folder", type=Path, required=True)
    ud.add_argument("--repo", required=True)
    mj = sub.add_parser("model-json")
    mj.add_argument("--folder", type=Path, required=True)
    mj.add_argument("--runtime", required=True, choices=RUNTIMES)
    mj.add_argument("--repo", required=True)
    mj.add_argument("--revision", required=True)
    mj.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(argv)

    if a.cmd == "manifest":
        print(json.dumps(file_manifest(a.folder), ensure_ascii=False, indent=1))
    elif a.cmd == "card":
        summary = json.loads(a.summary.read_text(encoding="utf-8"))
        a.out.write_text(
            render_card(a.version, a.base, a.runtime, summary, a.n_train), encoding="utf-8"
        )
    elif a.cmd == "upload-model":
        print(upload_model(a.folder, a.repo, a.tag))
    elif a.cmd == "upload-data":
        print(upload_data(a.folder, a.repo))
    else:
        data = model_json(a.runtime, a.repo, a.revision, file_manifest(a.folder))
        a.out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
