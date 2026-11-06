# SPDX-License-Identifier: Apache-2.0
# EXPLORATORY figure: unpaid discovery GET latency per iteration, one dot
# per committed sample in original run order (#1..#15), with the inter-
# quartile range shaded and the median marked. Derives only from the
# committed samples in experiments/echo-verify/data/03-latency-samples.json.
# Labeled exploratory (post-hoc); no figure was preregistered. Render with:
#     uv run --with matplotlib python figures/fig1-discovery-latency.py

import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = pathlib.Path(__file__).resolve().parents[1]
DATA = REPO / "experiments" / "echo-verify" / "data" / "03-latency-samples.json"


def main():
    raw = json.loads(DATA.read_text())["samples"]
    ms = [s * 1000.0 for s in raw]

    q = sorted(ms)
    n = len(q)
    # linear-interpolation quantiles (numpy default)
    def pct(p):
        k = (n - 1) * p
        f = int(k)
        return q[f] + (q[min(f + 1, n - 1)] - q[f]) * (k - f)

    median = pct(0.50)
    q1, q3 = pct(0.25), pct(0.75)
    assert round(median, 1) == 38.8, median
    assert round(q1, 1) == 31.5 and round(q3, 1) == 39.3, (q1, q3)

    ys = list(range(1, n + 1))
    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.axvspan(q1, q3, color="#1f77b4", alpha=0.09,
               label=f"IQR {q1:.1f}-{q3:.1f} ms")
    ax.axvline(median, color="#1f77b4", linestyle="--", linewidth=1.4,
               label=f"median {median:.1f} ms")
    ax.scatter(ms, ys, s=48, color="#1f77b4", alpha=0.85, zorder=3)
    ax.annotate("cold start", (ms[0], ys[0]),
                textcoords="offset points", xytext=(-10, 12),
                ha="right", va="center", fontsize=8, color="0.3")
    ax.set_xlabel("Discovery GET latency (ms)")
    ax.set_ylabel("Iteration")
    ax.set_yticks(ys, labels=[f"#{i}" for i in ys])
    ax.set_ylim(0.2, n + 0.8)
    ax.set_xlim(right=95)
    ax.set_title(
        "Unpaid discovery GET latency per iteration, 15 samples (exploratory)")
    ax.grid(True, axis="x", alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(loc="upper right", fontsize=9)
    fig.tight_layout()
    out = pathlib.Path(__file__).resolve().parent / "fig1-discovery-latency.png"
    fig.savefig(out, dpi=300)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
