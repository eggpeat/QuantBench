# Quant Bench Report

Generated: `2026-07-15T12:58:28+00:00`

## Leaderboard

| Model | Configuration | Coverage | Comparable | Median attempt pass | Attempt range | Median duration (s) | Provider output tok/s (median) |
|---|---|---:|:---:|---:|---:|---:|---:|
| OpenAI GPT 5.6 Luna | `openai-codex/gpt-5.6-luna · xhigh · OMP` | 200/200 | yes | 92.5% | 82.5%–92.5% | 242.156 | 47.5385 |
| OpenAI GPT 5.6 Sol | `openai-codex/gpt-5.6-sol · max · OMP` | 200/200 | yes | 87.5% | 87.5%–92.5% | 332.12 | 37.385 |
| OpenAI GPT 5.6 Terra | `openai-codex/gpt-5.6-terra · xhigh · OMP` | 200/200 | yes | 85.0% | 85.0%–90.0% | 243.2305 | 47.807 |
| Cognition SWE 1.7 | `devin/swe-1-7 · none · OMP` | 200/200 | yes | 80.0% | 77.5%–80.0% | 549.67 | 98.059 |

## OpenAI GPT 5.6 Luna

Configuration: `{"agents":["gpt-5-6-luna-xhigh"],"backend_provider":"openai-codex","harness":"OMP","model":"openai-codex/gpt-5.6-luna","thinking":"xhigh"}`

- Comparable: **yes**
- Statuses: `{"INFRA_BLOCKED": 0, "PASS": 180, "REJECT": 20, "TIME_LIMIT": 0}`
- Semantic cells: **200/200**
- Per-attempt budgeted pass rates: **1=92.5% (37/40), 2=82.5% (33/40), 3=92.5% (37/40), 4=90.0% (36/40), 5=92.5% (37/40)**
- Attempt distribution: **median 92.5%; range 82.5%–92.5%; spread 10.0 pp** (5 equally weighted attempts; TIME_LIMIT counts as a non-pass)
- Verified duration: median **242.156 s**, p90 **595.665 s**, complete total **66063.09 s**, observed sum **66063.09 s** (coverage 200/200)
- Total tokens: complete total **117074111** (coverage 200/200); observed sum **117074111**
- Cached-input tokens: complete total **103497216** (coverage 200/200); observed sum **103497216**
- Weighted cache read ratio: **0.9076 (coverage 200/200; weighted from complete cached/input totals)**
- Provider-reported/generated-duration throughput median: **47.5385** tok/s (coverage 200; not end-to-end speed)
- Wall output tok/s median: **46.598** (coverage 200)
- Task reliability distribution: `[{"rate":0.0,"semantic_passes":0,"semantic_trials":5,"tasks":1},{"rate":0.4,"semantic_passes":2,"semantic_trials":5,"tasks":1},{"rate":0.6,"semantic_passes":3,"semantic_trials":5,"tasks":4},{"rate":0.8,"semantic_passes":4,"semantic_trials":5,"tasks":4},{"rate":1.0,"semantic_passes":5,"semantic_trials":5,"tasks":30}]`

### Tasks

| Task | Attempts | PASS | REJECT | TIME_LIMIT | INFRA_BLOCKED | Semantic pass |
|---|---:|---:|---:|---:|---:|---:|
| adaptive_conformal_intervals | 5 | 3 | 2 | 0 | 0 | 0.6 |
| adaptive_ode_event_integration | 5 | 4 | 1 | 0 | 0 | 0.8 |
| async_odds_scraper_shutdown | 5 | 5 | 0 | 0 | 0 | 1 |
| bayesian_mcmc_rhat_diagnostic | 5 | 0 | 5 | 0 | 0 | 0 |
| bitemporal_asof_join | 5 | 5 | 0 | 0 | 0 | 1 |
| crps_vectorization_and_scoring | 5 | 5 | 0 | 0 | 0 | 1 |
| data_quality_leakage_client_model | 5 | 5 | 0 | 0 | 0 | 1 |
| distributional_boosting_boundary_stability | 5 | 5 | 0 | 0 | 0 | 1 |
| empirical_bayes_ctr_shrinkage | 5 | 5 | 0 | 0 | 0 | 1 |
| empirical_bayes_true_skill | 5 | 5 | 0 | 0 | 0 | 1 |
| event_driven_backtest_repair | 5 | 3 | 2 | 0 | 0 | 0.6 |
| feature_selection_knockoff_fdr | 5 | 3 | 2 | 0 | 0 | 0.6 |
| git_secret_alpha_purge | 5 | 5 | 0 | 0 | 0 | 1 |
| heteroscedastic_oof_calibration | 5 | 2 | 3 | 0 | 0 | 0.4 |
| incremental_feature_materialization | 5 | 4 | 1 | 0 | 0 | 0.8 |
| incremental_schur_feature_selector | 5 | 5 | 0 | 0 | 0 | 1 |
| kalman_2d_market_tracker | 5 | 5 | 0 | 0 | 0 | 1 |
| kalman_live_market_filter | 5 | 5 | 0 | 0 | 0 | 1 |
| linear_residual_boosting_pipeline | 5 | 4 | 1 | 0 | 0 | 0.8 |
| llm_news_batch_scheduler | 5 | 5 | 0 | 0 | 0 | 1 |
| market_log_latency_summary | 5 | 5 | 0 | 0 | 0 | 1 |
| odds_feed_data_merger | 5 | 5 | 0 | 0 | 0 | 1 |
| poker_hand_history_state_machine | 5 | 4 | 1 | 0 | 0 | 0.8 |
| poker_shove_fold_equity | 5 | 5 | 0 | 0 | 0 | 1 |
| poker_side_pot_resolution_engine | 5 | 3 | 2 | 0 | 0 | 0.6 |
| portfolio_optimizer_constraints | 5 | 5 | 0 | 0 | 0 | 1 |
| quant_cointegration_pairs_trade | 5 | 5 | 0 | 0 | 0 | 1 |
| quant_var_expected_shortfall | 5 | 5 | 0 | 0 | 0 | 1 |
| range_equity_engine | 5 | 5 | 0 | 0 | 0 | 1 |
| sparse_linear_solver | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_backtest_query_optimize | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_hold_vig_removal | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_injury_steam_audit | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_settlement_ledger_reconciliation | 5 | 5 | 0 | 0 | 0 | 1 |
| sportsbook_parlay_synthetic_risk | 5 | 5 | 0 | 0 | 0 | 1 |
| sqlite_wal_odds_recovery | 5 | 5 | 0 | 0 | 0 | 1 |
| stability_selection_resampling | 5 | 5 | 0 | 0 | 0 | 1 |
| stan_to_python_football_prop_model | 5 | 5 | 0 | 0 | 0 | 1 |
| temporal_ep_weighted_likelihood | 5 | 5 | 0 | 0 | 0 | 1 |
| vectorized_fisher_preconditioner | 5 | 5 | 0 | 0 | 0 | 1 |

## OpenAI GPT 5.6 Sol

Configuration: `{"agents":["gpt-5-6-sol"],"backend_provider":"openai-codex","harness":"OMP","model":"openai-codex/gpt-5.6-sol","thinking":"max"}`

- Comparable: **yes**
- Statuses: `{"INFRA_BLOCKED": 0, "PASS": 178, "REJECT": 22, "TIME_LIMIT": 0}`
- Semantic cells: **200/200**
- Per-attempt budgeted pass rates: **1=90.0% (36/40), 2=87.5% (35/40), 3=92.5% (37/40), 4=87.5% (35/40), 5=87.5% (35/40)**
- Attempt distribution: **median 87.5%; range 87.5%–92.5%; spread 5.0 pp** (5 equally weighted attempts; TIME_LIMIT counts as a non-pass)
- Verified duration: median **332.12 s**, p90 **654.819 s**, complete total **72345.626 s**, observed sum **72345.626 s** (coverage 200/200)
- Total tokens: complete total **70472186** (coverage 200/200); observed sum **70472186**
- Cached-input tokens: complete total **60617728** (coverage 200/200); observed sum **60617728**
- Weighted cache read ratio: **0.8943 (coverage 200/200; weighted from complete cached/input totals)**
- Provider-reported/generated-duration throughput median: **37.385** tok/s (coverage 200; not end-to-end speed)
- Wall output tok/s median: **36.6135** (coverage 200)
- Task reliability distribution: `[{"rate":0.0,"semantic_passes":0,"semantic_trials":5,"tasks":2},{"rate":0.4,"semantic_passes":2,"semantic_trials":5,"tasks":1},{"rate":0.6,"semantic_passes":3,"semantic_trials":5,"tasks":2},{"rate":0.8,"semantic_passes":4,"semantic_trials":5,"tasks":5},{"rate":1.0,"semantic_passes":5,"semantic_trials":5,"tasks":30}]`

### Tasks

| Task | Attempts | PASS | REJECT | TIME_LIMIT | INFRA_BLOCKED | Semantic pass |
|---|---:|---:|---:|---:|---:|---:|
| adaptive_conformal_intervals | 5 | 2 | 3 | 0 | 0 | 0.4 |
| adaptive_ode_event_integration | 5 | 3 | 2 | 0 | 0 | 0.6 |
| async_odds_scraper_shutdown | 5 | 5 | 0 | 0 | 0 | 1 |
| bayesian_mcmc_rhat_diagnostic | 5 | 0 | 5 | 0 | 0 | 0 |
| bitemporal_asof_join | 5 | 5 | 0 | 0 | 0 | 1 |
| crps_vectorization_and_scoring | 5 | 4 | 1 | 0 | 0 | 0.8 |
| data_quality_leakage_client_model | 5 | 4 | 1 | 0 | 0 | 0.8 |
| distributional_boosting_boundary_stability | 5 | 5 | 0 | 0 | 0 | 1 |
| empirical_bayes_ctr_shrinkage | 5 | 5 | 0 | 0 | 0 | 1 |
| empirical_bayes_true_skill | 5 | 5 | 0 | 0 | 0 | 1 |
| event_driven_backtest_repair | 5 | 4 | 1 | 0 | 0 | 0.8 |
| feature_selection_knockoff_fdr | 5 | 5 | 0 | 0 | 0 | 1 |
| git_secret_alpha_purge | 5 | 5 | 0 | 0 | 0 | 1 |
| heteroscedastic_oof_calibration | 5 | 0 | 5 | 0 | 0 | 0 |
| incremental_feature_materialization | 5 | 5 | 0 | 0 | 0 | 1 |
| incremental_schur_feature_selector | 5 | 5 | 0 | 0 | 0 | 1 |
| kalman_2d_market_tracker | 5 | 5 | 0 | 0 | 0 | 1 |
| kalman_live_market_filter | 5 | 5 | 0 | 0 | 0 | 1 |
| linear_residual_boosting_pipeline | 5 | 3 | 2 | 0 | 0 | 0.6 |
| llm_news_batch_scheduler | 5 | 5 | 0 | 0 | 0 | 1 |
| market_log_latency_summary | 5 | 5 | 0 | 0 | 0 | 1 |
| odds_feed_data_merger | 5 | 5 | 0 | 0 | 0 | 1 |
| poker_hand_history_state_machine | 5 | 4 | 1 | 0 | 0 | 0.8 |
| poker_shove_fold_equity | 5 | 5 | 0 | 0 | 0 | 1 |
| poker_side_pot_resolution_engine | 5 | 5 | 0 | 0 | 0 | 1 |
| portfolio_optimizer_constraints | 5 | 5 | 0 | 0 | 0 | 1 |
| quant_cointegration_pairs_trade | 5 | 5 | 0 | 0 | 0 | 1 |
| quant_var_expected_shortfall | 5 | 5 | 0 | 0 | 0 | 1 |
| range_equity_engine | 5 | 5 | 0 | 0 | 0 | 1 |
| sparse_linear_solver | 5 | 4 | 1 | 0 | 0 | 0.8 |
| sports_backtest_query_optimize | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_hold_vig_removal | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_injury_steam_audit | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_settlement_ledger_reconciliation | 5 | 5 | 0 | 0 | 0 | 1 |
| sportsbook_parlay_synthetic_risk | 5 | 5 | 0 | 0 | 0 | 1 |
| sqlite_wal_odds_recovery | 5 | 5 | 0 | 0 | 0 | 1 |
| stability_selection_resampling | 5 | 5 | 0 | 0 | 0 | 1 |
| stan_to_python_football_prop_model | 5 | 5 | 0 | 0 | 0 | 1 |
| temporal_ep_weighted_likelihood | 5 | 5 | 0 | 0 | 0 | 1 |
| vectorized_fisher_preconditioner | 5 | 5 | 0 | 0 | 0 | 1 |

## OpenAI GPT 5.6 Terra

Configuration: `{"agents":["gpt-5-6-terra-xhigh"],"backend_provider":"openai-codex","harness":"OMP","model":"openai-codex/gpt-5.6-terra","thinking":"xhigh"}`

- Comparable: **yes**
- Statuses: `{"INFRA_BLOCKED": 0, "PASS": 174, "REJECT": 26, "TIME_LIMIT": 0}`
- Semantic cells: **200/200**
- Per-attempt budgeted pass rates: **1=90.0% (36/40), 2=90.0% (36/40), 3=85.0% (34/40), 4=85.0% (34/40), 5=85.0% (34/40)**
- Attempt distribution: **median 85.0%; range 85.0%–90.0%; spread 5.0 pp** (5 equally weighted attempts; TIME_LIMIT counts as a non-pass)
- Verified duration: median **243.2305 s**, p90 **486.679 s**, complete total **56465.753 s**, observed sum **56465.753 s** (coverage 200/200)
- Total tokens: complete total **68120529** (coverage 200/200); observed sum **68120529**
- Cached-input tokens: complete total **55716096** (coverage 200/200); observed sum **55716096**
- Weighted cache read ratio: **0.8506 (coverage 200/200; weighted from complete cached/input totals)**
- Provider-reported/generated-duration throughput median: **47.807** tok/s (coverage 200; not end-to-end speed)
- Wall output tok/s median: **47.2605** (coverage 200)
- Task reliability distribution: `[{"rate":0.0,"semantic_passes":0,"semantic_trials":5,"tasks":3},{"rate":0.4,"semantic_passes":2,"semantic_trials":5,"tasks":1},{"rate":0.6,"semantic_passes":3,"semantic_trials":5,"tasks":2},{"rate":0.8,"semantic_passes":4,"semantic_trials":5,"tasks":4},{"rate":1.0,"semantic_passes":5,"semantic_trials":5,"tasks":30}]`

### Tasks

| Task | Attempts | PASS | REJECT | TIME_LIMIT | INFRA_BLOCKED | Semantic pass |
|---|---:|---:|---:|---:|---:|---:|
| adaptive_conformal_intervals | 5 | 0 | 5 | 0 | 0 | 0 |
| adaptive_ode_event_integration | 5 | 3 | 2 | 0 | 0 | 0.6 |
| async_odds_scraper_shutdown | 5 | 5 | 0 | 0 | 0 | 1 |
| bayesian_mcmc_rhat_diagnostic | 5 | 0 | 5 | 0 | 0 | 0 |
| bitemporal_asof_join | 5 | 5 | 0 | 0 | 0 | 1 |
| crps_vectorization_and_scoring | 5 | 5 | 0 | 0 | 0 | 1 |
| data_quality_leakage_client_model | 5 | 5 | 0 | 0 | 0 | 1 |
| distributional_boosting_boundary_stability | 5 | 5 | 0 | 0 | 0 | 1 |
| empirical_bayes_ctr_shrinkage | 5 | 5 | 0 | 0 | 0 | 1 |
| empirical_bayes_true_skill | 5 | 5 | 0 | 0 | 0 | 1 |
| event_driven_backtest_repair | 5 | 0 | 5 | 0 | 0 | 0 |
| feature_selection_knockoff_fdr | 5 | 5 | 0 | 0 | 0 | 1 |
| git_secret_alpha_purge | 5 | 5 | 0 | 0 | 0 | 1 |
| heteroscedastic_oof_calibration | 5 | 2 | 3 | 0 | 0 | 0.4 |
| incremental_feature_materialization | 5 | 5 | 0 | 0 | 0 | 1 |
| incremental_schur_feature_selector | 5 | 5 | 0 | 0 | 0 | 1 |
| kalman_2d_market_tracker | 5 | 5 | 0 | 0 | 0 | 1 |
| kalman_live_market_filter | 5 | 5 | 0 | 0 | 0 | 1 |
| linear_residual_boosting_pipeline | 5 | 3 | 2 | 0 | 0 | 0.6 |
| llm_news_batch_scheduler | 5 | 4 | 1 | 0 | 0 | 0.8 |
| market_log_latency_summary | 5 | 5 | 0 | 0 | 0 | 1 |
| odds_feed_data_merger | 5 | 5 | 0 | 0 | 0 | 1 |
| poker_hand_history_state_machine | 5 | 4 | 1 | 0 | 0 | 0.8 |
| poker_shove_fold_equity | 5 | 5 | 0 | 0 | 0 | 1 |
| poker_side_pot_resolution_engine | 5 | 5 | 0 | 0 | 0 | 1 |
| portfolio_optimizer_constraints | 5 | 5 | 0 | 0 | 0 | 1 |
| quant_cointegration_pairs_trade | 5 | 5 | 0 | 0 | 0 | 1 |
| quant_var_expected_shortfall | 5 | 5 | 0 | 0 | 0 | 1 |
| range_equity_engine | 5 | 5 | 0 | 0 | 0 | 1 |
| sparse_linear_solver | 5 | 4 | 1 | 0 | 0 | 0.8 |
| sports_backtest_query_optimize | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_hold_vig_removal | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_injury_steam_audit | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_settlement_ledger_reconciliation | 5 | 5 | 0 | 0 | 0 | 1 |
| sportsbook_parlay_synthetic_risk | 5 | 5 | 0 | 0 | 0 | 1 |
| sqlite_wal_odds_recovery | 5 | 5 | 0 | 0 | 0 | 1 |
| stability_selection_resampling | 5 | 5 | 0 | 0 | 0 | 1 |
| stan_to_python_football_prop_model | 5 | 5 | 0 | 0 | 0 | 1 |
| temporal_ep_weighted_likelihood | 5 | 4 | 1 | 0 | 0 | 0.8 |
| vectorized_fisher_preconditioner | 5 | 5 | 0 | 0 | 0 | 1 |

## Cognition SWE 1.7

Configuration: `{"agents":["swe-1-7-devin"],"backend_provider":"devin","harness":"OMP","model":"devin/swe-1-7","thinking":"none"}`

- Comparable: **yes**
- Statuses: `{"INFRA_BLOCKED": 0, "PASS": 158, "REJECT": 41, "TIME_LIMIT": 1}`
- Semantic cells: **199/200**
- Per-attempt budgeted pass rates: **1=80.0% (32/40), 2=77.5% (31/40), 3=77.5% (31/40), 4=80.0% (32/40), 5=80.0% (32/40)**
- Attempt distribution: **median 80.0%; range 77.5%–80.0%; spread 2.5 pp** (5 equally weighted attempts; TIME_LIMIT counts as a non-pass)
- Verified duration: median **549.67 s**, p90 **1779.664 s**, complete total **159067.417 s**, observed sum **159067.417 s** (coverage 199/199)
- Total tokens: complete total **779440018** (coverage 199/199); observed sum **779440018**
- Cached-input tokens: complete total **745277848** (coverage 199/199); observed sum **745277848**
- Weighted cache read ratio: **0.9745 (coverage 199/199; weighted from complete cached/input totals)**
- Provider-reported/generated-duration throughput median: **98.059** tok/s (coverage 199; not end-to-end speed)
- Wall output tok/s median: **92.97** (coverage 199)
- Task reliability distribution: `[{"rate":0.0,"semantic_passes":0,"semantic_trials":4,"tasks":1},{"rate":0.0,"semantic_passes":0,"semantic_trials":5,"tasks":5},{"rate":0.4,"semantic_passes":2,"semantic_trials":5,"tasks":1},{"rate":0.6,"semantic_passes":3,"semantic_trials":5,"tasks":2},{"rate":0.8,"semantic_passes":4,"semantic_trials":5,"tasks":5},{"rate":1.0,"semantic_passes":5,"semantic_trials":5,"tasks":26}]`

### Tasks

| Task | Attempts | PASS | REJECT | TIME_LIMIT | INFRA_BLOCKED | Semantic pass |
|---|---:|---:|---:|---:|---:|---:|
| adaptive_conformal_intervals | 5 | 3 | 2 | 0 | 0 | 0.6 |
| adaptive_ode_event_integration | 5 | 4 | 1 | 0 | 0 | 0.8 |
| async_odds_scraper_shutdown | 5 | 5 | 0 | 0 | 0 | 1 |
| bayesian_mcmc_rhat_diagnostic | 5 | 0 | 5 | 0 | 0 | 0 |
| bitemporal_asof_join | 5 | 5 | 0 | 0 | 0 | 1 |
| crps_vectorization_and_scoring | 5 | 5 | 0 | 0 | 0 | 1 |
| data_quality_leakage_client_model | 5 | 5 | 0 | 0 | 0 | 1 |
| distributional_boosting_boundary_stability | 5 | 5 | 0 | 0 | 0 | 1 |
| empirical_bayes_ctr_shrinkage | 5 | 5 | 0 | 0 | 0 | 1 |
| empirical_bayes_true_skill | 5 | 5 | 0 | 0 | 0 | 1 |
| event_driven_backtest_repair | 5 | 0 | 5 | 0 | 0 | 0 |
| feature_selection_knockoff_fdr | 5 | 5 | 0 | 0 | 0 | 1 |
| git_secret_alpha_purge | 5 | 5 | 0 | 0 | 0 | 1 |
| heteroscedastic_oof_calibration | 5 | 4 | 1 | 0 | 0 | 0.8 |
| incremental_feature_materialization | 5 | 0 | 5 | 0 | 0 | 0 |
| incremental_schur_feature_selector | 5 | 5 | 0 | 0 | 0 | 1 |
| kalman_2d_market_tracker | 5 | 5 | 0 | 0 | 0 | 1 |
| kalman_live_market_filter | 5 | 5 | 0 | 0 | 0 | 1 |
| linear_residual_boosting_pipeline | 5 | 0 | 4 | 1 | 0 | 0 |
| llm_news_batch_scheduler | 5 | 4 | 1 | 0 | 0 | 0.8 |
| market_log_latency_summary | 5 | 5 | 0 | 0 | 0 | 1 |
| odds_feed_data_merger | 5 | 4 | 1 | 0 | 0 | 0.8 |
| poker_hand_history_state_machine | 5 | 0 | 5 | 0 | 0 | 0 |
| poker_shove_fold_equity | 5 | 5 | 0 | 0 | 0 | 1 |
| poker_side_pot_resolution_engine | 5 | 5 | 0 | 0 | 0 | 1 |
| portfolio_optimizer_constraints | 5 | 5 | 0 | 0 | 0 | 1 |
| quant_cointegration_pairs_trade | 5 | 5 | 0 | 0 | 0 | 1 |
| quant_var_expected_shortfall | 5 | 5 | 0 | 0 | 0 | 1 |
| range_equity_engine | 5 | 3 | 2 | 0 | 0 | 0.6 |
| sparse_linear_solver | 5 | 2 | 3 | 0 | 0 | 0.4 |
| sports_backtest_query_optimize | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_hold_vig_removal | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_injury_steam_audit | 5 | 5 | 0 | 0 | 0 | 1 |
| sports_settlement_ledger_reconciliation | 5 | 5 | 0 | 0 | 0 | 1 |
| sportsbook_parlay_synthetic_risk | 5 | 5 | 0 | 0 | 0 | 1 |
| sqlite_wal_odds_recovery | 5 | 5 | 0 | 0 | 0 | 1 |
| stability_selection_resampling | 5 | 0 | 5 | 0 | 0 | 0 |
| stan_to_python_football_prop_model | 5 | 5 | 0 | 0 | 0 | 1 |
| temporal_ep_weighted_likelihood | 5 | 4 | 1 | 0 | 0 | 0.8 |
| vectorized_fisher_preconditioner | 5 | 5 | 0 | 0 | 0 | 1 |
