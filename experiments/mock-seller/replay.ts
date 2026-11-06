/**
 * mock-seller replay: EIP-3009 replay test on a pinned Anvil fork of Base.
 *
 * Spawns `anvil --fork-url https://mainnet.base.org`, records the fork
 * block, funds a throwaway in-memory dev key (native gas via
 * anvil_setBalance, USDC via anvil_setStorageAt at the native-USDC balance
 * slot), settles a transferWithAuthorization, then re-submits the SAME
 * authorization (same nonce). Expected: the second settle reverts at the
 * EVM state level. The real MAINNET_PAYER_PRIVATE_KEY is never used here.
 *
 * Usage: bun experiments/mock-seller/replay.ts
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { createPublicClient, createWalletClient, http, parseAbi, keccak256, encodePacked } from "viem";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";
import { getAddress } from "viem";
import { base } from "viem/chains";

const USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const ANVIL_PORT = 18545;
const ANVIL_RPC = `http://127.0.0.1:${ANVIL_PORT}`;
const DATA_DIR = new URL("./data/", import.meta.url).pathname;
const USDC_ABI = parseAbi([
  "function transferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce,uint8 v,bytes32 r,bytes32 s)",
  "function balanceOf(address) view returns (uint256)",
  "function authorizationState(address,address,bytes32) view returns (bool,bool)",
]);

async function rpc(method: string, params: unknown[]): Promise<unknown> {
  const res = await fetch(ANVIL_RPC, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
  });
  const body = await res.json();
  if (body.error) throw new Error(`${method}: ${JSON.stringify(body.error)}`);
  return body.result;
}

async function main(): Promise<Record<string, unknown>> {
  const anvil = Bun.spawn(
    ["anvil", "--fork-url", "https://mainnet.base.org", "--port", String(ANVIL_PORT), "--quiet"],
    { stdout: "pipe", stderr: "pipe" },
  );
  try {
    // Wait for anvil readiness.
    let ready = false;
    for (let i = 0; i < 60; i++) {
      try {
        await rpc("eth_blockNumber", []);
        ready = true;
        break;
      } catch {
        await new Promise((r) => setTimeout(r, 500));
      }
    }
    if (!ready) throw new Error("anvil did not become ready");

    const forkBlock = Number(await rpc("eth_blockNumber", []));
    const account = privateKeyToAccount(generatePrivateKey());
    const payer = account.address;
    await rpc("anvil_setBalance", [payer, "0xde0b6b3a7640000"]); // 1 ETH gas
    // Bridged/native USDC on Base stores balances in a mapping at slot 9.
    const slot = keccak256(encodePacked(["uint256", "uint256"], [BigInt(payer), 9n]));
    await rpc("anvil_setStorageAt", [USDC_BASE, slot, `0x${(100000n * 1000000n).toString(16).padStart(64, "0")}`]);

    const publicClient = createPublicClient({ chain: base, transport: http(ANVIL_RPC) });
    const walletClient = createWalletClient({
      chain: base,
      transport: http(ANVIL_RPC),
      account: account,
    });
    const fundedBalance = await publicClient.readContract({
      address: USDC_BASE,
      abi: USDC_ABI,
      functionName: "balanceOf",
      args: [payer],
    });

    const to: `0x${string}` = getAddress("0x169313d28075a6ddb70e7e5190a1eddc0d105671");
    const value = 10000n * 1000000n; // 10000 USDC of the funded 100000
    const validAfter = 0n;
    const validBefore = BigInt(Math.floor(Date.now() / 1000) + 3600);
    const nonce = crypto.getRandomValues(new Uint8Array(32));

    const signature = await account.signTypedData({
      domain: { name: "USD Coin", version: "2", chainId: 8453, verifyingContract: USDC_BASE },
      types: {
        TransferWithAuthorization: [
          { name: "from", type: "address" },
          { name: "to", type: "address" },
          { name: "value", type: "uint256" },
          { name: "validAfter", type: "uint256" },
          { name: "validBefore", type: "uint256" },
          { name: "nonce", type: "bytes32" },
        ],
      },
      primaryType: "TransferWithAuthorization",
      message: { from: payer, to, value, validAfter, validBefore, nonce: `0x${Buffer.from(nonce).toString("hex")}` },
    });
    const v = Number.parseInt(signature.slice(-2), 16);
    const r = `0x${signature.slice(2, 66)}` as const;
    const s = `0x${signature.slice(66, 130)}` as const;
    const nonceHex = `0x${Buffer.from(nonce).toString("hex")}` as const;
    const args = [payer, to, value, validAfter, validBefore, nonceHex, v, r, s] as const;

    let firstStatus: string | null = null;
    let firstError: string | null = null;
    let secondError: string | null = null;
    let secondStatus: string | null = null;
    try {
      const firstHash = await walletClient.writeContract({
        address: USDC_BASE,
        abi: USDC_ABI,
        functionName: "transferWithAuthorization",
        args,
      });
      firstStatus = (
        await publicClient.waitForTransactionReceipt({ hash: firstHash, pollingInterval: 500 })
      ).status;
    } catch (err) {
      firstError = String(err).slice(0, 300);
    }
    try {
      const secondHash = await walletClient.writeContract({
        address: USDC_BASE,
        abi: USDC_ABI,
        functionName: "transferWithAuthorization",
        args,
      });
      secondStatus = (await publicClient.getTransactionReceipt({ hash: secondHash })).status;
    } catch (err) {
      secondError = String(err).slice(0, 300);
    }

    const replayRejected = firstStatus === "success" && secondStatus !== "success";
    return {
      mode: "replay",
      anvil_fork_block: forkBlock,
      dev_payer: payer,
      funded_usdc_base_units: fundedBalance.toString(),
      first_settle_status: firstStatus,
      first_settle_error: firstError,
      second_settle_status: secondStatus,
      second_settle_error: secondError,
      replay_rejected: replayRejected,
      detection_correct: replayRejected,
    };
  } finally {
    anvil.kill();
  }
}

mkdirSync(DATA_DIR, { recursive: true });
main().then((result) => {
  writeFileSync(`${DATA_DIR}replay.json`, `${JSON.stringify(result, null, 2)}\n`);
  console.log(JSON.stringify(result));
  if (!result.detection_correct) process.exit(1);
});
