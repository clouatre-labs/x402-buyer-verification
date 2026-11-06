# Data Dictionary

This document defines the schema and field meanings for experiment data files in this repository. `validate_schema.py` enforces the required fields below; run `uv run python validate_schema.py` before every PR that touches `experiments/`.

## Layout

Each experiment directory `experiments/<slug>/` contains:

- `analysis.json`: run metadata, message counts, and evaluation scores (schema below)
- `scores.json`: per-criterion rubric scores with justifications
- `protocol.md`, `runner-prompt.md`, `scorer-prompt.md`: pre-registration artifacts
- `sessions/`: raw session logs or database exports

## analysis.json

### Top-level schema

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `experiment` | string | no | Experiment slug, matches the directory name |
| `schema_version` | string | no | Version of this schema the record conforms to |
| `title` | string | no | Human-readable experiment title |
| `issue` | string \| null | yes | Target issue or task reference |
| `date` | string | no | Experiment date (YYYY-MM-DD) |
| `model` | string | no | Model identifier under test |
| `n_per_group` | integer | no | Number of runs per group |
| `control_condition` | string | no | Description of the control condition |
| `treatment_condition` | string | no | Description of the treatment condition |
| `rubric_version` | string | no | Rubric identifier used for scoring |
| `orchestrator_session` | string \| null | yes | Orchestrator session reference, if any |
| `repo_head` | string | no | Repository commit at run time |
| `experiment_start` | string | no | ISO 8601 timestamp with UTC offset of first run |
| `experiment_end` | string | no | ISO 8601 timestamp with UTC offset of last run |
| `analyzed_at` | string | no | ISO 8601 timestamp with UTC offset of analysis |
| `runs` | object | no | Map of run ID to run record |
| `scores` | object | no | Scoring summary keyed by run ID |
| `statistical_test` | string | no | Pre-registered statistical test name |
| `conclusion` | string | no | Result summary |
| `pre_acknowledged_limitations` | array | no | Limitations stated before analysis |

### Run record schema

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `group` | string | no | `control` or `treatment` |
| `session_id` | string | no | Session identifier from the run harness |
| `messages` | integer | no | Message count in the session |
| `input_tokens` | integer | no | Accumulated input tokens |
| `output_tokens` | integer | no | Accumulated output tokens |
| `total_tokens` | integer | no | Sum of input and output tokens |
| `wall_clock_seconds` | number | no | Elapsed wall-clock seconds |
| `bytes` | integer \| null | yes | Session byte size, if recorded |
| `note` | string \| null | yes | Optional note (e.g. failure reason) |

## payment-run records

Experiments that exercise the x402 payment protocol set `record_type:
"payment-run"` at the top level. Absence of `record_type` means the original
`model-run` schema above; both are enforced by `validate_schema.py`.

### Additional top-level fields (payment-run)

| Field | Type | Description |
|-------|------|-------------|
| `record_type` | string | `"payment-run"` (absent means model-run) |
| `versions` | object | Tool versions: required keys `bun`, `node`, `x402_fetch`, `x402_evm`; optional `anvil`, `anvil_fork_block` |
| `rpc_endpoints` | string array | Non-empty list of RPC endpoints used for on-chain verification |

### Payment run record schema

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `mode` | string | no | Scenario label (e.g. `happy-path`, `amount-mismatch`, `replay`, `decode-only`) |
| `settled` | boolean | no | Whether a settlement transaction was attempted and confirmed |
| `tx_hash` | string | see note | `0x` + 64 hex chars; required non-null when `settled` is true; must be null when `settled` is false |
| `payer` | string | no | `0x` + 40 hex chars; address that signed the EIP-3009 authorization |
| `pay_to` | string | no | `0x` + 40 hex chars; address the challenge advertised as recipient |
| `amount_usdc` | number | no | USDC amount in human units (e.g. 0.01); 0 for unpaid runs |
| `receipt` | object | see note | Settlement receipt as returned by the server; required non-null when `settled` is true |
| `wall_clock_seconds` | number | yes | Descriptive elapsed time; not a performance measurement |
| `note` | string | yes | Optional note |

The `scores` object retains its shape (run ID to object) for both record
types; payment experiments use it for per-run detection/assertion outcomes.

## SDK-vs-harness attribution table

Every payment experiment's README must include a table attributing each
observed behavior to its source: the x402 SDK (client, EVM scheme,
facilitator client), the experiment harness (this repository's scripts), or
the remote service (resource server, facilitator). One row per checked
behavior; the harness must not re-implement SDK internals in a way that
makes detection circular (detectors mirror the same checks that are run
against the real endpoint).

## scores.json

Free-form per-criterion scoring keyed by run ID; each entry SHOULD include the score value, per-criterion results, and scorer justifications.
