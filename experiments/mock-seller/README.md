# mock-seller

Hostile localhost x402 seller plus buyer-side detector. See
[protocol.md](protocol.md) for the pre-registered design.

## Run

```sh
# four localhost modes (no real-mainnet settlement; dev key in memory)
bun experiments/mock-seller/probe.ts
# EIP-3009 replay rejection on a pinned Anvil fork of Base
bun experiments/mock-seller/replay.ts
```

`seller.ts` serves the hostile endpoint; `probe.ts` spawns it per mode and
detects deviations. `replay.ts` spawns Anvil (`--fork-url
https://mainnet.base.org`), records the pinned fork block, funds a
throwaway dev key via `anvil_setBalance` plus a USDC balance via
`anvil_setStorageAt` (slot 9), settles an EIP-3009
`transferWithAuthorization`, then replays the same authorization and nonce.

## Results (2026-11-06 run)

| Mode | Detected | Detection correct |
|---|---|---|
| baseline | no | yes |
| amount-mismatch | yes (challenge amount 99999 vs manifest 10000) | yes |
| payTo-mismatch | yes (challenge payTo differs from manifest) | yes |
| receipt-missing-key | yes (receipt drops `transaction` or `settledAmountUsdc`) | yes |
| replay (Anvil fork block 54035433) | yes (`FiatTokenV2: authorization is used or canceled`) | yes |

The first settle succeeded on the fork; the identical second submission
with the same nonce reverted at the EVM state level. The detector mirrors
the echo-verify verifier checks (v2 decode shape, manifest cross-check,
receipt keys), so the same checks that pass on the real endpoint fire here.

## SDK-vs-harness attribution

| Checked behavior | Attributed to |
|---|---|
| Payment payload construction and signing | x402 SDK (`@x402/fetch`, `@x402/evm` ExactEvmScheme) with in-memory dev key |
| Receipt capture via hooks | x402 SDK hooks (`onAfterPaymentCreation`, `onPaymentResponse`) via client methods before `wrapFetchWithPayment` |
| EIP-3009 settlement and nonce accounting | USDC contract (FiatTokenV2) on the Anvil fork |
| Manifest cross-check (amount, payTo) | this harness (`probe.ts`) |
| Receipt key completeness checks | this harness (`probe.ts`), same criteria as echo-verify |
| Replay rejection | EVM state on the pinned fork; harness (`replay.ts`) only orchestrates and asserts |
| Hostile challenge/receipt emission | this harness (`seller.ts`) |

## Threats to validity

The mock seller is harness code; deviations are controlled single-field
mutations of a manifest mirroring the real endpoint. Anvil fork state is
synthetic; the replay result demonstrates EVM nonce semantics, not the
live facilitator's behavior.
