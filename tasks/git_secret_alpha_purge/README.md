# git_secret_alpha_purge

## Overview

This task asks the agent to rewrite the history of a Git repository to completely remove a leaked binary file (`alpha_weights.bin`) and replace a production API secret token (`alpha-prod-tok-991283`) with `"REDACTED"` in all historical versions of `config.json`. The candidate must ensure the merge topology, branch names, commit authors, messages, and dates are preserved.

The candidate must complete `purge_alpha.py` and ensure running `run_purge.py` successfully scrubs the repository and outputs the validation report at `outputs/purge_report.json`.

## Source Grounding & Provenance

- **Source Tasks**: Concept-level adaptation of Git repository surgery and database history scrubbing.
- **Parent Behavior Preserved**:
  - Surgical removal of sensitive files and secret patterns from the complete commit history.
  - Updating all local references (branches, tags) to rewritten commits.
- **Domain Translation Added**:
  - Sets up an active git repository fixture in the candidate workspace.
  - The candidate must write a Python script `purge_alpha.py` that parses the git database (e.g. via fast-export/fast-import or git filter-branch) and outputs a detailed JSON report of modified commits.
- **Verifier Anti-Cheat & Robustness**:
  - The verifier resists static-output copying. In addition to testing if `purge_report.json` matches the static expected snapshot, it dynamically imports the candidate's `purge_alpha` module and runs it on a newly generated, randomized git history structure with distinct commit messages, dates, and file structures. It checks that no copy of the secret or binary remains anywhere in the reflog or Git objects.
- **Promotion Readiness**:
  - Promoted after all provenance and verifier-integrity blockers were cleared.

## What It Tests

- Understanding of the Git object model (commits, trees, blobs).
- Git history rewriting, fast-export, and fast-import.
- Merge preservation and DAG manipulation in Git.
- Parsing binary streams and rewriting file contents dynamically.
- Working with git subprocess calls and workspace environment variables safely.

## Environment

- Docker image: `python:3.13-slim-bookworm` (with `git` installed)
- Standard-library Python only.
- No network access.

## Inputs

An active Git repository initialized in `workspace/` containing a merge commit and a leaked binary weights file and credentials in its history.

## Required Outputs

Scrubbed Git repository history and `workspace/outputs/purge_report.json`.

## Verification

`tests/test_outputs.py` imports `purge_alpha.py` and verifies:
1. `outputs/purge_report.json` exactly matches `tests/expected.json` for the public fixture.
2. Runs the candidate's implementation on a newly generated randomized Git repository to check that leaks are fully removed, git fsck passes, merge topology is intact, and no secrets remain in unreachable/reflog database states.
