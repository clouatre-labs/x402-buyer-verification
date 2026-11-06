# Protocol: preflight-external

Pre-registered before any run. Do not modify after data collection begins;
changes require a dated addendum.

## Question

Do third-party x402 endpoints advertise protocol-compatible v2 challenges
in their unpaid 402 responses, without any payment being sent?

## Endpoint selection rule (pre-registered)

First v2-manifested endpoint per distinct operator from public x402
directories, priced at or below $0.05, with a live well-known document
verified before selection:

- `kaisha-api.hp-vladic.workers.dev`
- `blockrun.ai`
- `agent402.tools`

## Design

Decode-only probe. For each endpoint: GET `/.well-known/x402` (recorded),
then one unpaid POST to the protected path; the base64url
`PAYMENT-REQUIRED` header is decoded and its shape recorded. No retries.
Decode divergence on non-v2 manifests is a VALID finding, not an error.

## Hard no-payment guard

The probe runner aborts (process exit 1, nothing sent) if any outgoing
request to a non-localhost host would carry a payment-bearing header
(`payment-signature`, `x-payment`, or any header matching /^payment-/i).
Only the discovery GET and the unpaid decode POST are permitted. The
runner registers the guard before any network call.

## Passing criterion

Not applicable as pass/fail; findings are recorded verbatim. The guard
itself must hold (no payment-bearing header ever sent).

## Artifacts

Raw outputs to `data/` (per-endpoint discovery document, 402 headers,
decoded challenge or divergence record, guard audit line). Summary in
`analysis.json` with `record_type: "payment-run"`.

## Threats to validity

- Third-party endpoints may change manifests between selection and run.
- A single POST per endpoint; server-side state or user-agent gating could
  alter the 402 shape.
