"""Empirical Bayes Beta-Binomial CTR Shrinkage helpers.

Implement these functions to compute global prior, posterior summaries, and ad rankings.
"""


def fit_global_prior(rows, prior_strength):
    """Estimate the global prior parameters from all ad clicks and impressions.

    Args:
        rows: List of dicts, each with 'ad_id', 'impressions', and 'clicks'.
        prior_strength: Float, prior strength (K).

    Returns:
        A tuple of (global_ctr, alpha0, beta0).
    """
    raise NotImplementedError("fit_global_prior must be implemented")


def posterior_summary(row, alpha0, beta0):
    """Compute the posterior statistics for a single ad.

    Args:
        row: Dict with 'ad_id', 'impressions', and 'clicks'.
        alpha0: Float, prior alpha parameter.
        beta0: Float, prior beta parameter.

    Returns:
        A dict with posterior parameters and posterior mean.
    """
    raise NotImplementedError("posterior_summary must be implemented")


def rank_ads(rows, prior_strength):
    """Compute posterior summaries for all ads and sort them by posterior mean in descending order.

    Args:
        rows: List of dicts, each with 'ad_id', 'impressions', and 'clicks'.
        prior_strength: Float, prior strength (K).

    Returns:
        List of dicts representing the sorted posterior summaries.
    """
    raise NotImplementedError("rank_ads must be implemented")
