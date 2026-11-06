# Results: buyer-side x402 verification experiments

## Affiliation disclosure

The authors of this repository are affiliated with aptu.dev. Experiment 1 (echo-verify) verifies our own x402 endpoint. Experiments 2 and 3 probe harness-controlled and third-party endpoints. All figures below are copied verbatim from the committed `analysis.json` files; timings are descriptive only (single run per mode unless a sample set is stated).

## Experiment 1: echo-verify

Fresh $0.01 mainnet happy path with payer-anchored Transfer-event dual-RPC verification. All assertions passed: settlement settled 0.01 USDC exactly to the challenge payTo from the local payer per Transfer events on two independent RPCs; challenge decode and v2 shape validated. Settlement transaction: `0xa3143d32319392227c017ce86dceb2a8e377b7e4f32c21f2693a6925e91f201c`, payer `0xd0D40C485C6878DF38485E71bcc0Ad95Fb97FA5E`, payTo `0x169313d28075a6dDB70E7e5190a1Eddc0d105671`, exact amount in base units `10000`. Paid-run wall clock was 1.11 seconds; the unpaid decode-only POST took 0.039 seconds, with a latency median over 15 discovery GETs of 0.0388 s and an IQR of 0.0315-0.0393 s (descriptive only). Receipt and Transfer event were verified on both RPCs; `tx.from` is the Coinbase facilitator `0xb87e1a2cc2b4643f2892768e80e41167f17c5860`.

## Experiment 2: mock-seller

Hostile localhost seller with four failure modes plus an Anvil-fork EIP-3009 replay on a fork of Base pinned at block 54035433. All four detection outcomes were correct: baseline passed unchanged echo-verify criteria (not flagged, as expected); amount-mismatch (challenge amount 99999 vs manifest 10000), payTo-mismatch, and receipt-missing-key were each detected by cross-checks; the same-nonce EIP-3009 replay reverted at EVM state level with revert reason `FiatTokenV2: authorization is used or canceled`. Baseline, amount-mismatch, payTo-mismatch, and receipt-missing-key each took roughly 1.1-1.2 seconds; the replay took 12.4 seconds (descriptive). The replay payer was the fork-local dev account `0xCFDf9cF9c4a2078ADe2523d630A21aaB4fc991Ff`; the recorded tx hash is the fork-local first-settle reference, not a mainnet transaction.

## Experiment 3: preflight-external

Decode-only probe of three third-party x402 endpoints with a hard no-payment guard; zero payment-bearing headers were sent. Two of three endpoints (kaisha, blockrun) returned protocol-compatible v2 402 challenges; agent402.tools diverged with a 404 and no challenge. Kaisha's GET /resolve challenge advertised payTo `0xF2A6416EBb0C594Ab2977695bED061729ddEb47b` with amount `5000` base units (0.005 USDC). Blockrun's POST /api/v1/chat/completions challenge advertised payTo `0xe9030014F5DAe217d0A152f02A043567b16c1aBf` with amount `2000` base units (0.002 USDC). Wall-clock times were 0.6 s (kaisha), 0.7 s (blockrun), and 0.4 s (agent402), descriptive only. No payment was made and no settlement occurred in this experiment.
