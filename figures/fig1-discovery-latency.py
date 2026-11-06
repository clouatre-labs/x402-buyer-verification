#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Figure: unpaid discovery GET latency per iteration (echo-verify).

Exploratory (post-hoc): no figure was preregistered; this figure restates the
15 committed samples in experiments/echo-verify/data/03-latency-samples.json
as a sorted per-iteration strip (largest on top), with the median and IQR
band annotated. Writes a dark-mode-adaptive SVG plus a white-background PNG
render (rsvg-convert); no matplotlib dependency.

Usage: uv run python figures/fig1-discovery-latency.py
"""

import json
import pathlib
import subprocess

HERE = pathlib.Path(__file__).parent
DATA = HERE.parent / "experiments" / "echo-verify" / "data" / "03-latency-samples.json"


def iqr_linear(samples, q):
    # numpy-style linear interpolation (matches the committed 0.0315-0.0393 IQR)
    pos = (len(samples) - 1) * q
    lo = int(pos)
    frac = pos - lo
    return samples[lo] + frac * (samples[lo + 1] - samples[lo])


def main():
    payload = json.loads(DATA.read_text())
    n = payload["iterations"]
    samples = payload["samples"]
    assert len(samples) == n, f"expected {n} samples, got {len(samples)}"

    ranked = sorted(enumerate(samples), key=lambda p: -p[1])
    median = iqr_linear(sorted(samples), 0.5)
    iqr_lo = iqr_linear(sorted(samples), 0.25)
    iqr_hi = iqr_linear(sorted(samples), 0.75)
    assert n == 15, n
    assert round(median, 4) == 0.0388, median
    assert round(iqr_lo, 4) == 0.0315, iqr_lo
    assert round(iqr_hi, 4) == 0.0393, iqr_hi

    W, H = 640, 392
    M_L, M_R, M_T, M_B = 96, 96, 40, 52
    bar_h = 12
    gap = 6
    max_v = max(samples)
    scale = (W - M_L - M_R) / max_v

    def X(v):
        return M_L + v * scale

    rows = []
    y = M_T
    for rank, (idx, v) in enumerate(ranked, start=1):
        rows.append(
            f'  <text x="{M_L - 10}" y="{y + bar_h / 2 + 4}" text-anchor="end" '
            f'class="label">#{idx + 1}</text>'
            f'\n  <rect x="{M_L}" y="{y}" width="{X(v) - M_L:.1f}" height="{bar_h}" rx="2" class="mark"/>'
            f'\n  <text x="{X(v) + 8:.1f}" y="{y + bar_h / 2 + 4}" class="value">{v * 1000:.1f} ms</text>'
        )
        y += bar_h + gap

    def y_of(v):
        # vertical position of a latency value within the ranked strip
        r = sum(1 for _, s in ranked if s > v)
        return M_T + r * (bar_h + gap)

    iqr_y0 = y_of(iqr_hi)
    iqr_y1 = y_of(iqr_lo) + bar_h
    med_y = y_of(median) + bar_h / 2

    note_y = y + 8
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Unpaid discovery GET latency per iteration (echo-verify)">
  <style>
    text {{ font-family: ui-monospace, Menlo, monospace; }}
    .title {{ font-size: 14px; font-weight: 600; fill: #18181b; }}
    .label {{ font-size: 12px; fill: #18181b; }}
    .value {{ font-size: 12px; fill: #18181b; }}
    .note {{ font-size: 12px; fill: #52525b; }}
    .mark {{ fill: #075985; }}
    .ref {{ stroke: #dc2626; stroke-width: 1.5; }}
    .band {{ fill: #075985; fill-opacity: 0.10; }}
  </style>
  <rect x="{X(iqr_lo):.1f}" y="{iqr_y0 - 2}" width="{X(iqr_hi) - X(iqr_lo):.1f}" height="{iqr_y1 - iqr_y0 + 4}" class="band"/>
  <line x1="{X(iqr_lo):.1f}" y1="{iqr_y0 - 2}" x2="{X(iqr_lo):.1f}" y2="{iqr_y1 + 2}" class="ref"/>
  <line x1="{X(iqr_hi):.1f}" y1="{iqr_y0 - 2}" x2="{X(iqr_hi):.1f}" y2="{iqr_y1 + 2}" class="ref"/>
  <line x1="{X(median):.1f}" y1="{M_T - 8}" x2="{X(median):.1f}" y2="{med_y + 8}" class="ref"/>
  <text x="{W / 2}" y="24" text-anchor="middle" class="title">Unpaid discovery GET latency per iteration (echo-verify, exploratory)</text>
{chr(10).join(rows)}
  <text x="{M_L}" y="{note_y}" class="note">Exploratory (post-hoc). Source: experiments/echo-verify/data/03-latency-samples.json</text>
  <text x="{M_L}" y="{note_y + 16}" class="note">n = 15; median 0.0388 s, IQR 0.0315-0.0393 s (red lines); sorted largest on top</text>
</svg>
'''

    svg_path = HERE / "fig1-discovery-latency.svg"
    svg_path.write_text(svg)
    print(f"wrote {svg_path}")
    subprocess.run(
        [
            "rsvg-convert", "-z", "2", "-b", "#ffffff",
            "-o", str(HERE / "fig1-discovery-latency.png"),
            str(svg_path),
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
