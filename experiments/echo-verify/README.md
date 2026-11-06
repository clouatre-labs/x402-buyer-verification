# echo-verify

Buyer-side verification of a single x402 v2 payment to
`https://aptu.dev/v1/echo` on Base mainnet. See [protocol.md](protocol.md)
for the pre-registered design.

## Run

```sh
# decode-only dry run (no settlement)
bun experiments/echo-verify/verify.ts --skip-pay
# full run (settles ~0.01 USDC; requires MAINNET_PAYER_PRIVATE_KEY in env)
bun experiments/echo-verify/verify.ts
```

Raw outputs land in `data/` (discovery, decoded challenge, payment payload,
settlement receipt, Transfer-event evidence per RPC, latency samples,
summary).

## Results (2026-11-06 run)

- Settlement tx `0xa3143d32319392227c017ce86dceb2a8e377b7e4f32c21f2693a6925e91f201c`
  (block 54034097, within the pre-recorded window 54034088-54034098).
- On both `https://mainnet.base.org` and `https://base.publicnode.com`:
  the USDC `Transfer` event has `from` = payer
  `0xd0D40C485C6878DF38485E71bcc0Ad95Fb97FA5E`, `to` = challenge `payTo`
  `0x169313d28075a6dDB70E7e5190a1eDdc0d105671`, value = 10000 base units
  (0.01 USDC) exactly. The on-chain `tx.from` is the Coinbase facilitator
  (`0xb87e1a2cc2b4643f2892768e80e41167f17c5860`), confirming payer identity
  is anchored by the Transfer event, not the transaction sender.
- Unpaid discovery latency (descriptive only, n = 15): median 0.0388 s,
  IQR 0.0315-0.0393 s.

## SDK-vs-harness attribution

| Checked behavior | Attributed to |
|---|---|
| Challenge fetch and EIP-3009 payload construction | x402 SDK (`@x402/fetch`, `@x402/evm` ExactEvmScheme) |
| Facilitator settlement broadcast | x402 SDK facilitator client / Coinbase facilitator |
| Receipt capture via hooks | x402 SDK hooks (`onAfterPaymentCreation`, `onPaymentResponse`), registered via client methods before `wrapFetchWithPayment` |
| PAYMENT-REQUIRED base64url decode and v2 shape validation | this harness (`verify.ts`) |
| Transfer-event payer/payTo/amount assertions on dual RPCs | this harness (`verify.ts`), viem |
| Challenge issuance and receipt emission | remote service (`aptu.dev`) |

## Threats to validity

Single irreversible settlement; free-RPC receipt lag mitigated by 2-5 s
backoff polling; timings are descriptive only.
