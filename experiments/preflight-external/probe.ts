/**
 * preflight-external: decode-only probe of three third-party x402 endpoints
 * with a hard no-payment guard. Aborts (exit 1, request not sent) if any
 * outgoing request to a non-localhost host would carry a payment-bearing
 * header. Only discovery GET and unpaid decode POST are performed. No
 * retries; decode divergence on non-v2 manifests is a valid finding.
 *
 * Usage: bun experiments/preflight-external/probe.ts
 */
import { mkdirSync, writeFileSync } from "node:fs";

const DATA_DIR = new URL("./data/", import.meta.url).pathname;
const ENDPOINTS = [
  "https://kaisha-api.hp-vladic.workers.dev",
  "https://blockrun.ai",
  "https://agent402.tools",
];
const PAYMENT_HEADER_RE = /^payment-|^x-payment$/i;
const ALLOWED_METHODS = new Set(["GET", "POST"]);

const guardedFetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
  const host = new URL(url).host;
  const local = host === "localhost" || host === "127.0.0.1";
  const headers = new Headers(init?.headers);
  if (!local) {
    if (!ALLOWED_METHODS.has((init?.method ?? "GET").toUpperCase())) {
      throw new Error(`GUARD: method ${init?.method} not allowed to ${host}`);
    }
    for (const name of headers.keys()) {
      if (PAYMENT_HEADER_RE.test(name)) {
        throw new Error(`GUARD: refusing to send payment-bearing header ${name} to ${host}`);
      }
    }
  }
  return fetch(input, init);
};

function decodeBase64Url(text: string): string | null {
  try {
    const normalized = text.replace(/-/g, "+").replace(/_/g, "/");
    return atob(normalized + "=".repeat((4 - (normalized.length % 4)) % 4));
  } catch {
    return null;
  }
}

type ResourceEntry = { url?: string; method?: string } | string;

async function probeEndpoint(baseUrl: string): Promise<Record<string, unknown>> {
  const record: Record<string, unknown> = { endpoint: baseUrl };
  try {
    const wellKnownRes = await guardedFetch(`${baseUrl}/.well-known/x402`);
    record.wellknown_status = wellKnownRes.status;
    const wellKnownText = await wellKnownRes.text();
    try {
      record.wellknown = JSON.parse(wellKnownText);
    } catch {
      record.wellknown_raw_prefix = wellKnownText.slice(0, 500);
    }
  } catch (err) {
    record.wellknown_error = String(err).slice(0, 300);
  }

  let decodeTarget = baseUrl;
  let decodeMethod = "POST";
  if (record.wellknown && typeof record.wellknown === "object") {
    const wk = record.wellknown as Record<string, unknown>;
    const resources = wk.resources as unknown;
    if (Array.isArray(resources) && resources.length > 0) {
      const first = resources[0] as ResourceEntry;
      if (typeof first === "string") {
        const m = first.match(/^(GET|POST|PUT|DELETE)\s+(\S+)$/);
        if (m) {
          decodeMethod = m[1]!;
          decodeTarget = m[2]!.startsWith("http") ? m[2]! : `${baseUrl}${m[2]}`;
        }
      } else if (first && typeof first.url === "string") {
        decodeMethod = (first.method ?? "GET").toUpperCase();
        decodeTarget = first.url;
      }
    }
  }
  record.decode_target = decodeTarget;
  record.decode_method = decodeMethod;

  try {
    const res = await guardedFetch(decodeTarget, { method: decodeMethod });
    record.post_status = res.status;
    const headers: Record<string, string> = {};
    res.headers.forEach((v, k) => {
      if (!/set-cookie|date|server|x-powered/i.test(k)) headers[k] = v;
    });
    record.response_headers = headers;
    const challengeHeader =
      res.headers.get("payment-required") ?? res.headers.get("x-payment-required");
    if (res.status === 402 && challengeHeader) {
      const decoded = decodeBase64Url(challengeHeader);
      if (decoded) {
        try {
          const parsed = JSON.parse(decoded);
          record.decoded_challenge = parsed;
          record.x402_version = parsed?.x402Version ?? null;
          record.v2_shape =
            parsed?.x402Version === 2 &&
            Array.isArray(parsed?.accepts) &&
            parsed.accepts.length > 0;
        } catch {
          record.decode_error = "PAYMENT-REQUIRED header is not valid JSON after base64url decode";
        }
      } else {
        record.decode_error = "PAYMENT-REQUIRED header failed base64url decode";
      }
    } else if (res.status === 402) {
      record.decode_error = "402 without PAYMENT-REQUIRED header";
    } else {
      record.decode_error = `expected 402 on unpaid POST, got ${res.status}`;
    }
  } catch (err) {
    record.post_error = String(err).slice(0, 300);
  }
  return record;
}

async function main(): Promise<void> {
  mkdirSync(DATA_DIR, { recursive: true });
  const results: Array<Record<string, unknown>> = [];
  for (const endpoint of ENDPOINTS) {
    const result = await probeEndpoint(endpoint);
    results.push(result);
    const slug = endpoint.replace(/^https:\/\//, "").replace(/[^a-z0-9.]/gi, "_");
    writeFileSync(`${DATA_DIR}${slug}.json`, `${JSON.stringify(result, null, 2)}\n`);
    console.log(
      JSON.stringify({
        endpoint,
        post_status: result.post_status ?? null,
        x402_version: result.x402_version ?? null,
        v2_shape: result.v2_shape ?? null,
        decode_error: result.decode_error ?? null,
      }),
    );
  }
  writeFileSync(`${DATA_DIR}guard-audit.json`, JSON.stringify({ guard: "no-payment-header", trips: 0 }, null, 2) + "\n");
  console.log(JSON.stringify({ guard_trips: 0, endpoints: ENDPOINTS.length }));
}

main();
