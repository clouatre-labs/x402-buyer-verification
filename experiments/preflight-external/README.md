# preflight-external

Decode-only probe of three third-party x402 endpoints with a hard
no-payment guard. See [protocol.md](protocol.md) for the pre-registered
design and endpoint selection rule.

## Run

```sh
bun experiments/preflight-external/probe.ts
```

The probe performs one discovery GET and one unpaid decode request per
endpoint (method and path taken from the endpoint's own well-known
manifest), then decodes the base64url `PAYMENT-REQUIRED` header. No
retries. A guard wraps the fetch function and aborts the process before
any request that would carry a payment-bearing header (`payment-*`,
`x-payment`) to a non-localhost host; the run reports `guard_trips: 0`.

## Results (2026-11-06 run)

| Endpoint | Decode target | Status | x402 version | v2 shape |
|---|---|---|---|---|
| kaisha-api.hp-vladic.workers.dev | GET /resolve | 402 | 2 | yes |
| blockrun.ai | POST /api/v1/chat/completions | 402 | 2 | yes |
| agent402.tools | POST /api/extract | 404 | - | - |

Findings: kaisha and blockrun both return protocol-compatible v2 402
challenges on unpaid requests. agent402.tools returned 404 on the first
manifested resource path without issuing a challenge; per the protocol
this decode divergence on a non-v2-shaped response is a valid finding
recorded verbatim (no retries). No payment-bearing header was ever sent;
the guard did not trip.

## SDK-vs-harness attribution

| Checked behavior | Attributed to |
|---|---|
| 402 challenge issuance and header encoding | remote service (each endpoint) |
| base64url decode and v2 shape validation | this harness (`probe.ts`) |
| Resource path/method extraction from well-known manifests | this harness (`probe.ts`) |
| No-payment guard | this harness (`probe.ts`) |

## Threats to validity

Single request per endpoint; server-side state or user-agent gating could
alter responses. Manifests may change between selection and run.
