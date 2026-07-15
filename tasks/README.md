# Quant Bench task corpus

This index covers the 40 task directories registered in
[`benchmarks/quant-terminal-v1.toml`](../benchmarks/quant-terminal-v1.toml).
Links are grouped by each task's `metadata.category`; a task README, when
present, describes its observable contract and runtime constraints.

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

- [odds_feed_data_merger](odds_feed_data_merger/)
- [llm_news_batch_scheduler](llm_news_batch_scheduler/)
- [bitemporal_asof_join](bitemporal_asof_join/)
- [incremental_feature_materialization](incremental_feature_materialization/)

## Data science

- [bayesian_mcmc_rhat_diagnostic](bayesian_mcmc_rhat_diagnostic/)
- [kalman_live_market_filter](kalman_live_market_filter/)
- [empirical_bayes_ctr_shrinkage](empirical_bayes_ctr_shrinkage/)
- [empirical_bayes_true_skill](empirical_bayes_true_skill/)
- [data_quality_leakage_client_model](data_quality_leakage_client_model/)
- [kalman_2d_market_tracker](kalman_2d_market_tracker/)
- [heteroscedastic_oof_calibration](heteroscedastic_oof_calibration/)
- [vectorized_fisher_preconditioner](vectorized_fisher_preconditioner/)
- [crps_vectorization_and_scoring](crps_vectorization_and_scoring/)
- [temporal_ep_weighted_likelihood](temporal_ep_weighted_likelihood/)
- [linear_residual_boosting_pipeline](linear_residual_boosting_pipeline/)
- [portfolio_optimizer_constraints](portfolio_optimizer_constraints/)

## Data systems

- [sports_backtest_query_optimize](sports_backtest_query_optimize/)

## Deep quant

- [poker_shove_fold_equity](poker_shove_fold_equity/)
- [quant_var_expected_shortfall](quant_var_expected_shortfall/)
- [poker_side_pot_resolution_engine](poker_side_pot_resolution_engine/)
- [quant_cointegration_pairs_trade](quant_cointegration_pairs_trade/)
- [range_equity_engine](range_equity_engine/)

## Feature selection

- [feature_selection_knockoff_fdr](feature_selection_knockoff_fdr/)
- [incremental_schur_feature_selector](incremental_schur_feature_selector/)
- [stability_selection_resampling](stability_selection_resampling/)

## Machine learning

- [distributional_boosting_boundary_stability](distributional_boosting_boundary_stability/)

## Operations

- [async_odds_scraper_shutdown](async_odds_scraper_shutdown/)

## Probabilistic ML

- [adaptive_conformal_intervals](adaptive_conformal_intervals/)

## Quantitative finance

- [event_driven_backtest_repair](event_driven_backtest_repair/)

## Scientific computing

- [adaptive_ode_event_integration](adaptive_ode_event_integration/)
- [sparse_linear_solver](sparse_linear_solver/)

## Sports modeling

- [sports_hold_vig_removal](sports_hold_vig_removal/)
- [sports_injury_steam_audit](sports_injury_steam_audit/)
- [sports_settlement_ledger_reconciliation](sports_settlement_ledger_reconciliation/)
- [stan_to_python_football_prop_model](stan_to_python_football_prop_model/)
- [sportsbook_parlay_synthetic_risk](sportsbook_parlay_synthetic_risk/)

## Systems

- [market_log_latency_summary](market_log_latency_summary/)
- [sqlite_wal_odds_recovery](sqlite_wal_odds_recovery/)
- [poker_hand_history_state_machine](poker_hand_history_state_machine/)
- [git_secret_alpha_purge](git_secret_alpha_purge/)
