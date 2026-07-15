SELECT
    m.sport,
    o.bookmaker,
    COUNT(*) as total_bets,
    ROUND(AVG(o.odds_value), 4) as avg_odds,
    ROUND(AVG(p.pred_value), 4) as avg_pred
FROM matches m
JOIN odds o ON o.game_id = m.game_id
JOIN predictions p ON p.game_id = m.game_id
WHERE m.sport IN ('soccer', 'basketball')
  AND m.kickoff_time BETWEEN '2024-07-01 00:00:00' AND '2024-09-30 23:59:59'
  AND o.recorded_at = (
      SELECT MAX(o2.recorded_at)
      FROM odds o2
      WHERE o2.game_id = m.game_id
        AND o2.bookmaker = o.bookmaker
        AND o2.recorded_at <= m.kickoff_time
  )
  AND p.generated_at = (
      SELECT MAX(p2.generated_at)
      FROM predictions p2
      WHERE p2.game_id = m.game_id
        AND p2.model_name = 'AlphaModel'
        AND p2.generated_at <= o.recorded_at
  )
  AND (p.pred_value * o.odds_value - 1.0) > 0.1
GROUP BY m.sport, o.bookmaker
ORDER BY total_bets DESC, m.sport, o.bookmaker;
