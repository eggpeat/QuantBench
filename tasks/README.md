# Quant Bench task corpus

This index covers the 40 task directories registered in
[`benchmarks/quant-terminal-v1.toml`](../benchmarks/quant-terminal-v1.toml).
Links are grouped by each task's `metadata.category`; a task README, when
present, describes its observable contract and runtime constraints.

The summaries below are intentionally capability-level. They explain the
problem each task represents without exposing formulas, implementation steps,
verifier cases, or hidden evaluation details. During a benchmark run, the
solver receives only the task's `instruction.md` and `workspace/`; these
repository-facing summaries are not staged into the solve environment.

## Use the corpus

List the frozen official task IDs without launching a model request:

```bash
python3 scripts/quant_bench_runner.py \
  --manifest benchmarks/quant-terminal-v1.toml \
  --task-set official \
  --list-tasks
```

Validate the manifest, task layout, public workspaces, and integrity declarations:

```bash
python3 scripts/validate_bench_tasks.py benchmarks/quant-terminal-v1.toml
```

A deterministic one-task oracle check uses the locked Docker image and does not
call a model. Replace `<task-id>` with one ID from the list:

```bash
python3 scripts/quant_bench_runner.py \
  --manifest benchmarks/quant-terminal-v1.toml \
  --task-set official \
  --task <task-id> \
  --attempts 1 \
  --oracle \
  --agent-execution docker \
  --verifier docker \
  --run-id task-oracle-smoke
```

Host and bubblewrap execution modes are diagnostics. Docker solve plus Docker
verification is required for an official comparison.

## Add a task

A task directory separates public solve inputs from hidden evaluation material:

```text
tasks/<task-id>/
  README.md                 # public contract and constraints
  task.toml                 # schema, resources, and verifier command
  instruction.md            # public agent instruction
  environment/
    Dockerfile              # digest-pinned image definition
    requirements.txt        # task-only dependencies, when needed
  workspace/                # public mutable input
  solution/                 # hidden reference solution
  tests/                    # hidden verifier and mutants
```

When proposing a task:

1. Choose a unique, stable `snake_case` task ID and create the layout above.
2. Keep the public instruction and workspace self-contained, deterministic, and
   meaningful. Do not place tests, solutions, expected outputs, credentials,
   answer keys, or absolute home-directory paths in the public view.
3. Declare resource and timeout limits in `task.toml`; pin the environment base
   image by digest and record only task-local dependencies.
4. Add the task to the manifest's task list and the appropriate task set, then
   add its link to this index.
5. Run the validator, the unchanged-workspace no-op gate, the reference oracle,
   and each declared integrity mutant. Repeat stochastic oracles when the task
   contract requires it.
6. Describe the observable outputs and verifier contract in the task README.

Task IDs and manifest order are part of result identity. Changing a promoted
task's verifier, fixtures, dependency set, image, or resource budget requires a
new benchmark version rather than silently changing historical results. Keep
all generated run directories under ignored `artifacts/` and keep credentials in
host-side OMP configuration, never in a task directory.

## Data engineering

| Task | What it tests |
| --- | --- |
| [Odds feed data merger](odds_feed_data_merger/) | Combining differently formatted sportsbook feeds into consistent records while detecting duplicates and conflicting data. |
| [News batch scheduler](llm_news_batch_scheduler/) | Scheduling simulated AI news-scoring jobs reliably while respecting batching, request-rate, and retry limits. |
| [Bitemporal as-of join](bitemporal_asof_join/) | Finding the record version that was both valid and known at a requested point in time. |
| [Incremental feature materialization](incremental_feature_materialization/) | Updating derived features from new events without reprocessing all history or corrupting saved progress after an interruption. |

## Data science

| Task | What it tests |
| --- | --- |
| [Bayesian simulation diagnostics](bayesian_mcmc_rhat_diagnostic/) | Assessing whether repeated statistical simulation chains agree and estimating how much independent information they contain. |
| [Live market Kalman filter](kalman_live_market_filter/) | Tracking an underlying market value from noisy updates while handling observations that appear abnormal. |
| [Advertising rate shrinkage](empirical_bayes_ctr_shrinkage/) | Stabilizing click-rate estimates for low-volume advertisements by combining individual results with evidence from the full population. |
| [Player skill shrinkage](empirical_bayes_true_skill/) | Estimating player ability from uneven amounts of performance data without overreacting to small samples. |
| [Client-model data quality audit](data_quality_leakage_client_model/) | Finding unusable records and future-information leakage before building a time-ordered training and validation dataset. |
| [Two-dimensional market tracker](kalman_2d_market_tracker/) | Tracking both market level and trend from noisy observations while recognizing sudden changes in behavior. |
| [Out-of-fold uncertainty calibration](heteroscedastic_oof_calibration/) | Producing leakage-safe cross-validated predictions and calibrating uncertainty that changes from one observation to another. |
| [Vectorized Fisher preconditioner](vectorized_fisher_preconditioner/) | Rescaling batches of machine-learning gradients with a memory-efficient estimate of each parameter's curvature. |
| [Probabilistic forecast scoring](crps_vectorization_and_scoring/) | Measuring the accuracy of distribution-based and sample-based forecasts while keeping large calculations memory-efficient. |
| [Weighted temporal inference](temporal_ep_weighted_likelihood/) | Estimating a changing hidden signal from differently weighted observations using approximate Bayesian inference. |
| [Linear residual boosting](linear_residual_boosting_pipeline/) | Combining a linear baseline with a tree model without data leakage, then saving and restoring the fitted model. |
| [Constrained portfolio optimizer](portfolio_optimizer_constraints/) | Allocating investments to reduce risk while honoring return goals and practical limits on assets, sectors, and trading. |

## Data systems

| Task | What it tests |
| --- | --- |
| [Sports backtest query optimization](sports_backtest_query_optimize/) | Speeding up a complex historical betting query through database indexing and query-plan analysis without changing its results. |

## Deep quant

| Task | What it tests |
| --- | --- |
| [Poker shove-or-fold equity](poker_shove_fold_equity/) | Evaluating whether an all-in poker decision is profitable and how often opponents must fold for it to break even. |
| [Portfolio loss risk](quant_var_expected_shortfall/) | Estimating likely and severe portfolio losses from historical asset returns at a chosen confidence level. |
| [Poker side-pot resolution](poker_side_pot_resolution_engine/) | Distributing chips correctly when poker hands include folds, all-in limits, tied winners, and multiple side pots. |
| [Cointegration pairs analysis](quant_cointegration_pairs_trade/) | Distinguishing price series with a stable long-run relationship from series that are merely correlated. |
| [Poker range equity engine](range_equity_engine/) | Comparing poker hands and ranges by exact enumeration or reproducible simulation across valid card combinations. |

## Feature selection

| Task | What it tests |
| --- | --- |
| [Knockoff false-discovery control](feature_selection_knockoff_fdr/) | Selecting useful variables while statistically limiting the expected share of false discoveries. |
| [Incremental Schur feature selector](incremental_schur_feature_selector/) | Choosing complementary variables one at a time while updating the required linear-algebra state efficiently. |
| [Stability selection](stability_selection_resampling/) | Finding variables that remain useful across repeated group-aware or time-aware samples with missing and weighted data. |

## Machine learning

| Task | What it tests |
| --- | --- |
| [Distributional boosting stability](distributional_boosting_boundary_stability/) | Keeping probability-model gradient calculations finite and accurate near extreme parameter limits. |

## Operations

| Task | What it tests |
| --- | --- |
| [Async odds scraper shutdown](async_odds_scraper_shutdown/) | Running asynchronous scraping jobs with limited concurrency while preserving result order and cleaning up safely after cancellation. |

## Probabilistic ML

| Task | What it tests |
| --- | --- |
| [Adaptive conformal intervals](adaptive_conformal_intervals/) | Building prediction intervals that account for groups, time ordering, and observation weights while maintaining reliable coverage. |

## Quantitative finance

| Task | What it tests |
| --- | --- |
| [Event-driven backtest repair](event_driven_backtest_repair/) | Repairing a trading backtest so events, orders, corporate actions, costs, and portfolio accounting follow real-world timing. |

## Scientific computing

| Task | What it tests |
| --- | --- |
| [Adaptive differential-equation solver](adaptive_ode_event_integration/) | Solving a changing system efficiently while locating important events that occur between numerical integration steps. |
| [Sparse linear solver](sparse_linear_solver/) | Solving large systems of linear equations stored sparsely without consuming memory as if every entry were present. |

## Sports modeling

| Task | What it tests |
| --- | --- |
| [Sportsbook margin removal](sports_hold_vig_removal/) | Converting quoted odds into fair probabilities, identifying favorable bets, and sizing exposure with controlled risk. |
| [Injury and line-movement audit](sports_injury_steam_audit/) | Comparing injury news with betting-line movement to judge whether the market has already reacted. |
| [Settlement ledger reconciliation](sports_settlement_ledger_reconciliation/) | Matching internal betting transactions to payment-processor records while handling fees, duplicates, and time differences. |
| [Football prop model translation](stan_to_python_football_prop_model/) | Rebuilding a football player forecasting model in deterministic Python and using it to evaluate proposition bets. |
| [Parlay synthetic-risk accounting](sportsbook_parlay_synthetic_risk/) | Measuring sportsbook exposure when multi-leg tickets are represented through their component bets. |

## Systems

| Task | What it tests |
| --- | --- |
| [Market log latency summary](market_log_latency_summary/) | Turning imperfect API logs into grouped request, error, drop, and response-time summaries. |
| [SQLite write-ahead-log recovery](sqlite_wal_odds_recovery/) | Restoring database updates after a crash by validating and replaying intact transaction-log records. |
| [Poker hand-history parser](poker_hand_history_state_machine/) | Converting messy poker hand logs into structured game state while tolerating chat and malformed lines. |
| [Git secret and file purge](git_secret_alpha_purge/) | Removing sensitive data from an entire Git history while preserving legitimate content and repository structure. |
