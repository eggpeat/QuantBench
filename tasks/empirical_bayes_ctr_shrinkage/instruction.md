# Empirical Bayes CTR Shrinkage

Implement the starter module `ctr_shrinkage.py` in the workspace and produce `outputs/ctr_report.json` using `ad_clicks.csv` and `config.json`.

## Methodology

This task tests conjugate beta-binomial shrinkage with an empirical global mean and a configured prior strength $K$ (as a simplified empirical Bayes update task, rather than full prior hyperparameter MLE fitting, following the concepts in David Robinson's *Introduction to Empirical Bayes*, lines 537-538, 543-579, 669-671).

We use a beta-binomial model for empirical Bayes shrinkage of click-through rates (CTR) to update posteriors.
### 1. Fit Global Prior
The global click-through rate is estimated across all ads in the dataset:
$$\text{global\_ctr} = \frac{\sum \text{clicks}}{\sum \text{impressions}}$$

Given a `prior_strength` ($K$), the parameters for the Beta prior are:
$$\alpha_0 = \text{global\_ctr} \times K$$
$$\beta_0 = (1 - \text{global\_ctr}) \times K$$

### 2. Posterior Summary
For each ad, we update the Beta distribution parameters based on its observed `clicks` ($C$) and `impressions` ($I$):
$$\alpha_{\text{post}} = C + \alpha_0$$
$$\beta_{\text{post}} = (I - C) + \beta_0$$

The posterior mean (shrunk CTR) is:
$$\text{posterior\_mean} = \frac{C + \alpha_0}{I + \alpha_0 + \beta_0} = \frac{C + \alpha_0}{I + K}$$

### 3. Constraints & Edge Cases
- If an ad has 0 impressions and 0 clicks, its posterior mean should equal the prior mean (i.e. $\text{global\_ctr}$).
- If an ad has negative clicks, negative impressions, or clicks exceeding impressions, `posterior_summary` must raise a `ValueError`.
- In the helper functions (`fit_global_prior`, `posterior_summary`, and `rank_ads`), all returned floating-point values (such as posterior parameters, global CTR, and posterior mean) must be rounded to exactly 6 decimal places, consistent with the JSON output.
- Only use Python's standard library.
## Inputs
- `ad_clicks.csv`: CSV with columns `ad_id,impressions,clicks`.
- `config.json`: JSON configuration specifying:
  - `prior_strength` (float): The strength of the Beta prior.
  - `top_k` (int): Number of top ranked ads to include in the output ranking.

## Required Output
Write `outputs/ctr_report.json` with the following structure:
```json
{
  "prior": {
    "global_ctr": 0.026727,
    "prior_strength": 100.0,
    "alpha0": 2.67271,
    "beta0": 97.32729
  },
  "ranking": [
    {
      "ad_id": "ad_1",
      "impressions": 10000,
      "clicks": 500,
      "raw_ctr": 0.05,
      "posterior_alpha": 502.67271,
      "posterior_beta": 9597.32729,
      "posterior_mean": 0.04977
    },
    ...
  ]
}
```
All floating-point numbers in the output JSON must be rounded to exactly 6 decimal places.
The `ranking` array must contain the top `top_k` ads ranked by `posterior_mean` in descending order.
