def audit_game(game: dict) -> dict:
    """
    Audits a single game and decides if injury/line movement edge is priced in,
    represents a stale market betting opportunity, or is a fake steam move.

    Args:
        game (dict): The game data dictionary.

    Returns:
        dict: The audit result with keys: 'event_id', 'edge_points', 'classification'.
    """
    raise NotImplementedError("audit_game not implemented")


def audit_slate(games: list) -> list:
    """
    Audits a list of game events and returns a list of audit results.

    Args:
        games (list): A list of game dictionaries.

    Returns:
        list: A list of result dictionaries.
    """
    raise NotImplementedError("audit_slate not implemented")
