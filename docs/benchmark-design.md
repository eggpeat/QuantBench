# Benchmark design

## Scope

Quant Bench measures whether terminal agents can complete applied quantitative,
data, and systems work inside a constrained workspace. The frozen
`quant-terminal-v1` suite contains 40 text-only tasks across:

- software engineering and debugging;
- data engineering and data quality;
- statistical and Bayesian modeling;
- forecasting, calibration, and feature selection;
- scientific and numerical computing;
- quantitative finance, poker, and risk;
- sports modeling and market operations; and
- operational reliability and repository hygiene.

The unit of comparison is the complete agent configuration: exact model
selector, backend provider, thinking level, harness, task image, and benchmark
manifest. Quant Bench does not claim to isolate raw model capability from its
execution harness.

## Frozen v1 contract

[`benchmarks/quant-terminal-v1.toml`](../benchmarks/quant-terminal-v1.toml) is the
scored v1 source of truth. It defines:

- the ordered set of 40 official task IDs;
- five independent attempts per task and configuration;
- at most three retries for retryable infrastructure failures;
- exact agent metadata used by reproducible runs;
- an eight-task pilot subset for diagnostics; and
- task-integrity mutants that must be rejected by hidden verifiers.

Task IDs, attempt numbers, agent configuration, and run IDs form result
identity. Changing any scored task, verifier, fixture, dependency, image, or
resource budget requires a new benchmark version. Historical result rows must
not be silently reinterpreted under a changed contract.

## Task structure

Each promoted task follows this boundary:

```text
tasks/<task-id>/
  README.md
  task.toml
  instruction.md
  environment/
    Dockerfile
    requirements.txt        # when needed
  workspace/                # only mutable candidate input
  solution/                 # oracle; never shown during solve
  tests/                    # verifier; never shown during solve
```

`task.toml` uses the repository's declared schema and the
`quant-bench/<task-id>` namespace. It records resource limits, time budgets,
category, difficulty, provenance, promotion status, canary secrets, and the
verifier command. The manifest path and task ID must agree.

A promoted task must satisfy all of these conditions:

1. The public workspace is non-empty and contains no tests, solutions, expected
   outputs, provider credentials, or absolute home-directory paths.
2. The instruction defines observable outputs and leaves meaningful work for the
   agent.
3. The reference solution passes the verifier repeatedly.
4. The unchanged public workspace fails the verifier unless the fixture is
   intentionally pre-solved.
5. A plausible shortcut mutant fails repeatedly.
6. The verifier is deterministic, bounded, and independent of network access.
7. The task image uses a digest-pinned base and dependency set.

The [task corpus index](../tasks/README.md) links every official task contract.

## Solve and verification boundary

Before an attempt, the runner creates a fresh directory containing only
`instruction.md` and a copy of `workspace/`. `tests/` and `solution/` stay in
the source task directory and are not part of the solve image context.

Official agent solves and verification use the same immutable task image ID. The
agent may mutate only `/workspace`. Verification mounts the final workspace
read/write and mounts `/tests` read-only. The verifier does not run a candidate
entry point unless the task contract explicitly requires one.

Docker runs enforce:

- no task network access;
- a read-only root filesystem except declared temporary mounts;
- dropped Linux capabilities and `no-new-privileges`;
- task-declared CPU, memory, process, and timeout limits; and
- no repository, Docker socket, host credential, or prior-run mounts.

OMP-backed solves receive model access through a credential-free gateway
boundary. Provider credentials stay on the host. The candidate process sees
neither provider secrets nor the host OMP state directory.

Host and bubblewrap modes are diagnostics. Docker solve plus Docker verification
is the official comparability path for `quant-terminal-v1`.

## Attempts, retries, and terminal status

Each official configuration receives five independent attempts for every task.
Task-local `[agent].timeout_sec` and `[verifier].timeout_sec` values define the
budget; the environment has a separate build timeout.

Terminal statuses have distinct meanings:

- `PASS`: the agent completed and the hidden verifier accepted the workspace.
- `REJECT`: the agent completed, but the deterministic verifier rejected the
  result. Semantic failures are not retried within an attempt.
- `TIME_LIMIT`: the agent or verifier exceeded its declared time budget. This is
  a right-censored, budgeted non-pass and is not retried at the same budget.
- `INFRA_BLOCKED`: transport, authentication, provider, image, or runtime
  infrastructure prevented a semantic outcome. Only retryable infrastructure
  failures receive the manifest retry limit.
- `DRY_RUN`: scheduling metadata only; never scored or published as an outcome.

Result rows are append-only. A repair writes a new row with
`supersedes_result_id`; reports score only the latest unsuperseded head for each
configuration, task, and attempt cell.

## Scoring and comparability

The primary public score is budgeted pass rate:

$$
\text{budgeted pass rate} =
\frac{\text{PASS}}
{\text{PASS} + \text{REJECT} + \text{TIME\_LIMIT}}.
$$

The semantic pass rate excludes right-censored time limits:

$$
\text{semantic pass rate} =
\frac{\text{PASS}}
{\text{PASS} + \text{REJECT}}.
$$

`INFRA_BLOCKED` is excluded from both rates because it is not a semantic or
budgeted result. A configuration is comparable only when all 200 expected cells
are terminal, no cell is infrastructure-blocked, every row records Docker solve
and verification, every task image matches the checked-in lock, and each source
run matches one of the manifest's exact accepted digests: the current
publication digest or its declared preserved-results digest.

For complete attempts, the report includes the minimum and maximum semantic
pass rates across the five attempt numbers. This is a descriptive stochastic
range, not a confidence interval. Reports also retain verified duration,
covered token totals, weighted cache-read ratio, provider-reported throughput,
and end-to-end wall throughput when those fields are complete. Missing runtime
fields remain missing rather than being imputed.

## Reproduction and publication

Start with the [repository quickstart](../README.md#quickstart). For a
model-backed run, keep OMP credentials in the host-side OMP configuration and
route requests through the short-lived credential-free gateway described in
[the sandbox design](sandbox-design.md). Do not copy credentials, raw prompts,
agent outputs, or local run directories into version control.

Use explicit run IDs and aggregate only complete runs:

```bash
python3 scripts/bench_report.py RUN_ID [RUN_ID ...] \
  --artifact-root artifacts/quant-bench-runs \
  --json-output /tmp/quant-bench-report.json \
  --markdown-output /tmp/quant-bench-report.md
```

A public comparison must:

1. pass explicit run IDs to `scripts/bench_report.py`;
2. include only configurations with a complete 40 × 5 terminal matrix;
3. bind every source run to the current publication digest or the exact
   preserved-results digest declared by that publication manifest;
4. match row and status execution modes and image IDs to the checked-in lock;
5. retain exact configuration and metric definitions;
6. publish both Markdown and machine-readable JSON aggregates;
7. omit partial runs instead of ranking them on observed subsets; and
8. keep credentials, raw prompts, agent outputs, and local run directories out
   of version control.

The public manifest intentionally lists only completed configurations and
records the common historical digest used by their preserved run artifacts.
The published report exposes the publication digest, preserved-results digest,
and exact accepted digest set so the distinction is machine-readable. An
unrelated digest still fails closed.

## Validation workflow

The following commands are read-only unless an explicit build or run flag is
provided. They require only the host Python standard library plus PyYAML from
the root [`requirements.txt`](../requirements.txt).

Validate the manifest, task structure, provenance, public workspace, and
integrity declarations:

```bash
python3 scripts/validate_bench_tasks.py benchmarks/quant-terminal-v1.toml
```

Run host-only readiness diagnostics when Docker is unavailable or when checking
the local installation. This is not an official benchmark execution:

```bash
python3 scripts/bench_doctor.py \
  --manifest benchmarks/quant-terminal-v1.toml \
  --agent-execution host \
  --verifier host
```

For the official Docker path, build and verify the locked images, then run a
small deterministic oracle smoke:

```bash
python3 scripts/quant_bench_runner.py \
  --manifest benchmarks/quant-terminal-v1.toml \
  --task-set official \
  --build-images
python3 scripts/bench_doctor.py \
  --manifest benchmarks/quant-terminal-v1.toml \
  --require-images
python3 scripts/quant_bench_runner.py \
  --manifest benchmarks/quant-terminal-v1.toml \
  --task-set official \
  --task-limit 1 \
  --attempts 1 \
  --oracle \
  --agent-execution docker \
  --verifier docker \
  --run-id design-oracle-smoke
```

Before a paid or long-running matrix, run the
[exact-model route smoke](sandbox-design.md#credential-boundary) with the
selector intended for the evaluation. That lifecycle starts the UNIX proxy,
executes one sandboxed task, and stops the gateway; health and model-list
probes alone do not establish the route boundary. Candidate and task listing
commands remain read-only and must not launch model requests.

## Contribution and known limits

Add tasks according to the checklist in [`tasks/README.md`](../tasks/README.md):
keep hidden tests, solutions, expected outputs, and credentials out of the
public solve view; use deterministic bounded verification; and run the
validator, no-op gate, oracle, and integrity-mutant checks before promotion.

The suite is intentionally text-only and cannot represent every production
workload. Hidden deterministic verifiers favor contracts that can be checked
mechanically. Scores compare frozen configurations under one resource budget;
they do not establish universal model rankings. Provider or harness changes can
alter results even when a selector string is unchanged, so exact run metadata
matters.
