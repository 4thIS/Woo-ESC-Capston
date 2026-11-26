import json

import pytest

from app.assistant import manifest as M

GOOD = {
    "enabled": True,
    "runtime": "webllm",
    "repo": "owner/name",
    "revision": "a" * 40,
    "files": [{"name": "m/model.bin", "size": 10, "sha256": "b" * 64}],
}


def _write(tmp_path, d):
    p = tmp_path / "model.json"
    p.write_text(d if isinstance(d, str) else json.dumps(d), encoding="utf-8")
    return p


def test_committed_model_json_loads():
    """커밋된 model.json 은 (릴리스 PR 이 켜든 끄든) 어느 쪽이어도 검증을 통과한다."""
    m = M.load()
    assert m["enabled"] in (True, False)
    assert M.current_revision() == (m["revision"] if m["enabled"] else None)


def test_valid_manifest(tmp_path):
    p = _write(tmp_path, {**GOOD, "generation": {"temperature": 0, "max_tokens": 64}})
    m = M.load(p)
    assert m["enabled"] is True and m["generation"] == {"temperature": 0, "max_tokens": 64}
    assert M.load(_write(tmp_path, GOOD))["generation"] == M.DEFAULT_GENERATION
    assert M.current_revision(p) == "a" * 40


def _file(**kw):
    return [{"name": "m.bin", "size": 1, "sha256": "b" * 64, **kw}]


BAD = {
    "runtime": {**GOOD, "runtime": "onnx"},
    "enabled-string": {**GOOD, "enabled": "yes"},
    "enabled-one": {**GOOD, "enabled": 1},
    "repo-slash": {**GOOD, "repo": "/"},
    "repo-space": {**GOOD, "repo": "a b/c"},
    "repo-dotdot-path": {**GOOD, "repo": "a/../c"},
    "repo-three": {**GOOD, "repo": "a/b/c"},
    "repo-dot-owner": {**GOOD, "repo": "./x"},
    "repo-dotdot-name": {**GOOD, "repo": "a/.."},
    "repo-dotdot-both": {**GOOD, "repo": "../.."},
    "repo-dot-both": {**GOOD, "repo": "./."},
    "rev-branch": {**GOOD, "revision": "main"},
    "rev-upper": {**GOOD, "revision": "A" * 40},
    "files-empty": {**GOOD, "files": []},
    "name-dotdot": {**GOOD, "files": _file(name="../x")},
    "name-nested-dotdot": {**GOOD, "files": _file(name="a/../../x")},
    "name-slash": {**GOOD, "files": _file(name="/etc/x")},
    "name-backslash": {**GOOD, "files": _file(name="\\x")},
    "size-bool": {**GOOD, "files": _file(size=True)},
    "size-zero": {**GOOD, "files": _file(size=0)},
    "sha-short": {**GOOD, "files": _file(sha256="b" * 63)},
    "generation-str": {**GOOD, "generation": "hot"},
    "not-object": [],
}


@pytest.mark.parametrize("d", BAD.values(), ids=BAD.keys())
def test_invalid_manifest_fails_per_request(tmp_path, d):
    p = _write(tmp_path, d)
    with pytest.raises(ValueError):
        M.load(p)
    assert M.current_revision(p) is None  # 기록 쪽은 절대 던지지 않는다


def test_unreadable_manifest(tmp_path):
    assert M.current_revision(_write(tmp_path, "{")) is None
    assert M.current_revision(tmp_path / "missing.json") is None
    with pytest.raises(ValueError):
        M.load(_write(tmp_path, "{"))
