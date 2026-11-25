"""0단계 묶음(suites/spike.json) 만들기 — 임시 지시문·스키마·20문장. form.gbnf 가 있으면 함께 넣는다."""

import json
import pathlib

HERE = pathlib.Path(__file__).parent


def main() -> None:
    lines = (HERE / "spike_examples.jsonl").read_text(encoding="utf-8").splitlines()
    examples = [json.loads(line) for line in lines if line.strip()]
    gbnf_path = HERE / "form.gbnf"
    suite = {
        "system_prompt": (HERE / "system_draft.txt").read_text(encoding="utf-8").strip(),
        "json_schema": json.loads((HERE / "form.schema.json").read_text(encoding="utf-8")),
        "gbnf": gbnf_path.read_text(encoding="utf-8") if gbnf_path.exists() else None,
        "examples": examples,
    }
    out = HERE / "suites" / "spike.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(suite, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out} — {len(examples)}문장, gbnf={'있음' if suite['gbnf'] else '없음'}")


if __name__ == "__main__":
    main()
