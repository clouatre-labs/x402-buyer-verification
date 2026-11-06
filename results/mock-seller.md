# mock-seller

Status: analyzed (2026-11-06)

**Headline result: 4/4 hostile-seller failure modes correctly detected; the same-nonce EIP-3009 replay reverted at EVM state level with `FiatTokenV2: authorization is used or canceled` on an Anvil fork of Base pinned at block 54035433.**

| Mode | Detected | Expected | Wall clock |
|---|---|---|---|
| baseline | no (correct) | no | 1.2 s |
| amount-mismatch (challenge 99999 vs manifest 10000) | yes | yes | 1.1 s |
| payTo-mismatch | yes | yes | 1.1 s |
| receipt-missing-key | yes | yes | 1.1 s |
| EIP-3009 replay (same nonce) | reverted at EVM state level | yes | 12.4 s |

*Table 1: detection outcomes and timings, copied verbatim from [analysis.json](../experiments/mock-seller/analysis.json).*

The replay payer was the fork-local dev account
`0xCFDf9cF9c4a2078ADe2523d630A21aaB4fc991Ff`; the recorded tx hash is a
fork-local placeholder (`0x000...0`, synthetic — Anvil does not emit real
hashes on a local fork), not an on-chain transaction. Negative
finding (replay reverted) has a known cause: USDC's EIP-3009 authorization
is single-use, so the second settle with the same nonce fails at EVM
state level. Timings are descriptive only (single run per mode).

## Reproduce

```sh
uv run python validate_schema.py
bun experiments/mock-seller/probe.ts
bun experiments/mock-seller/replay.ts
```

Sources: [experiments/mock-seller/](../experiments/mock-seller/) - full
numbers in [RESULTS.md](../RESULTS.md).
