# Protocol: mock-seller

Pre-registered before any run. Do not modify after data collection begins;
changes require a dated addendum.

## Question

Do buyer-side detectors that pass on the verified real endpoint
(`aptu.dev/v1/echo`, see `experiments/echo-verify`) correctly reject a
hostile localhost seller in four failure modes, including an EVM-level
EIP-3009 replay rejection on a pinned Anvil fork?

## Design

A `bun.serve` hostile seller runs on localhost with four modes. The probe
client mirrors the echo-verify verifier code path (same receipt checks,
same manifest cross-check, same decode checks) so detection is not
circular: the checks that passed on the real endpoint are applied unchanged
to the mock's deviations.

Modes (one run each, no settlement on real mainnet):

1. **amount-mismatch**: the challenge `amount` differs from the amount the
   seller's own local `/.well-known/x402` manifest advertises. Expected
   detection: challenge/manifest cross-check fails.
2. **payTo-mismatch**: the challenge `payTo` differs from the manifest.
   Expected detection: cross-check fails.
3. **receipt-missing-key**: settlement "succeeds" but the receipt drops
   `transaction` or `settledAmountUsdc`. Expected detection: receipt key
   check fails.
4. **replay** (Anvil fork): spin up `anvil --fork-url
   https://mainnet.base.org` with the fork block pinned and recorded; fund
   a throwaway in-memory dev key via `anvil_setBalance` (native gas) and a
   USDC balance via `anvil_setStorageAt` at the native-USDC balance slot;
   settle an EIP-3009 `transferWithAuthorization` on the fork, then
   re-submit the same authorization with the same nonce. Expected
   detection: the second settle reverts at the EVM state level
   (authorization nonce already consumed). The real
   `MAINNET_PAYER_PRIVATE_KEY` is never used in this mode.

## Passing criterion

All four detections fire exactly as expected; the echo-verify checks
(passing on the real endpoint) are the same ones that fire here.

## Artifacts

Raw outputs to `data/` (per-mode challenge, manifest, receipt, detector
verdicts; fork block number for the replay mode). Summary in `analysis.json`
with `record_type: "payment-run"`.

## Threats to validity

- The mock seller is itself harness code; it could be buggy in a way that
  trivializes detection (mitigated by mirroring the real-endpoint checks
  and serving a manifest identical to the real one except for the one
  mutated field per mode).
- Anvil fork state is synthetic; replay rejection demonstrates the EVM
  nonce semantics, not the live facilitator's behavior.
