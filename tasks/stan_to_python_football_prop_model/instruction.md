Translate a Bayesian Poisson Generalized Linear Model (GLM) for football player passing touchdowns from R/Stan into a deterministic, standard-library-only Python implementation.

You are provided with a historical game dataset containing quarterback stats (`data/passing_tds.csv`), an upcoming prop slate (`data/prop_bets.csv`), and a reference R/Stan model definition (`model_rstan.R`).

Starter files are provided in the workspace:
- `football_prop_model.py`: Contains stubs for your implementation.
- `run_model.py`: A wrapper script that imports and runs your model analysis.

### Objectives

1. Complete the implementation of `football_prop_model.py` exposing the following API:
   - `fit_poisson_model(rows)`
   - `predict_lambda(coeffs, row)`
   - `poisson_tail(lambda_value, threshold)`
   - `analyze_props(data_csv, props_csv)`

2. Implement a deterministic Poisson GLM solver using **Iteratively Reweighted Least Squares (IRLS)**.
   - The model has a log link: $\log(\lambda) = X \beta$.
   - Predictors are ordered as: `[intercept, passer_rating, opp_defense_rating, is_home]`.
   - Intercept is always `1.0`.
   - Initialize coefficients to `0.0` (i.e. $\beta = [0.0, 0.0, 0.0, 0.0]$).
   - In each IRLS iteration:
     1. Calculate $\lambda_i = \exp(X_i^T \beta)$ for all observations $i$. Clip the linear predictor $X_i^T \beta$ to the range $[-20.0, 20.0]$ before exponentiation to prevent overflow/underflow.
     2. Form the $4 \times 4$ Fisher information matrix $I = X^T W X$, where $W$ is a diagonal matrix of $\lambda_i$. Specifically, $I_{j,k} = \sum_{i=1}^N X_{i,j} X_{i,k} \lambda_i$.
     3. Form the $4 \times 1$ gradient vector $g = X^T (y - \lambda)$. Specifically, $g_j = \sum_{i=1}^N X_{i,j} (y_i - \lambda_i)$.
     4. Solve the linear system $I \cdot d = g$ for the step update vector $d$ using Gaussian elimination with partial pivoting.
     5. Update $\beta \leftarrow \beta + d$.
     6. Check convergence: Stop iterating if the sum of absolute updates $\sum_{j=0}^3 |d_j| < 10^{-9}$.
   - Return a dictionary mapping the feature names to their fitted values:
     `{"intercept": beta_0, "passer_rating": beta_1, "opp_defense_rating": beta_2, "is_home": beta_3}`.

3. Calculate the Poisson tail probability for any line/threshold:
   - $P(Y > \text{threshold}) = 1 - \sum_{k=0}^{\lfloor\text{threshold}\rfloor} \frac{\lambda^k e^{-\lambda}}{k!}$.
   - You must compute this using basic arithmetic without external library calls (e.g. `scipy.stats`).

4. Convert model probabilities to fair American odds:
   - For probability $p$:
     - If $p \ge 0.5$: American odds $= \text{round}\left(-100 \times \frac{p}{1 - p}\right)$
     - If $p < 0.5$: American odds $= \text{round}\left(100 \times \frac{1 - p}{p}\right)$

5. Convert market odds (American odds) to implied break-even probability:
   - If market odds $O > 0$: implied probability $= 100 / (O + 100)$
   - If market odds $O < 0$: implied probability $= |O| / (|O| + 100)$

6. Generate opinions for each prop option:
   - Compare the model probability of the Over ($p_{\text{over}}$) with the market break-even probability for the Over ($p_{\text{be, over}}$):
     - $\text{edge}_{\text{over}} = p_{\text{over}} - p_{\text{be, over}}$
   - Compare the model probability of the Under ($p_{\text{under}} = 1 - p_{\text{over}}$) with the market break-even probability for the Under ($p_{\text{be, under}}$):
     - $\text{edge}_{\text{under}} = p_{\text{under}} - p_{\text{be, under}}$
   - Opinion is:
     - `"OVER"` if $\text{edge}_{\text{over}} > 0$.
     - `"UNDER"` if $\text{edge}_{\text{under}} > 0$.
     - `"NO_BET"` if both edges are less than or equal to zero.

7. Write results to `outputs/prop_opinions.json` with the following schema:
   ```json
   {
     "coefficients": {
       "intercept": -1.494668,
       "passer_rating": 0.754303,
       "opp_defense_rating": 0.617869,
       "is_home": 0.311304
     },
     "prop_opinions": [
       {
         "prop_id": "prop_1",
         "passer": "Patrick Mahomes",
         "opponent": "Raiders",
         "line": 1.5,
         "lambda": 2.749247,
         "model_prob_over": 0.760138,
         "model_prob_under": 0.239862,
         "market_be_over": 0.565217,
         "market_be_under": 0.47619,
         "fair_odds_over": -317,
         "fair_odds_under": 317,
         "edge_over": 0.194921,
         "edge_under": -0.236329,
         "opinion": "OVER"
       }
       // ...
     ]
   }
   ```

### Rounding Rules

- Coefficients, lambdas, probabilities, and edges in the output JSON must be rounded to exactly 6 decimal places.
- Fair odds must be rounded to the nearest integer.
