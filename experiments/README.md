# Experiments

One directory per pre-registered experiment: `experiments/<slug>/`.

`experiments/example-fixture/` is a complete minimal scaffold and the CI
schema-validation fixture; copy it when starting a real experiment. CI
validates every `experiments/*/analysis.json`, so an experiment directory
without `analysis.json` fails the build.

## Payment experiments

Experiments that exercise the x402 payment protocol set
`record_type: "payment-run"` in `analysis.json` (see DATA_DICTIONARY.md).
Raw outputs from every run (challenge headers, receipts, on-chain event
evidence, probe transcripts) are committed under `data/` inside the
experiment directory. Each experiment's README includes an SDK-vs-harness
attribution table mapping every checked behavior to the x402 SDK, this
repository's harness, or the remote service.

## Required Layout

```text
experiments/<slug>/
  protocol.md        # pre-registered design: task, groups, sample size, statistical test
  runner-prompt.md   # exact prompt given to the runner/agent
  scorer-prompt.md   # exact prompt given to the scorer
  analysis.json      # run metadata and scores (schema in DATA_DICTIONARY.md)
  scores.json        # per-criterion rubric scores with justifications
  sessions/          # raw session logs or database exports
```

## Workflow

1. Commit `protocol.md`, `runner-prompt.md`, and `scorer-prompt.md` BEFORE running anything.
2. Run the experiment; store raw artifacts under `sessions/`.
3. Score blind against the rubric; write `scores.json`.
4. Summarize into `analysis.json` and validate: `uv run python validate_schema.py`. Validation iterates every `experiments/*/` directory; one missing `analysis.json` is a validation error (exit 1).
5. Write derived tables and figures to `results/` and `figures/` respectively; keep raw artifacts in `sessions/`.
6. Update the experiment index table in the repository README.
