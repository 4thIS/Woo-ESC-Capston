import pytest
from assistant_proto import FIRST_PREFIX, canonical_json

from esc_ml.records import Example
from esc_ml.train import data_digest, to_prompt_completion

EX = Example(
    "g1",
    "train",
    "cancel/01",
    "2026-11-25T10:00:00+09:00",
    FIRST_PREFIX,
    "취소",
    {"v": 1, "intent": "cancel", "target": {}, "set": {}},
)


class FakeTok:
    """토크나이저가 BOS 를 스스로 붙이는 경우."""

    bos_token = "<bos>"
    bos_token_id = 2
    add_bos = True

    def __call__(self, text):
        return {"input_ids": ([self.bos_token_id] if self.add_bos else []) + [9]}

    def apply_chat_template(
        self, msgs, tokenize=False, add_generation_prompt=False, enable_thinking=False
    ):
        s = "<bos>" + "".join(f"<{m['role']}>{m['content']}<end>" for m in msgs)
        return s + ("<assistant>" if add_generation_prompt else "")


class NoBosTok(FakeTok):
    """Gemma 4 처럼 add_bos_token=False — chat template 의 <bos> 가 유일한 BOS."""

    add_bos = False


class BadTok(FakeTok):
    def apply_chat_template(
        self, msgs, tokenize=False, add_generation_prompt=False, enable_thinking=False
    ):
        out = super().apply_chat_template(msgs, tokenize, add_generation_prompt, enable_thinking)
        return out.replace("<assistant>", "<model>") if add_generation_prompt else out


def test_prompt_completion_split():
    pc = to_prompt_completion(FakeTok(), EX)
    assert not pc["prompt"].startswith("<bos>")  # 토크나이저가 BOS 를 다시 붙인다
    assert pc["prompt"].endswith("<user>관리자: 취소<end><assistant>")
    assert pc["completion"] == canonical_json(EX.form) + "<end>"


def test_prompt_keeps_bos_when_tokenizer_does_not_add():
    pc = to_prompt_completion(NoBosTok(), EX)
    assert pc["prompt"].startswith("<bos>")  # 지우면 학습·생성 입력이 한 토큰 어긋난다(#173)


def test_template_mismatch_raises():
    with pytest.raises(ValueError):
        to_prompt_completion(BadTok(), EX)


def test_data_digest_changes_with_content(tmp_path):
    p = tmp_path / "a.jsonl"
    p.write_text("x\n", encoding="utf-8")
    d1 = data_digest([p])
    p.write_text("y\n", encoding="utf-8")
    assert d1 != data_digest([p]) and len(d1) == 12


def test_longest_tokens_counts_prompt_and_completion():
    from esc_ml.train import longest_tokens

    class LenTok:
        def __call__(self, text, add_special_tokens=False):
            return {"input_ids": list(range(len(text)))}

    rows = [{"prompt": "ab", "completion": "c"}, {"prompt": "abcd", "completion": "ef"}]
    assert longest_tokens(LenTok(), rows) == 6
