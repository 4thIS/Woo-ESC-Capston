import hashlib

import pytest

from esc_ml.release import file_manifest, model_json, render_card

REV = "0123456789abcdef0123456789abcdef01234567"


def test_file_manifest(tmp_path):
    (tmp_path / "a.gguf").write_bytes(b"abc")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "b.bin").write_bytes(b"xy")
    (tmp_path / "README.md").write_text("card", encoding="utf-8")
    (tmp_path / ".gitattributes").write_text("*", encoding="utf-8")
    got = file_manifest(tmp_path)
    assert got == [
        {"name": "a.gguf", "size": 3, "sha256": hashlib.sha256(b"abc").hexdigest()},
        {"name": "sub/b.bin", "size": 2, "sha256": hashlib.sha256(b"xy").hexdigest()},
    ]


def test_model_json_shape():
    files = [{"name": "a.gguf", "size": 3, "sha256": "x" * 64}]
    got = model_json("wllama", "org/esc-assistant-e2b", REV, files)
    assert got == {
        "enabled": True,
        "runtime": "wllama",
        "repo": "org/esc-assistant-e2b",
        "revision": REV,
        "files": files,
        "generation": {"temperature": 0, "max_tokens": 256},
    }


def test_model_json_rejects_bad_values():
    with pytest.raises(ValueError):
        model_json("onnx", "org/x", REV, [])
    with pytest.raises(ValueError):
        model_json("wllama", "org/x", "main", [])


def test_card_mentions_metrics_and_data():
    s = {
        "n": 320,
        "intent_acc": 0.985,
        "field_acc": 0.961,
        "exact_acc": 0.93,
        "format_err": 0.0,
        "danger_rate": 0.0,
        "latency_mean_ms": 2100.0,
        "latency_p90_ms": 3200.0,
    }
    md = render_card("1.0.0", "google/gemma-4-E2B-it", "wllama", s, n_train=9000)
    assert "98.5%" in md and "가상" in md and "Apache-2.0" in md and "1.0.0" in md
