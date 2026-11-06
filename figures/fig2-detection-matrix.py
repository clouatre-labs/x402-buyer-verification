# SPDX-License-Identifier: Apache-2.0
# EXPLORATORY figure: mock-seller detection matrix, one row per hostile
# mode plus the baseline control, annotating the exact value that got
# caught. Every annotated value is asserted against the committed data
# in experiments/mock-seller/data/. The replay row is fork-local
# (Anvil, Base fork pinned at block 54035433), not mainnet.
# Render with:
#     uv run --with matplotlib python figures/fig2-detection-matrix.py

import json
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = pathlib.Path(__file__).resolve().parents[1]
DATA = REPO / "experiments" / "mock-seller" / "data"


def load(name):
    return json.loads((DATA / f"{name}.json").read_text())


def main():
    baseline = load("baseline")
    amount = load("amount-mismatch")
    payto = load("payTo-mismatch")
    receipt = load("receipt-missing-key")
    replay = load("replay")

    # Recompute and assert every annotated value from the JSON.
    assert baseline["detected"] is False
    assert all(baseline["decode_checks"].values())
    assert all(baseline["receipt_checks"].values())

    amt_manifest = int(amount["manifest"]["accepts"][0]["amount"])
    amt_challenge = int(amount["challenge"]["accepts"][0]["amount"])
    ratio = amt_challenge / amt_manifest
    assert (amt_challenge, amt_manifest) == (99999, 10000)
    assert round(ratio, 1) == 10.0
    assert amount["decode_checks"]["manifest_amount_matches_challenge"] is False
    assert amount["detected"] is True

    p_manifest = payto["manifest"]["accepts"][0]["payTo"].lower()
    p_challenge = payto["challenge"]["accepts"][0]["payTo"].lower()
    assert p_manifest[:6] == "0x1693" and p_challenge[:6] == "0x2693"
    assert p_manifest[4:] == p_challenge[4:]  # differs only in the first hex digit
    assert payto["decode_checks"]["manifest_payTo_matches_challenge"] is False
    assert payto["detected"] is True

    assert "settledAmountUsdc" not in receipt["receipt"]
    assert receipt["receipt_checks"]["settledAmount_present"] is False
    assert receipt["detected"] is True

    assert replay["anvil_fork_block"] == 54035433
    assert replay["replay_rejected"] is True
    assert "FiatTokenV2: authorization is used or canceled" in replay["second_settle_error"]

    rows = [
        ("baseline (control)", "all decode + receipt checks passed", "passed clean"),
        ("amount-mismatch", f"{amt_challenge} vs {amt_manifest} ({ratio:.1f}x)", "detected"),
        ("payTo-mismatch", "0x2693... vs 0x1693... single-hex swap", "detected"),
        ("receipt-missing-key", 'missing receipt key "settledAmountUsdc"', "detected"),
        ("replayed-nonce (fork-local)", "revert: FiatTokenV2: authorization\nis used or canceled", "rejected"),
    ]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, len(rows) + 0.55)
    ax.axis("off")

    n = len(rows)
    col_x = (0.02, 0.26, 0.88)
    for i, (mode, value, outcome) in enumerate(rows):
        y = n - 0.5 - i
        color = "0.15" if i == 0 else "black"
        ax.text(col_x[0], y, mode, ha="left", va="center", fontsize=9,
                weight="bold" if outcome != "passed clean" else "normal",
                color=color)
        ax.text(col_x[1], y, value, ha="left", va="center", fontsize=8.5,
                family="monospace" if i in (2, 4) else None, color=color)
        ok = outcome == "passed clean"
        ax.text(col_x[2], y, outcome, ha="right", va="center", fontsize=9,
                color="green" if ok else "firebrick",
                weight="bold")
    for y in range(n + 1):
        ax.plot([0, 1], [y, y], color="0.75", lw=0.8)
    ax.plot([col_x[1] - 0.02] * 2, [0, n], color="0.75", lw=0.8)
    ax.plot([col_x[2] - 0.02] * 2, [0, n], color="0.75", lw=0.8)
    ax.text(col_x[0], n + 0.05, "mode", ha="left", va="bottom", fontsize=9, weight="bold")
    ax.text(col_x[1], n + 0.05, "value caught", ha="left", va="bottom", fontsize=9, weight="bold")
    ax.text(col_x[2], n + 0.05, "outcome", ha="right", va="bottom", fontsize=9, weight="bold")

    ax.set_title(
        "Hostile-seller failure modes, detection outcomes (mock-seller, exploratory)",
        fontsize=11)
    fig.tight_layout()
    out = pathlib.Path(__file__).resolve().parent / "fig2-detection-matrix.png"
    fig.savefig(out, dpi=300)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
