# preflight-external

Status: analyzed (2026-11-06)

**Headline result: 2/3 third-party x402 endpoints returned protocol-compatible v2 402 challenges; agent402.tools diverged with a 404 and no challenge. Zero payment-bearing headers were sent.**

| Endpoint | Result | payTo | Amount | Wall clock |
|---|---|---|---|---|
| kaisha (GET /resolve) | v2-compatible | `0xF2A6416EBb0C594Ab2977695bED061729ddEb47b` | 5000 base units (0.005 USDC) | 0.6 s |
| blockrun (POST /api/v1/chat/completions) | v2-compatible | `0xe9030014F5DAe217d0A152f02A043567b16c1aBf` | 2000 base units (0.002 USDC) | 0.7 s |
| agent402.tools (POST /api/extract) | diverged: 404, no challenge | n/a | n/a | 0.4 s |

*Table 1: probe outcomes, copied verbatim from [analysis.json](../experiments/preflight-external/analysis.json).*

Negative/divergent finding (agent402.tools) and its cause: the endpoint
returned a 404 without a challenge rather than the expected v2 402, so no
challenge-issued payTo or amount exists; the divergence is recorded
verbatim per the pre-registered protocol (no retries, by design). No
payment was made and no settlement occurred; the guarded fetch wrapper
tripped zero times.

## Reproduce

```sh
uv run python validate_schema.py
bun experiments/preflight-external/probe.ts
```

Note: third-party endpoint responses were captured on 2026-11-06 and are
not guaranteed to reproduce later.

Sources: [experiments/preflight-external/](../experiments/preflight-external/) -
full numbers in [RESULTS.md](../RESULTS.md).
