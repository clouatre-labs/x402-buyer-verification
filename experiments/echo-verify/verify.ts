/**
 * echo-verify: buyer-side x402 v2 verification against https://aptu.dev/v1/echo.
 *
 * Stages: discover -> decode (unpaid) -> latency sample -> pay -> assert.
 * On-chain assertions run on two independent Base RPCs. The payer private
 * key is read from the environment only; it is never written to disk or
 * logged.
 *
 * Usage: bun experiments/echo-verify/verify.ts [--skip-pay]
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { x402Client, wrapFetchWithPayment } from "@x402/fetch";
import { ExactEvmScheme } from "@x402/evm";
import { createPublicClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { base } from "viem/chains";

const ECHO_URL = "https://aptu.dev/v1/echo";
const WELLKNOWN_URL = "https://aptu.dev/.well-known/x402";
const USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const TRANSFER_TOPIC =
  "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef";
const EXPECTED_AMOUNT_BASE_UNITS = 10000n; // 0.01 USDC, 6 decimals
const RPC_PRIMARY = "https://mainnet.base.org";
const RPC_SECONDARY = "https://base.publicnode.com";
const DATA_DIR = new URL("./data/", import.meta.url).pathname;
const SKIP_PAY = process.argv.includes("--skip-pay");
const LATENCY_ITERATIONS = 15;

type PaymentRequired = {
  x402Version: number;
  error?: string;
  resource: { url?: string; description?: string; [k: string]: unknown };
  accepts: Array<{
    scheme: string;
    network: string;
    asset: string;
    amount: string;
    payTo: string;
    maxTimeoutSeconds?: number;
    extra?: Record<string, unknown>;
    [k: string]: unknown;
  }>;
  extensions?: Record<string, unknown>;
  [k: string]: unknown;
};

function fail(msg: string): never {
  console.error(`FAIL: ${msg}`);
  process.exit(1);
}

function save(name: string, value: unknown): string {
  mkdirSync(DATA_DIR, { recursive: true });
  const path = `${DATA_DIR}${name}`;
  writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`);
  return path;
}

function decodeBase64Url(text: string): string {
  const normalized = text.replace(/-/g, "+").replace(/_/g, "/");
  return atob(normalized + "=".repeat((4 - (normalized.length % 4)) % 4));
}

function nowIso(): string {
  return new Date().toISOString();
}

async function discover(): Promise<unknown> {
  const res = await fetch(WELLKNOWN_URL);
  if (!res.ok) fail(`discovery GET failed: HTTP ${res.status}`);
  const body = await res.json();
  save("01-discovery.json", { url: WELLKNOWN_URL, status: res.status, body });
  return body;
}

async function decodeChallenge(): Promise<{
  paymentRequired: PaymentRequired;
  blockAtDecode: bigint;
}> {
  const res = await fetch(ECHO_URL, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({}),
  });
  if (res.status !== 402) fail(`expected 402 on unpaid POST, got ${res.status}`);
  const header = res.headers.get("payment-required");
  if (!header) fail("missing PAYMENT-REQUIRED response header");
  const paymentRequired = JSON.parse(decodeBase64Url(header)) as PaymentRequired;
  save("02-decoded-challenge.json", {
    header: header,
    decoded: paymentRequired,
  });
  if (paymentRequired.x402Version !== 2) {
    fail(`expected x402Version 2, got ${paymentRequired.x402Version}`);
  }
  const accept = paymentRequired.accepts?.find(
    (a) => a.scheme === "exact" && a.network === "eip155:8453",
  );
  if (!accept) fail("no accepts[] entry for exact/eip155:8453");
  if (accept.asset.toLowerCase() !== USDC_BASE.toLowerCase()) {
    fail(`unexpected asset ${accept.asset}`);
  }
  const publicClient = createPublicClient({ chain: base, transport: http(RPC_PRIMARY) });
  const blockAtDecode = await publicClient.getBlockNumber();
  return { paymentRequired, blockAtDecode };
}

async function latencySample(): Promise<number[]> {
  const samples: number[] = [];
  for (let i = 0; i < LATENCY_ITERATIONS; i++) {
    const start = performance.now();
    const res = await fetch(WELLKNOWN_URL);
    if (!res.ok) fail(`latency-sample GET ${i} failed: HTTP ${res.status}`);
    await res.arrayBuffer();
    samples.push((performance.now() - start) / 1000);
  }
  save("03-latency-samples.json", {
    iterations: LATENCY_ITERATIONS,
    unit: "seconds",
    samples: samples,
  });
  return samples;
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0 ? (sorted[mid - 1] + sorted[mid]) / 2 : sorted[mid];
}

function quantile(values: number[], q: number): number {
  const sorted = [...values].sort((a, b) => a - b);
  const pos = (sorted.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return sorted[lo] + (sorted[hi] - sorted[lo]) * (pos - lo);
}

async function pay(): Promise<{
  paymentPayload: unknown;
  settleResponse: unknown;
  responseStatus: number;
  responseBody: string;
}> {
  const key = process.env.MAINNET_PAYER_PRIVATE_KEY;
  if (!key || !key.startsWith("0x")) {
    fail("MAINNET_PAYER_PRIVATE_KEY not set in environment");
  }
  const account = privateKeyToAccount(key as `0x${string}`);
  const client = new x402Client();
  client.register("eip155:8453", new ExactEvmScheme(account));

  const captured: { payload?: unknown; settle?: unknown } = {};
  // Hooks MUST be attached via client methods BEFORE wrapFetchWithPayment;
  // the wrapFetchWithPaymentFromConfig object has no hooks field (silent no-op).
  client.onAfterPaymentCreation(async (ctx) => {
    captured.payload = ctx.paymentPayload;
    save("04-payment-payload.json", ctx.paymentPayload);
  });
  client.onPaymentResponse(async (ctx) => {
    captured.settle = ctx.settleResponse;
    save("05-settlement-receipt.json", ctx.settleResponse ?? { error: String(ctx.error) });
  });

  const fetchWithPay = wrapFetchWithPayment(fetch, client);
  const start = performance.now();
  const res = await fetchWithPay(ECHO_URL, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({}),
  });
  const wallClockSeconds = (performance.now() - start) / 1000;
  const responseBody = await res.text();
  save("06-paid-response.json", {
    status: res.status,
    wall_clock_seconds: wallClockSeconds,
    body: responseBody,
  });
  return {
    paymentPayload: captured.payload,
    settleResponse: captured.settle,
    responseStatus: res.status,
    responseBody,
  };
}

type TransferEvidence = {
  rpc: string;
  found: boolean;
  from?: string;
  to?: string;
  valueBaseUnits?: string;
  blockNumber?: number;
  txFrom?: string;
  errors: string[];
};

async function fetchReceipt(
  rpc: string,
  txHash: string,
  poll: boolean,
): Promise<Awaited<ReturnType<typeof publicClientGetReceipt>> | null> {
  const publicClient = createPublicClient({ chain: base, transport: http(rpc) });
  let delayMs = 2000;
  const deadline = Date.now() + (poll ? 30000 : 5000);
  while (Date.now() < deadline) {
    try {
      const receipt = await publicClient.getTransactionReceipt({
        hash: txHash as `0x${string}`,
      });
      return receipt;
    } catch {
      if (!poll) return null;
      await new Promise((r) => setTimeout(r, delayMs));
      delayMs = Math.min(delayMs + 1000, 5000);
    }
  }
  return null;
}

// viem getTransactionReceipt throws when the tx is unknown; mirror that shape.
declare function publicClientGetReceipt(args: {
  hash: `0x${string}`;
}): Promise<{
  status: string;
  blockNumber: bigint;
  logs: Array<{ address: string; topics: string[]; data: string }>;
  from: string;
}>;

async function assertTransfer(
  rpc: string,
  txHash: string,
  payer: string,
  payTo: string,
  poll: boolean,
): Promise<TransferEvidence> {
  const evidence: TransferEvidence = { rpc: rpc, found: false, errors: [] };
  const receipt = await fetchReceipt(rpc, txHash, poll);
  if (!receipt) {
    evidence.errors.push(`receipt not available on ${rpc} within deadline`);
    return evidence;
  }
  evidence.blockNumber = Number(receipt.blockNumber);
  evidence.txFrom = receipt.from;
  if (receipt.status !== "success") {
    evidence.errors.push(`tx status ${receipt.status}`);
  }
  const log = receipt.logs.find(
    (l) =>
      l.address.toLowerCase() === USDC_BASE.toLowerCase() &&
      l.topics[0]?.toLowerCase() === TRANSFER_TOPIC &&
      l.topics.length === 3,
  );
  if (!log) {
    evidence.errors.push("no USDC Transfer(address,address,uint256) log found");
    return evidence;
  }
  const from = `0x${log.topics[1]!.slice(26)}`;
  const to = `0x${log.topics[2]!.slice(26)}`;
  const value = BigInt(log.data);
  evidence.found = true;
  evidence.from = from;
  evidence.to = to;
  evidence.valueBaseUnits = value.toString();
  if (from.toLowerCase() !== payer.toLowerCase()) {
    evidence.errors.push(`Transfer from ${from} != payer ${payer}`);
  }
  if (to.toLowerCase() !== payTo.toLowerCase()) {
    evidence.errors.push(`Transfer to ${to} != challenge payTo ${payTo}`);
  }
  if (value !== EXPECTED_AMOUNT_BASE_UNITS) {
    evidence.errors.push(`Transfer value ${value} != expected ${EXPECTED_AMOUNT_BASE_UNITS}`);
  }
  return evidence;
}

async function main(): Promise<void> {
  const key = process.env.MAINNET_PAYER_PRIVATE_KEY;
  const payerAddress = key?.startsWith("0x")
    ? privateKeyToAccount(key as `0x${string}`).address
    : "unknown";
  const blockHeightStart = await createPublicClient({
    chain: base,
    transport: http(RPC_PRIMARY),
  }).getBlockNumber();

  const discovery = await discover();
  const { paymentRequired, blockAtDecode } = await decodeChallenge();
  const accept = paymentRequired.accepts.find(
    (a) => a.scheme === "exact" && a.network === "eip155:8453",
  )!;
  const samples = await latencySample();

  let payResult: Awaited<ReturnType<typeof pay>> | null = null;
  let txHash: string | null = null;
  if (!SKIP_PAY) {
    payResult = await pay();
    const settle = payResult.settleResponse as
      | { success?: boolean; transaction?: string; [k: string]: unknown }
      | undefined;
    if (!settle?.transaction) fail("no settlement transaction captured via onPaymentResponse hook");
    txHash = settle.transaction;
  }

  const blockHeightEnd = await createPublicClient({
    chain: base,
    transport: http(RPC_PRIMARY),
  }).getBlockNumber();

  let primary: TransferEvidence | null = null;
  let secondary: TransferEvidence | null = null;
  if (txHash) {
    primary = await assertTransfer(RPC_PRIMARY, txHash, payerAddress, accept.payTo, true);
    secondary = await assertTransfer(RPC_SECONDARY, txHash, payerAddress, accept.payTo, true);
    save("07-transfer-evidence.json", { primary: primary, secondary: secondary });
  }

  const assertOk =
    !!primary &&
    !!secondary &&
    primary.found &&
    secondary.found &&
    primary.errors.length === 0 &&
    secondary.errors.length === 0;

  const summary = {
    stage: SKIP_PAY ? "decode-only" : "full",
    payer: payerAddress,
    payTo: accept.payTo,
    amount_base_units: accept.amount,
    tx_hash: txHash,
    tx_from_is_facilitator: primary?.txFrom?.toLowerCase() !== payerAddress.toLowerCase(),
    transfer_from_matches_payer_on_both_rpcs:
      !!primary?.found && primary.errors.length === 0 && !!secondary?.found && secondary.errors.length === 0,
    block_at_decode: Number(blockAtDecode),
    block_height_window: [Number(blockHeightStart), Number(blockHeightEnd)],
    primary_rpc: primary,
    secondary_rpc: secondary,
    latency_seconds: {
      n: samples.length,
      median: median(samples),
      iqr: [quantile(samples, 0.25), quantile(samples, 0.75)],
    },
    paid_http_status: payResult?.responseStatus ?? null,
    asserts_passed: assertOk,
    ran_at: nowIso(),
  };
  save("08-summary.json", summary);
  console.log(JSON.stringify(summary, null, 2));
  if (!assertOk && !SKIP_PAY) fail("assertion failures recorded in data/07-transfer-evidence.json");
}

main();
