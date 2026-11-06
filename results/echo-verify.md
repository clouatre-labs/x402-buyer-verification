# echo-verify

Status: analyzed (2026-11-06)

**Headline result: fresh $0.01 mainnet x402 v2 settlement verified end-to-end via payer-anchored Transfer events on two independent RPCs.**

| Check | Outcome |
|---|---|
| Settlement amount | 0.01 USDC exactly to challenge payTo (10000 base units) |
| Payer / payTo | `0xd0D40C485C6878DF38485E71bcc0Ad95Fb97FA5E` / `0x169313d28075a6dDB70E7e5190a1Eddc0d105671` |
| Settlement tx | `0xa3143d32319392227c017ce86dceb2a8e377b7e4f32c21f2693a6925e91f201c` |
| Paid-run wall clock | 1.11 s (unpaid decode-only POST 0.039 s) |
| Discovery latency (n = 15 GETs) | median 0.0388 s, IQR 0.0315-0.0393 s |
| Receipt + Transfer event | verified on both RPCs; on-chain `tx.from` is the Coinbase facilitator `0xb87e1a2cc2b4643f2892768e80e41167f17c5860` |

*Table 1: echo-verify assertions and timings, copied verbatim from [analysis.json](../experiments/echo-verify/analysis.json).*

Timings are descriptive only (single paid run). Limitations are recorded in
the committed analysis record: single irreversible settlement; free-RPC
receipt lag mitigated by backoff polling.

## Reproduce

```sh
uv run python validate_schema.py
# decode-only dry run (no settlement)
bun experiments/echo-verify/verify.ts --skip-pay
# full run settles ~0.01 USDC; requires MAINNET_PAYER_PRIVATE_KEY in env
bun experiments/echo-verify/verify.ts
```

Sources: [experiments/echo-verify/](../experiments/echo-verify/) - full
numbers in [RESULTS.md](../RESULTS.md).
