/**
 * mock-seller probe: buyer-side detector mirroring the echo-verify verifier
 * code path (same decode, manifest cross-check, and receipt-key checks that
 * pass on the real endpoint). Runs against the local hostile seller only;
 * settles nothing on real mainnet (payment payloads are signed with a
 * throwaway in-memory dev key).
 *
 * Usage: bun experiments/mock-seller/probe.ts [--modes baseline,amount-mismatch,...]
 */
import { randomInt } from "node:crypto";
import { mkdirSync, writeFileSync } from "node:fs";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";
import { x402Client, wrapFetchWithPayment } from "@x402/fetch";
import { ExactEvmScheme } from "@x402/evm";

const USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const DATA_DIR = new URL("./data/", import.meta.url).pathname;
const ALL_MODES = ["baseline", "amount-mismatch", "payTo-mismatch", "receipt-missing-key"];

type PaymentRequired = {
  x402Version: number;
  resource: Record<string, unknown>;
  accepts: Array<{
    scheme: string;
    network: string;
    asset: string;
    amount: string;
    payTo: string;
    extra?: Record<string, unknown>;
  }>;
};

type Manifest = {
  x402Version: number;
  accepts: Array<{ scheme: string; network: string; asset: string; amount: string; payTo: string }>;
};

function decodeBase64Url(text: string): string {
  const normalized = text.replace(/-/g, "+").replace(/_/g, "/");
  return atob(normalized + "=".repeat((4 - (normalized.length % 4)) % 4));
}

async function waitForServer(url: string, tries = 40): Promise<void> {
  for (let i = 0; i < tries; i++) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      /* not up yet */
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`seller at ${url} did not come up`);
}

async function runMode(mode: string): Promise<Record<string, unknown>> {
  const port = 4100 + randomInt(800);
  const baseUrl = `http://localhost:${port}`;
  const seller = Bun.spawn(["bun", "experiments/mock-seller/seller.ts", "--mode", mode, "--port", String(port)], {
    stdout: "pipe",
    stderr: "inherit",
  });
  try {
    await waitForServer(`${baseUrl}/.well-known/x402`);
    // Discovery: manifest fetch (mirrors echo-verify discover stage).
    const manifestRes = await fetch(`${baseUrl}/.well-known/x402`);
    const manifest = (await manifestRes.json()) as Manifest;
    // Decode: unpaid POST, base64url PAYMENT-REQUIRED header, v2 shape.
    const res = await fetch(`${baseUrl}/v1/echo`, { method: "POST" });
    const header = res.headers.get("payment-required");
    const decoded = header ? (JSON.parse(decodeBase64Url(header)) as PaymentRequired) : null;
    const accept = decoded?.accepts?.find((a) => a.scheme === "exact" && a.network === "eip155:8453");
    const decodeChecks = {
      got_402: res.status === 402,
      header_present: !!header,
      v2_shape: decoded?.x402Version === 2 && !!accept,
      asset_is_base_usdc: accept?.asset?.toLowerCase() === USDC_BASE.toLowerCase(),
      manifest_amount_matches_challenge: accept?.amount === manifest.accepts[0]?.amount,
      manifest_payTo_matches_challenge:
        accept?.payTo?.toLowerCase() === manifest.accepts[0]?.payTo?.toLowerCase(),
    };

    // Pay: x402Client with in-memory dev key; hooks via client methods BEFORE
    // wrapFetchWithPayment (the config object has no hooks field).
    const account = privateKeyToAccount(generatePrivateKey());
    const client = new x402Client();
    client.register("eip155:8453", new ExactEvmScheme(account));
    const captured: { payload?: unknown; receipt?: Record<string, unknown> } = {};
    client.onAfterPaymentCreation(async (ctx) => {
      captured.payload = ctx.paymentPayload;
    });
    client.onPaymentResponse(async (ctx) => {
      captured.receipt = ctx.settleResponse as Record<string, unknown>;
    });
    const fetchWithPay = wrapFetchWithPayment(fetch, client);
    const paidRes = await fetchWithPay(`${baseUrl}/v1/echo`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({}),
    });
    await paidRes.text();
    const receipt = captured.receipt ?? {};
    const hex64 = /^0x[0-9a-fA-F]{64}$/;
    const receiptChecks = {
      receipt_captured: !!captured.receipt,
      success_true: receipt.success === true,
      transaction_present_and_hex: typeof receipt.transaction === "string" && hex64.test(receipt.transaction as string),
      settledAmount_present: receipt.settledAmountUsdc !== undefined,
      settledAmount_matches_challenge: String(receipt.settledAmountUsdc ?? "") === accept?.amount,
    };

    // Detector verdict mirrors echo-verify's pass criteria applied to the
    // real endpoint; any deviation from the seller's own manifest or a
    // dropped receipt key is a detection.
    const crossCheckPassed = decodeChecks.manifest_amount_matches_challenge && decodeChecks.manifest_payTo_matches_challenge;
    const receiptPassed = Object.values(receiptChecks).every(Boolean);
    const detected = !(crossCheckPassed && receiptPassed);

    return {
      mode,
      detected,
      expected_detected: mode !== "baseline",
      detection_correct: detected === (mode !== "baseline"),
      decode_checks: decodeChecks,
      receipt_checks: receiptChecks,
      manifest: manifest,
      challenge: decoded,
      receipt: receipt,
      paid_http_status: paidRes.status,
    };
  } finally {
    seller.kill();
  }
}

async function main(): Promise<void> {
  const modesArg = process.argv.find((a) => a.startsWith("--modes="));
  const modes = modesArg ? (modesArg.split("=")[1]!.split(",")) : ALL_MODES;
  mkdirSync(DATA_DIR, { recursive: true });
  const results: Array<Record<string, unknown>> = [];
  for (const mode of modes) {
    const result = await runMode(mode);
    results.push(result);
    writeFileSync(`${DATA_DIR}${mode}.json`, `${JSON.stringify(result, null, 2)}\n`);
    console.log(JSON.stringify({ mode, detected: result.detected, detection_correct: result.detection_correct }));
  }
  const allCorrect = results.every((r) => r.detection_correct === true);
  console.log(JSON.stringify({ all_detection_correct: allCorrect, modes_run: modes.length }));
  if (!allCorrect) process.exit(1);
}

main();
