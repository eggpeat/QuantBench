# model_rstan.R
# Reference implementation of a Poisson Regression model in RStan
# Based on Football Analytics with Python & R (Chapter 6: Using Data Science for Sports Betting)

library(rstan)
library(dplyr)

# Load game data
games_data <- read.csv("data/passing_tds.csv")

# Prepare design matrix and target variable
# Predictors: intercept, passer_rating, opp_defense_rating, is_home
X <- model.matrix(~ passer_rating + opp_defense_rating + is_home, data = games_data)
y <- games_data$passing_tds

# Stan code definition for Poisson GLM with log link
stan_model_code <- "
data {
  int<lower=0> N;          // Number of observations (games)
  int<lower=0> K;          // Number of predictors (coefficients)
  matrix[N, K] X;          // Design matrix
  array[N] int<lower=0> y; // Response counts (passing TDs)
}
parameters {
  vector[K] beta;          // Coefficients (intercept, rating, def, home)
}
model {
  // Weakly informative prior
  beta ~ normal(0, 10);

  // Poisson regression likelihood with log link
  y ~ poisson_log(X * beta);
}
"

# Compile and fit the model
stan_data <- list(
  N = nrow(games_data),
  K = ncol(X),
  X = X,
  y = y
)

fit <- stan(
  model_code = stan_model_code,
  data = stan_data,
  chains = 4,
  iter = 2000,
  warmup = 1000,
  seed = 42
)

# Extract posterior mean of coefficients
beta_hat <- colMeans(extract(fit)$beta)
print("Fitted Coefficients:")
print(beta_hat)
