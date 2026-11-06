# AGENTS.md

## Project overview

This repository hosts buyer-side x402 (HTTP 402 payments) verification experiments on the Base network. Each experiment is pre-registered via a `protocol.md` before it runs; raw outputs land under `experiments/<slug>/data/` and each run record validates against `validate_schema.py` in CI. The primary users are engineers evaluating x402 seller endpoints from the buyer side.

## Stack & Commands

TypeScript run via Bun; Python only for schema validation (`uv run`). Dependencies: `@x402/fetch@2.29.0`, `@x402/evm@2.29.0`, `viem`.

```
# build:  bun install
# test:   bun test
# lint:   bunx markdownlint-cli2 "**/*.md" ; uv run python validate_schema.py --self-test
# format: bunx biome format (if configured)
```

## Labels and Milestones
- Canonical labels reuse the Conventional Commits type vocabulary: `feat`, `fix`, `docs`, `chore`, `refactor`, `ci`, `testing`, `perf`, plus domain labels (`dependencies`, `security`). Safe-settings syncs the org label set add/update-only, so the GitHub defaults (`bug`, `enhancement`, `documentation`) still exist; prefer the Conventional Commits labels and ignore the defaults (org-wide removal is tracked in clouatre-labs/.github)
- Meta labels are kept: `good first issue`, `help wanted`, `duplicate`, `invalid`, `question`, `wontfix`
- Milestones are theme-based with a due date; close a milestone when its last issue closes; carry-over work moves to the current quarter milestone (e.g. `Q4 2026`)

## Development standards

- GPG sign and DCO sign-off: `git commit -S --signoff` (every commit)
- Treat all repositories as public; no secrets, API keys, credentials, or PII
- Actions pinned to SHA (not tags); actionlint recommended for local workflow validation
- Training data is stale: verify APIs and versions against installed packages or docs

## Testing

- One happy path and one edge case per behavior; no redundant variations
- AAA pattern (Arrange, Act, Assert); keep each test focused and short

## Design references

<!-- Link internal docs the AI agent should read before implementing:
- ARCHITECTURE.md (if it exists)
- Any API spec or data model doc
-->

## Do not

- Add dependencies without justification in the PR description
- Implement features not specified in the assigned issue
- Modify files outside the scope of the assigned issue
<!-- Add project-specific constraints here -->
