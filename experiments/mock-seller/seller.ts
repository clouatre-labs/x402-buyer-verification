/**
 * mock-seller: hostile localhost x402 seller for buyer-side detector testing.
 *
 * Modes:
 *   amount-mismatch      challenge amount differs from the seller manifest
 *   payTo-mismatch       challenge payTo differs from the seller manifest
 *   receipt-missing-key  settlement receipt drops `transaction` or `settledAmountUsdc`
 *   baseline             fully consistent seller (negative control)
 *
 * Usage: bun experiments/mock-seller/seller.ts --mode <mode> --port <port>
 */
import { getAddress } from "viem";

function parseArgs(): { mode: string; port: number } {
  const get = (name: string, fallback?: string) => {
    const i = process.argv.indexOf(`--${name}`);
    return i >= 0 ? process.argv[i + 1] : fallback;
  };
  const mode = get("mode", "baseline")!;
  const allowed = ["baseline", "amount-mismatch", "payTo-mismatch", "receipt-missing-key"];
  if (!allowed.includes(mode)) {
    console.error(`FAIL: unknown mode ${mode}; allowed: ${allowed.join(", ")}`);
    process.exit(1);
  }
  return { mode, port: Number(get("port", "4021")) };
}

const USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const MANIFEST_PAY_TO = getAddress("0x169313d28075a6ddb70e7e5190a1eddc0d105671");
const MANIFEST_AMOUNT = "10000";

const { mode, port } = parseArgs();

// Mutations apply ONLY to the challenge, never to the manifest.
const challengePayTo =
  mode === "payTo-mismatch" ? getAddress("0x269313d28075a6ddb70e7e5190a1eddc0d105671") : MANIFEST_PAY_TO;
const challengeAmount = mode === "amount-mismatch" ? "99999" : MANIFEST_AMOUNT;

function encodeBase64Url(text: string): string {
  return btoa(text).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function paymentRequiredJson(): string {
  return JSON.stringify({
    x402Version: 2,
    resource: { url: `http://localhost:${port}/v1/echo`, description: "mock seller echo" },
    accepts: [
      {
        scheme: "exact",
        network: "eip155:8453",
        asset: USDC_BASE,
        amount: challengeAmount,
        payTo: challengePayTo,
        maxTimeoutSeconds: 60,
        extra: { name: "USD Coin", version: "2" },
      },
    ],
  });
}

function settlementReceiptJson(): string {
  const base: Record<string, unknown> = {
    success: true,
    network: "eip155:8453",
    payer: getAddress("0xcccccccccccccccccccccccccccccccccccccccc"),
    settledAmountUsdc: "10000",
    transaction: "0x" + "ab".repeat(32),
  };
  if (mode === "receipt-missing-key") {
    // Drop one settlement identity key, alternating by port parity.
    if (port % 2 === 0) delete base.transaction;
    else delete base.settledAmountUsdc;
  }
  return JSON.stringify(base);
}

const manifest = {
  x402Version: 2,
  accepts: [
    {
      scheme: "exact",
      network: "eip155:8453",
      asset: USDC_BASE,
      amount: MANIFEST_AMOUNT,
      payTo: MANIFEST_PAY_TO,
      maxTimeoutSeconds: 60,
      extra: { name: "USD Coin", version: "2" },
    },
  ],
};

Bun.serve({
  port,
  async fetch(req) {
    const url = new URL(req.url);
    if (req.method === "GET" && url.pathname === "/.well-known/x402") {
      return Response.json(manifest);
    }
    if (req.method === "POST" && url.pathname === "/v1/echo") {
      const paymentHeader = req.headers.get("payment-signature") ?? req.headers.get("x-payment");
      if (!paymentHeader) {
        return new Response(JSON.stringify({ error: "payment required" }), {
          status: 402,
          headers: {
            "content-type": "application/json",
            "payment-required": encodeBase64Url(paymentRequiredJson()),
          },
        });
      }
      // Hostile seller "settles" locally and always reports success.
      return new Response(JSON.stringify({ echo: "paid" }), {
        status: 200,
        headers: {
          "content-type": "application/json",
          "payment-response": encodeBase64Url(settlementReceiptJson()),
        },
      });
    }
    return new Response("not found", { status: 404 });
  },
});

console.log(JSON.stringify({ mode: mode, port: port, manifest: manifest }));
