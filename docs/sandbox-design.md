# Sandbox design

Quant Bench evaluates an agent inside its execution harness while keeping host
state, credentials, repository files, hidden verifiers, reference solutions,
and prior-run artifacts outside the candidate boundary. The [benchmark design](benchmark-design.md)
defines the scored contract; this document defines the isolation boundary.

## Execution modes

The runner exposes three agent execution modes and two verifier modes:

- **host**: a diagnostic convenience mode; it does not provide benchmark
  isolation or official comparability;
- **bubblewrap**: a local isolation diagnostic for hosts with `bwrap`; and
- **Docker**: the official solve and verification path for `quant-terminal-v1`.

Official comparisons use Docker for both phases with the same locked task image.
A host or bubblewrap pass is useful for debugging installation and task logic,
but cannot be substituted for an official Docker result.

## Security contract

A candidate attempt may access only:

- a fresh `/workspace` copied from the task's public workspace;
- the task instruction supplied by the runner;
- a generated, credential-free home directory;
- read-only runtime dependencies needed to execute the agent harness; and
- a short-lived model-call gateway capability for the selected route.

It must not access:

- the repository or source task directory;
- `tests/`, `solution/`, expected-output files, or integrity mutants;
- provider API keys, OAuth refresh material, broker tokens, or the host OMP
  state directory;
- prior workspaces, result rows, logs, or model outputs;
- the Docker socket; or
- arbitrary host paths or host environment variables.

## Task boundary

A source task contains separate public and hidden views:

```text
tasks/<task-id>/
  task.toml
  instruction.md
  environment/
  workspace/       # public mutable input
  solution/        # hidden oracle
  tests/           # hidden verifier
```

For each attempt, the runner copies `instruction.md` and `workspace/` into a
fresh attempt directory. It never copies `tests/` or `solution/` into the solve
view or Docker build context. Candidate writes therefore cannot mutate source
fixtures or the verifier used by later attempts.

The solve and verifier use the same immutable task image ID. During
verification, the final workspace is mounted at `/workspace` and task tests are
mounted read-only at `/tests`.

## Docker controls

Official containers run with:

- `--network none` for task execution;
- a read-only root filesystem;
- `--cap-drop ALL` and `no-new-privileges`;
- task-declared CPU, memory, process, and timeout limits;
- isolated temporary filesystems for writable runtime paths;
- no host home, repository, credential, artifact, or Docker-socket mount; and
- an explicit command and environment assembled by the host runner.

Task images use digest-pinned base images. Quant Bench records the Dockerfile,
dependency, and base-image metadata under `org.quant-bench.*` labels and locks
the resulting immutable image IDs in
[`benchmarks/image-lock.json`](../benchmarks/image-lock.json).

## Credential boundary

Configure OMP and provider access on the host using the
[official OMP documentation](https://github.com/can1357/oh-my-pi#readme). Keep
API keys, OAuth tokens, provider `.env` files, `models.yml`, and the OMP agent
database in the external OMP agent directory (normally `~/.omp/agent`), never
in this checkout. If a non-default directory is used, point readiness checks at
it with `OMP_AGENT_DIR` and pass the same external directory to any helper that
explicitly requests `--agent-dir`.

The container receives model-call capability, not provider credentials:

1. The host starts a short-lived OMP authentication gateway.
2. A host-side UNIX-socket proxy exposes only the required gateway endpoint to
   the sandbox.
3. The generated sandbox OMP configuration routes the selected provider through
   that socket and contains no API key or host credential path.
4. Provider keys, OAuth tokens, the broker token, and the live OMP database stay
   host-side.
5. The gateway is stopped after the run.

A loopback `--no-auth` gateway still confers temporary spend capability to any
process that can reach it. The proxy socket and container mounts must therefore
be scoped to the active attempt, and the gateway must not be left running when
no evaluation is active.

The route smoke below starts the exact-model UNIX proxy, runs one sandboxed task
through it, and then stops the recorded gateway generation. It performs live
model-backed work and can incur provider charges; run it only after the
validator, doctor, image checks, no-op gate, and oracle smoke pass.

```bash
GATEWAY_RUN_ID=quant-bench-gateway-smoke
GATEWAY_SOCKET=/tmp/quant-bench-gateway-smoke.sock
ROUTE_RUN_ID="gateway-route-smoke-$(date -u +%Y%m%dT%H%M%SZ)"

python3 scripts/auth_gateway.py \
  --model-selector openai-codex/gpt-5.6-sol:max \
  --run-id "$GATEWAY_RUN_ID" \
  --unix-socket "$GATEWAY_SOCKET" \
  --keep-running
trap 'python3 scripts/auth_gateway.py --stop-run "$GATEWAY_RUN_ID" >/dev/null' EXIT

python3 scripts/quant_bench_runner.py \
  --manifest benchmarks/quant-terminal-v1.toml \
  --task-set official \
  --task-limit 1 \
  --attempts 1 \
  --agent-set completed_sol \
  --agent-execution docker \
  --verifier docker \
  --auth-gateway-socket "$GATEWAY_SOCKET" \
  --run-id "$ROUTE_RUN_ID"

python3 scripts/auth_gateway.py --stop-run "$GATEWAY_RUN_ID"
trap - EXIT
```

The helpers write status and logs under ignored `artifacts/` paths. Do not copy
those files into task workspaces or published results.

## Environment and tool boundary

The runner builds a small allowlisted environment rather than forwarding the
host environment. Secret-like variables are removed. The generated home may
contain only the minimal OMP agent and provider configuration needed for the
selected route; it must not contain `.env`, `agent.db`, request state, blobs,
history, or OAuth state.

The candidate tool set is explicit. Network-capable shell access is not paired
with a host-network namespace or host credential mount. Every writable path is
inside the attempt boundary.

## Verification boundary

The hidden verifier reads the candidate's final workspace and task-local test
fixtures. It does not inherit the agent process, model gateway, or candidate
environment. Verification also runs without network access and under the task's
resource limits.

The verifier may execute candidate-authored code only when the task contract
requires it. It must never run an arbitrary candidate entry point as an
unreviewed pre-test hook.

## Required proof

Before a model-backed matrix run:

1. `scripts/validate_bench_tasks.py` accepts the manifest and all public task
   views.
2. Host-only `scripts/bench_doctor.py --agent-execution host --verifier host`
   confirms the local installation; the official check additionally requires
   Docker and locked images.
3. A no-op solve is rejected by every promoted verifier.
4. Each reference solution passes repeatedly in the locked image.
5. Every declared integrity mutant is rejected repeatedly.
6. A one-task gateway smoke confirms that the sandbox can call only the
   selected route without receiving a credential.
7. Inspection of the attempt directory confirms that repository, hidden tests,
   solutions, host homes, prior artifacts, and secret-like environment values
   are absent.

Only after these checks should a paid or long-running evaluation begin.
