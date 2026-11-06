# Protocol: echo-verify

Pre-registered before any run. Do not modify after data collection begins;
changes require a dated addendum.

## Question

Does a single buyer-side x402 v2 payment against `https://aptu.dev/v1/echo`
settle on Base mainnet with all verifiable properties consistent with the
challenge the seller issued?

## Design

Single paid run plus a latency sample of unpaid discovery requests.

1. **Discover**: GET `https://aptu.dev/.well-known/x402`. Record response.
2. **Decode**: unpaid POST to `/v1/echo`; parse the base64url
   `PAYMENT-REQUIRED` response header; validate the v2 shape
   (`x402Version`, `resource`, `accepts[]` with `scheme: exact`,
   `network: eip155:8453`, asset `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`,
   expected `payTo` and amount 10000 base units = 0.01 USDC).
3. **Latency sample**: 15 unpaid discovery iterations; record per-iteration
   wall-clock seconds; report median and interquartile range. Descriptive
   only; no performance claims.
4. **Pay**: x402Client with ExactEvmScheme registered for `eip155:8453`,
   hooks attached via client methods (`onAfterPaymentCreation`,
   `onPaymentResponse`) BEFORE `wrapFetchWithPayment`; hooks capture the
   PaymentPayload and settlement receipt before any assertion.
5. **Assert**, on two independent RPCs (`https://mainnet.base.org` primary,
   `https://base.publicnode.com` secondary with 2-5 s exponential backoff,
   up to ~30 s, for receipt availability):
   - receipt keys present (`success`, `transaction`) and `success: true`;
   - the USDC `Transfer` event on the settlement tx has `from` == local
     payer address (the payer is anchored by the Transfer event's from
     argument; on-chain `tx.from` is the facilitator), `to` == challenge
     `payTo`, and value == 10000 base units exactly;
   - block height of the settlement tx is within [block at challenge
     decode, block at assertion completion] window.

## Passing criterion

All assertions true on both RPCs; exact amount match required (no tolerance).

## Artifacts

Raw outputs to `data/` (discovery response, decoded challenge, payment
payload, settlement receipt, Transfer-event evidence per RPC, latency
sample). Summary in `analysis.json` with `record_type: "payment-run"`.

## Threats to validity

- Single settlement; irreversible on-chain spend of ~0.01 USDC.
- Free RPC lag may delay the secondary receipt (mitigated by backoff).
- Facilitator-mediated settlement means `tx.from` is the facilitator, not
  the payer; payer identity is anchored by the Transfer event only.
