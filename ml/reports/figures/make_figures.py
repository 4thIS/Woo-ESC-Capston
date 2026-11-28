"""학습·검증 수치 그림 — ml/reports/figures/.

    # 1) 학습 로그에서 손실 곡선을 뽑아 metrics.json 에 넣는다 (runs/ 는 git 밖 — 학습한 PC 에서만)
    uv run python reports/figures/make_figures.py extract --run run1=runs/run1/train.log \
        --run run2=runs/run2/train.log
    # 2) metrics.json → 그림(PNG). matplotlib 은 의존성에 넣지 않았다 — 그릴 때만 받는다
    uv run --with matplotlib python reports/figures/make_figures.py plot

metrics.json 이 원본이다. 점수는 reports/*.md·*.json 에서 옮겨 적은 값이다(출처는 각 항목의 source).
"""

from __future__ import annotations

import argparse
import ast
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
METRICS = HERE / "metrics.json"
LOG_EVERY, EVAL_EVERY = 20, 200  # esc_ml.train 기본값 — 학습 손실 20단계, 검증 200단계마다

# 차트 색 — dataviz 기준 팔레트(밝은 면) 범주 순서 그대로. 같은 대상은 모든 그림에서 같은 색
INK, INK2, GRID, SURFACE = "#191919", "#666666", "#e6e6e6", "#ffffff"
C_BASE, C_V1, C_V2 = "#9c9c9c", "#f47230", "#257de0"  # 기준선(회색) · v0.1.0 · v0.2.0
C_RUN = {"run1": C_V1, "run2": C_V2}


def _dicts(line: str):
    for m in re.finditer(r"\{'[^{}]*\}", line):
        try:
            yield ast.literal_eval(m.group(0))
        except (SyntaxError, ValueError):
            continue


def extract(runs: list[str]) -> None:
    data = json.loads(METRICS.read_text(encoding="utf-8"))
    for spec in runs:
        name, _, path = spec.partition("=")
        train, evals = [], []
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            for d in _dicts(line):
                if "loss" in d and "eval_loss" not in d:
                    train.append(
                        {
                            "step": (len(train) + 1) * LOG_EVERY,
                            "loss": float(d["loss"]),
                            "epoch": float(d["epoch"]),
                        }
                    )
                elif "eval_loss" in d:
                    evals.append(
                        {
                            "step": (len(evals) + 1) * EVAL_EVERY,
                            "loss": float(d["eval_loss"]),
                            "epoch": float(d["epoch"]),
                        }
                    )
        data["curves"][name] = {"train": train, "eval": evals}
        print(f"{name}: 학습 손실 {len(train)}점 · 검증 손실 {len(evals)}점")
    METRICS.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _korean_font() -> str:
    from matplotlib import font_manager

    have = {f.name for f in font_manager.fontManager.ttflist}
    return next(
        (f for f in ("Malgun Gothic", "AppleGothic", "NanumGothic") if f in have), "sans-serif"
    )


def _style(plt) -> None:
    plt.rcParams.update(
        {
            "font.family": _korean_font(),
            "axes.unicode_minus": False,
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK2,
            "axes.titlecolor": INK,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.8,
            "xtick.color": INK2,
            "ytick.color": INK2,
            "legend.frameon": False,
            "legend.labelcolor": INK,
            "savefig.dpi": 160,
            "savefig.bbox": "tight",
        }
    )


def fig_loss(plt, data: dict) -> None:
    fig, ax = plt.subplots(figsize=(9, 4.6))
    for name, cur in data["curves"].items():
        c = C_RUN[name]
        label = data["runs"][name]["label"]
        xs = [p["step"] for p in cur["train"]]
        ax.plot(xs, [p["loss"] for p in cur["train"]], color=c, lw=2, label=f"{label} 학습 손실")
        ex = [p["step"] for p in cur["eval"]]
        ax.plot(
            ex,
            [p["loss"] for p in cur["eval"]],
            color=c,
            lw=2,
            ls="--",
            marker="o",
            ms=7,
            markeredgecolor=SURFACE,
            markeredgewidth=2,
            label=f"{label} 검증 손실",
        )
        best = data["runs"][name].get("best_step")
        if best:
            y = next(p["loss"] for p in cur["eval"] if p["step"] == best)
            ax.annotate(
                f"채택 {best}단계",
                (best, y),
                xytext=(0, 14),
                textcoords="offset points",
                ha="center",
                color=INK,
                fontsize=9,
                fontweight="bold",
            )
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.text(
        0.01,
        0.02,
        "검증 손실은 run1(데이터 v1 검증 400문장)과 run2(데이터 v2 검증 627문장)의 "
        "검증 문장이 달라 서로 직접 비교하지 않는다",
        transform=ax.transAxes,
        fontsize=8,
        color=INK2,
    )
    ax.set_xlabel("학습 단계(step) — 1단계 = 문장 16개")
    ax.set_ylabel("손실 (로그 눈금, 낮을수록 좋음)")
    ax.set_title("학습·검증 손실 — run1(1바퀴 중 600단계에서 멈춤) vs run2(2바퀴)")
    ax.legend(loc="upper right", ncols=2, fontsize=9)
    fig.savefig(HERE / "loss.png")
    plt.close(fig)


def fig_versions(plt, data: dict) -> None:
    metrics = [("intent_acc", "요청 종류"), ("field_acc", "칸"), ("exact_acc", "양식 전체 일치")]
    vers = data["versions"]
    colors = [C_BASE, C_V1, C_V2]
    fig, ax = plt.subplots(figsize=(9, 4.8))
    n, w = len(vers), 0.26
    for i, v in enumerate(vers):
        xs = [k + (i - (n - 1) / 2) * (w + 0.02) for k in range(len(metrics))]
        ys = [v[m] * 100 for m, _ in metrics]
        bars = ax.bar(xs, ys, width=w, color=colors[i], label=v["label"], zorder=2)
        for b, y in zip(bars, ys, strict=True):  # 값은 막대 안 위쪽 — 합격선과 겹치지 않게
            ax.text(
                b.get_x() + b.get_width() / 2,
                y - 1.5,
                f"{y:.1f}",
                ha="center",
                va="top",
                fontsize=9,
                color=SURFACE,
                fontweight="bold",
            )
    for k, (m, _) in enumerate(metrics):
        line = data["pass_line"][m] * 100
        ax.plot([k - 0.45, k + 0.45], [line, line], color=INK, lw=1.5, ls=(0, (4, 3)), zorder=3)
        ax.text(
            k + 0.45, line + 1, f"합격선 {line:.0f}", ha="right", va="bottom", fontsize=8, color=INK
        )
    ax.set_xticks(range(len(metrics)), [t for _, t in metrics])
    ax.set_ylim(0, 118)
    ax.set_ylabel("정확도 (%)")
    ax.grid(axis="x", visible=False)
    ax.set_title("버전별 시험 점수 — 시험 문장 381개")
    ax.text(
        0,
        -0.13,
        "v0.1.0·v0.2.0 은 브라우저에서 도는 양자화 모델(q4f16_1), 기준선은 튜닝 전 원본 모델(예시 6개)",
        transform=ax.transAxes,
        fontsize=8,
        color=INK2,
    )
    ax.legend(loc="upper left", fontsize=9, ncols=3)
    fig.savefig(HERE / "versions.png")
    plt.close(fig)


def fig_checkpoints(plt, data: dict) -> None:
    cps = data["run2_checkpoints"]
    metrics = [
        ("intent_acc", "요청 종류", "#257de0"),
        ("field_acc", "칸", "#f47230"),
        ("exact_acc", "양식 전체 일치", "#00b894"),
    ]
    fig, ax = plt.subplots(figsize=(8, 4.4))
    xs = [c["step"] for c in cps]
    for m, label, color in metrics:
        ys = [c[m] * 100 for c in cps]
        ax.plot(
            xs,
            ys,
            color=color,
            lw=2,
            marker="o",
            ms=8,
            markeredgecolor=SURFACE,
            markeredgewidth=2,
            label=label,
        )
        ax.annotate(
            label,
            (xs[-1], ys[-1]),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            fontsize=9,
            color=INK,
        )
    best = data["runs"]["run2"]["best_step"]
    ax.axvline(best, color=INK2, lw=1, ls=":")
    ax.text(best, 101, f"채택 {best}단계", ha="center", fontsize=9, color=INK)
    ax.set_xticks(xs, [f"{c['step']}\n({c['epoch']})" for c in cps])
    ax.set_xlabel("저장본 단계 (에폭)")
    ax.set_ylabel("정확도 (%)")
    ax.set_ylim(80, 103)
    ax.set_xlim(xs[0] - 120, xs[-1] + 260)
    ax.set_title("run2 저장본 비교 — 양자화 전(HF) 시험 점수")
    ax.legend(loc="lower right", fontsize=9)
    fig.savefig(HERE / "checkpoints.png")
    plt.close(fig)


def fig_per_intent(plt, data: dict) -> None:
    rows = sorted(data["v020_per_intent"], key=lambda r: r["exact"])
    fig, ax = plt.subplots(figsize=(8, 6.4))
    ys = range(len(rows))
    ax.barh(
        ys,
        [r["exact"] * 100 for r in rows],
        color=C_V2,
        height=0.62,
        zorder=2,
        label="양식 전체 일치",
    )
    ax.scatter(
        [r["intent"] * 100 for r in rows],
        ys,
        s=46,
        color=INK,
        zorder=3,
        edgecolors=SURFACE,
        linewidths=2,
        label="요청 종류 정확도",
    )
    for y, r in zip(ys, rows, strict=True):
        ax.text(
            r["exact"] * 100 - 1.5,
            y,
            f"{r['exact'] * 100:.0f}",
            ha="right",
            va="center",
            fontsize=8,
            color=SURFACE,
        )
    ax.set_yticks(list(ys), [f"{r['name']} ({r['n']})" for r in rows])
    ax.set_xlim(0, 104)
    ax.set_xlabel("정확도 (%) — 괄호는 시험 문장 수")
    ax.grid(axis="y", visible=False)
    ax.set_title("v0.2.0 요청 종류별 점수 — 막대 = 양식 전체 일치, 점 = 요청 종류")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncols=2, fontsize=9)
    fig.savefig(HERE / "per_intent.png")
    plt.close(fig)


def plot() -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _style(plt)
    data = json.loads(METRICS.read_text(encoding="utf-8"))
    fig_loss(plt, data)
    fig_versions(plt, data)
    fig_checkpoints(plt, data)
    fig_per_intent(plt, data)
    print("loss.png · versions.png · checkpoints.png · per_intent.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract")
    ex.add_argument("--run", action="append", required=True, help="이름=train.log 경로")
    sub.add_parser("plot")
    a = ap.parse_args()
    extract(a.run) if a.cmd == "extract" else plot()
