"""Empirical Bayes Beta-Binomial Player Skill Estimation."""


def fit_beta_prior(rows):
    """Estimate the global prior parameters alpha0 and beta0 from the rows using the Method of Moments.

    To avoid noisy, low-volume players distorting the prior estimation,
    this function should filter the data to players with at least 10 attempts (attempts >= 10).
    If fewer than 2 players remain, fall back to players with attempts > 0.
    If still fewer than 2 players remain, return (1.0, 1.0).

    Args:
        rows (list of dict): List of player dictionaries with keys 'successes' and 'attempts'.

    Returns:
        tuple of (float, float): The fitted (alpha0, beta0) parameters.
    """
    # TODO: Implement Method of Moments fitting with fallbacks
    raise NotImplementedError("Implement fit_beta_prior")


def posterior_summary(row, alpha0, beta0):
    """Compute posterior statistics for a single player.

    This includes calculating raw rates, posterior parameters, posterior means,
    and the 95% credible interval using the Normal approximation to the Beta distribution.

    Args:
        row (dict): A player dictionary with keys 'player_id', 'successes', and 'attempts'.
        alpha0 (float): Prior alpha parameter.
        beta0 (float): Prior beta parameter.

    Returns:
        dict: Summary containing player info, raw statistics, posterior alpha/beta,
              posterior mean, and credible interval bounds. All floating-point fields
              must be rounded to exactly 6 decimal places.
    """
    # TODO: Implement posterior update and credible interval calculation
    raise NotImplementedError("Implement posterior_summary")


def rank_players(rows):
    """Fit the prior from the raw rows, compute posterior summaries, and rank all players.

    Sorts the players in descending order of posterior_mean, assigning a 1-based rank.

    Args:
        rows (list of dict): List of player dictionaries.

    Returns:
        list of dict: List of ranked player dictionaries.
    """
    # TODO: Implement ranking pipeline
    raise NotImplementedError("Implement rank_players")
