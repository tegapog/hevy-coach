-- One-off migration: lbs -> kg. Run once, then reset the sync watermark and
-- re-run scripts/hevy_sync.py so every row is rewritten with kg values.
-- (Column values are left as-is here; the re-sync overwrites them.)

ALTER TABLE workout_sets DROP COLUMN IF EXISTS e1rm;
ALTER TABLE workout_sets RENAME COLUMN weight_lbs TO weight_kg;
ALTER TABLE workout_sets
  ADD COLUMN e1rm numeric GENERATED ALWAYS AS (weight_kg * (1 + reps / 30.0)) STORED;

ALTER TABLE workouts     RENAME COLUMN bodyweight_lbs TO bodyweight_kg;
ALTER TABLE body_metrics RENAME COLUMN weight_lbs     TO weight_kg;

UPDATE daily_plan SET target_value = -0.45, target_unit = 'kg_per_week'
WHERE item_type = 'goal' AND label = 'weight_rate';

-- force a full re-backfill on the next sync run
DELETE FROM sync_state WHERE key = 'last_workout_event_at';
