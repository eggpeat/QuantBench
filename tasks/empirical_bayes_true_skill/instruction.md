# Empirical Bayes True Skill Estimation

Implement the starter module `eb_skill.py` in the workspace and produce `outputs/skill_rankings.json` using `players.csv`.

## Methodology

This task implements conjugate Beta-binomial empirical Bayes shrinkage to estimate player skills (success rates) from noisy binomial observations. We estimate the global Beta prior parameters from the dataset using the Method of Moments and update each player's posterior distribution accordingly.

### 1. Fit Global Prior
To fit the Beta prior $\text{Beta}(\alpha_0, \beta_0)$ to the observed success rates, we use the Method of Moments.
We filter the input rows to players with at least 10 attempts (i.e., `attempts >= 10`). If fewer than 2 players satisfy this criterion, we fall back to all players with `attempts > 0`. If still fewer than 2 players are available, we return the default parameters $\alpha_0 = 1.0, \beta_0 = 1.0$.

For the selected subset of players, we calculate the raw success rates:
$$p_i = \frac{\text{successes}_i}{\text{attempts}_i}$$

We then calculate the sample mean ($\mu$) and sample variance ($v$) of these rates:
$$\mu = \frac{1}{N} \sum_{i=1}^N p_i$$
$$v = \frac{1}{N - 1} \sum_{i=1}^N (p_i - \mu)^2$$

- If $\mu \le 0$ or $\mu \ge 1$, we return $\alpha_0 = 1.0, \beta_0 = 1.0$.
- If $v \le 0$ or $v \ge \mu(1 - \mu)$, we fall back to a default prior strength $K = 10.0$, returning:
  $$\alpha_0 = \mu \times K$$
  $$\beta_0 = (1 - \mu) \times K$$
- Otherwise, the Method of Moments estimates are:
  $$\alpha_0 = \mu \left( \frac{\mu(1 - \mu)}{v} - 1 \right)$$
  $$\beta_0 = (1 - \mu) \left( \frac{\mu(1 - \mu)}{v} - 1 \right)$$

### 2. Posterior Summary and Credible Interval
For each player, we update the Beta distribution parameters based on their successes ($S$) and attempts ($A$):
$$\alpha_{\text{post}} = S + \alpha_0$$
$$\beta_{\text{post}} = (A - S) + \beta_0$$

The posterior mean is:
$$\text{posterior\_mean} = \frac{\alpha_{\text{post}}}{\alpha_{\text{post}} + \beta_{\text{post}}}$$

The posterior variance of the Beta distribution is:
$$\sigma^2 = \frac{\alpha_{\text{post}} \beta_{\text{post}}}{(\alpha_{\text{post}} + \beta_{\text{post}})^2 (\alpha_{\text{post}} + \beta_{\text{post}} + 1)}$$

Using the Normal approximation to the Beta distribution, the 95% credible interval is:
$$\text{credible\_interval\_low} = \max\left(0.0, \text{posterior\_mean} - 1.96 \sigma\right)$$
$$\text{credible\_interval\_high} = \min\left(1.0, \text{posterior\_mean} + 1.96 \sigma\right)$$

### 3. Constraints & Edge Cases
- If a player has 0 attempts and 0 successes, their `raw_rate` should be 0.0, and their posterior mean should equal the prior mean (i.e. $\frac{\alpha_0}{\alpha_0 + \beta_0}$).
- If successes or attempts are negative, or if successes exceed attempts, the functions must raise a `ValueError`.
- Only use Python's standard library.

## Inputs
- `players.csv`: A CSV file containing:
  - `player_id`: unique identifier for the player (string)
  - `successes`: count of successes (integer)
  - `attempts`: count of attempts (integer)

## Required API

Your module `eb_skill.py` must implement the following functions:
- `fit_beta_prior(rows)`: Takes a list of dictionary rows (with keys `"successes"` and `"attempts"`) and returns `(alpha0, beta0)`.
- `posterior_summary(row, alpha0, beta0)`: Takes a single player row (dict) and the prior parameters, and returns a dictionary with keys:
  - `"player_id"` (string)
  - `"successes"` (int)
  - `"attempts"` (int)
  - `"raw_rate"` (float)
  - `"posterior_alpha"` (float)
  - `"posterior_beta"` (float)
  - `"posterior_mean"` (float)
  - `"credible_interval_low"` (float)
  - `"credible_interval_high"` (float)
- `rank_players(rows)`: Computes the prior parameters from all rows, generates posterior summaries for all players, sorts them in descending order of `posterior_mean`, assigns a 1-based rank (`"rank"`), and returns the ranked list.

## Required Output
Write `outputs/skill_rankings.json` with the following structure:
```json
{
  "prior": {
    "alpha": 3.099177,
    "beta": 5.578519,
    "mean": 0.357143
  },
  "rankings": [
    {
      "rank": 1,
      "player_id": "player_10",
      "successes": 700,
      "attempts": 1000,
      "raw_rate": 0.700000,
      "posterior_alpha": 703.099177,
      "posterior_beta": 305.578519,
      "posterior_mean": 0.697050,
      "credible_interval_low": 0.668705,
      "credible_interval_high": 0.725396
    },
    ...
  ]
}
```
All floating-point numbers in the output JSON must be rounded to exactly 6 decimal places.
