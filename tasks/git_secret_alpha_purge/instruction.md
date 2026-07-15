Rewrite the history of the Git repository in the workspace to purge sensitive leaked data.

### Background
During past development of the Alpha Inference Engine, a large binary file `alpha_weights.bin` (model weights) and a production credentials API token `alpha-prod-tok-991283` (inside `config.json`) were committed to the repository history.

Although these files and values were deleted/updated in the latest commit on `main`, they are still fully reachable through historical commits, branch points, and merges. This leaks credentials and balloons the size of the repository.

### Requirements

1. Complete `purge_alpha.py` in the workspace:
   - Implement `purge_repository(repo_path: Path)` which performs surgical history rewriting on the Git repository located at `repo_path`.
   - **Remove `alpha_weights.bin`**: The file must be completely purged from all commits in the repository history. This means no commit, tree, or blob in the rewritten history may contain `alpha_weights.bin`. Discard any commit file-addition, modification, or deletion operations for this file.
   - **Scrub secret credentials**: Any occurrence of the production token `"alpha-prod-tok-991283"` in any historical version of `config.json` must be replaced with the word `"REDACTED"`.
   - **Preserve Merge Topology**: The exact branch structure and merge topology (specifically the merge commit uniting the main line and the `feature/inference` branch) must be preserved. Commit messages, author details, dates, and order must remain unchanged.
   - **Update References**: Both the `main` and `feature/inference` local branch references must be updated to point to the new rewritten head commits.
   - **Database Hygiene**: The rewritten repository must be clean: expire the reflog and prune all dangling objects so that the leaked binary and token are no longer stored in the Git database.

2. Run `run_purge.py` to evaluate the purge and generate the file `outputs/purge_report.json` in the workspace.

### Constraints
- You may use standard Python modules and standard `git` CLI operations (via `subprocess`).
- Do NOT use external tools like BFG Repo-Cleaner or `git-filter-repo` as they are not pre-installed in the environment.
- The latest/current working directory files on `main` must remain completely intact and unchanged, except that any leaked token is removed.
- Your solution must be robust to changes in metadata, commit messages, or dates.
