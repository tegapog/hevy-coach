-- ============================================================================
--  $8,250 Fitness Coach schema + Hevy-sync additions
--  Run this ONCE in the Supabase SQL Editor (Dashboard -> SQL Editor -> New query).
--  Faithful to the guide's 10 tables. Lines marked [HEVY] are additive columns/
--  tables the Hevy->DB sync needs; the guide's three coaches ignore them.
-- ============================================================================

-- Your local timezone so "a day" means your midnight, not UTC.
-- (Supabase: this sets it for this database's default.)
ALTER DATABASE postgres SET timezone TO 'Europe/London';

-- ---------- the guide's ten tables ----------

CREATE TABLE IF NOT EXISTS messages (
  id bigserial PRIMARY KEY,
  source text,
  chat_id bigint,
  kind text,
  raw_text text,
  transcript text,
  status text NOT NULL DEFAULT 'pending',
  parsed_data jsonb,
  received_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS foods (
  id bigserial PRIMARY KEY,
  name text NOT NULL,
  brand text NOT NULL DEFAULT '',
  serving_size numeric,
  serving_unit text,
  calories numeric,
  protein_g numeric,
  carbs_g numeric,
  fat_g numeric,
  source_url text,
  UNIQUE (name, brand, serving_size, serving_unit)
);

CREATE TABLE IF NOT EXISTS food_log (
  id bigserial PRIMARY KEY,
  food_id bigint REFERENCES foods(id),
  quantity numeric,
  calories numeric,
  protein_g numeric,
  carbs_g numeric,
  fat_g numeric,
  consumed_at timestamptz,
  message_id bigint REFERENCES messages(id)
);

CREATE TABLE IF NOT EXISTS exercises (
  id bigserial PRIMARY KEY,
  name text NOT NULL UNIQUE,
  pattern text,
  primary_muscle text,
  equipment text,
  is_compound boolean,
  hevy_template_id text UNIQUE          -- [HEVY] maps a Hevy exercise template to this row
);

CREATE TABLE IF NOT EXISTS workouts (
  id bigserial PRIMARY KEY,
  session_date date,
  split text,
  duration_min int,
  bodyweight_lbs numeric,
  message_id bigint REFERENCES messages(id),
  hevy_id text UNIQUE                    -- [HEVY] Hevy workout uuid, for idempotent upsert/delete
);

CREATE TABLE IF NOT EXISTS workout_sets (
  id bigserial PRIMARY KEY,
  workout_id bigint REFERENCES workouts(id) ON DELETE CASCADE,  -- [HEVY] cascade so a deleted workout takes its sets
  exercise_id bigint REFERENCES exercises(id),
  set_index int,
  weight_lbs numeric,
  reps int,
  rir int,
  -- 30.0 (not 30) so integer division never silently returns your bench as your 1RM:
  e1rm numeric GENERATED ALWAYS AS (weight_lbs * (1 + reps / 30.0)) STORED
);

CREATE TABLE IF NOT EXISTS supplements (
  id bigserial PRIMARY KEY,
  name text NOT NULL,
  brand text NOT NULL DEFAULT '',
  form text,
  serving_size numeric,
  serving_unit text,
  key_ingredients jsonb,
  cost_per_serving numeric
);

CREATE TABLE IF NOT EXISTS supplement_log (
  id bigserial PRIMARY KEY,
  supplement_id bigint REFERENCES supplements(id),
  quantity numeric,
  taken_at timestamptz,
  message_id bigint REFERENCES messages(id)
);

CREATE TABLE IF NOT EXISTS body_metrics (
  id bigserial PRIMARY KEY,
  weight_lbs numeric,
  bodyfat_pct numeric,
  waist_in numeric,
  resting_hr int,
  recorded_at timestamptz,
  message_id bigint REFERENCES messages(id),
  hevy_measurement_id bigint UNIQUE     -- [HEVY] Hevy body_measurement id, for idempotent upsert
);

CREATE TABLE IF NOT EXISTS daily_plan (
  id bigserial PRIMARY KEY,
  time_local time,
  item_type text,
  label text,
  target_ref text,
  target_value numeric,
  target_unit text,
  active boolean NOT NULL DEFAULT true
);

-- ---------- [HEVY] tiny key/value table to remember the last sync point ----------
CREATE TABLE IF NOT EXISTS sync_state (
  key text PRIMARY KEY,
  value text
);

-- ---------- your goal rows (from what your coach already knows; edit if wrong) ----------
-- weight_rate is in lb/week: cutting ~0.45 kg/wk = about -1.0 lb/wk.
INSERT INTO daily_plan (item_type, label, target_value, target_unit)
VALUES ('goal', 'weight_rate', -1.0, 'lb_per_week')
ON CONFLICT DO NOTHING;
INSERT INTO daily_plan (item_type, label, target_value, target_unit)
VALUES ('goal', 'calories', 2265, 'kcal')
ON CONFLICT DO NOTHING;

-- ---------- v_adherence: last 30 days, one row per day even if nothing logged ----------
CREATE OR REPLACE VIEW v_adherence AS
WITH days AS (
  SELECT generate_series(
           (current_date - INTERVAL '29 days')::date,
           current_date,
           INTERVAL '1 day')::date AS day
),
planned AS (
  SELECT count(*) AS n
  FROM daily_plan
  WHERE active AND item_type <> 'goal'
)
SELECT
  d.day,
  (SELECT n FROM planned) AS planned,
  (
    SELECT count(*) FROM daily_plan dp
    WHERE dp.active AND dp.item_type <> 'goal'
      AND (
        EXISTS (SELECT 1 FROM food_log fl       WHERE fl.consumed_at::date = d.day)
     OR EXISTS (SELECT 1 FROM supplement_log sl WHERE sl.taken_at::date    = d.day)
     OR EXISTS (SELECT 1 FROM workouts w        WHERE w.session_date       = d.day)
      )
  ) AS hit,
  (SELECT n FROM planned)
    - (
    SELECT count(*) FROM daily_plan dp
    WHERE dp.active AND dp.item_type <> 'goal'
      AND (
        EXISTS (SELECT 1 FROM food_log fl       WHERE fl.consumed_at::date = d.day)
     OR EXISTS (SELECT 1 FROM supplement_log sl WHERE sl.taken_at::date    = d.day)
     OR EXISTS (SELECT 1 FROM workouts w        WHERE w.session_date       = d.day)
      )
  ) AS missed,
  round(100.0 * (
    SELECT count(*) FROM daily_plan dp
    WHERE dp.active AND dp.item_type <> 'goal'
      AND (
        EXISTS (SELECT 1 FROM food_log fl       WHERE fl.consumed_at::date = d.day)
     OR EXISTS (SELECT 1 FROM supplement_log sl WHERE sl.taken_at::date    = d.day)
     OR EXISTS (SELECT 1 FROM workouts w        WHERE w.session_date       = d.day)
      )
  ) / nullif((SELECT n FROM planned), 0)) AS pct
FROM days d
ORDER BY d.day;
