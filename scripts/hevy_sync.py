"""
Hevy -> Postgres sync for the $8,250 Fitness Coach build.

Polls GET /workouts/events?since=<last sync> and upserts changed workouts into
the guide's Postgres schema. Replaces the Telegram ingest+parse (STEP 2/3) for
WORKOUTS only. Food/supplements still come from Telegram.

Mappings (Hevy -> guide's lbs-based schema):
  weight_kg -> weight_lbs   (kg / 0.45359237)   so e1RM + coach "+5 lbs" logic stay valid
  rpe (0-10) -> rir         (rir = 10 - rpe, floored at 0; null if no RPE)
  warmup sets               -> skipped (don't pollute e1RM slopes)
  exercise                  -> one of 8 patterns the training coach groups by

Env:
  HEVY_API_KEY   Hevy Pro API key (GitHub secret; falls back to ../.env locally)
  DATABASE_URL   Postgres/Supabase connection string (GitHub secret)

Idempotent: safe to run every 15 min. First run (no saved sync point) backfills
your entire history.
"""
import os
import re
import sys
import json
import time
import pathlib
import datetime as dt
import urllib.request
import urllib.error

import psycopg

BASE = "https://api.hevyapp.com/v1"
LB_PER_KG = 0.45359237
ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- credentials
def _hevy_key():
    k = os.environ.get("HEVY_API_KEY")
    if k:
        return k.strip()
    envf = ROOT / ".env"          # local convenience only; not used in CI
    if envf.exists():
        m = re.search(r"HEVY_API_KEY=(.*)", envf.read_text(encoding="utf-8-sig"))
        if m:
            return m.group(1).strip()
    sys.exit("HEVY_API_KEY not set")


def _db_url():
    u = os.environ.get("DATABASE_URL")
    if u:
        return u.strip()
    envf = ROOT / ".env"          # local convenience only; not used in CI
    if envf.exists():
        m = re.search(r"DATABASE_URL=(.*)", envf.read_text(encoding="utf-8-sig"))
        if m and m.group(1).strip():
            return m.group(1).strip()
    sys.exit("DATABASE_URL not set")


HEVY_KEY = _hevy_key()


# ---------------------------------------------------------------- hevy api
def api(path, params=None, retries=4):
    url = BASE + path
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    req = urllib.request.Request(url, headers={"api-key": HEVY_KEY, "Accept": "application/json"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise


# ---------------------------------------------------------------- conversions
def kg_to_lb(kg):
    return None if kg is None else round(kg / LB_PER_KG, 4)


def rpe_to_rir(rpe):
    if rpe is None:
        return None
    return max(0, int(round(10 - rpe)))


PATTERN_COMPOUND = {"horizontal_push", "vertical_push", "horizontal_pull",
                    "vertical_pull", "hinge", "squat", "carry"}


def pattern_for(title, muscle):
    """Map a Hevy exercise to one of the guide's 8 movement patterns."""
    t = (title or "").lower()
    m = (muscle or "").lower()
    if any(w in t for w in ("carry", "farmer", "suitcase", "yoke")):
        return "carry"
    if any(w in t for w in ("squat", "leg press", "lunge", "split squat", "step up", "hack")):
        return "squat"
    if any(w in t for w in ("deadlift", "romanian", "rdl", "hip thrust", "good morning",
                            "back extension", "hyperextension", "kettlebell swing")):
        return "hinge"
    if any(w in t for w in ("pulldown", "pull up", "pull-up", "pullup", "chin up", "chin-up")):
        return "vertical_pull"
    if any(w in t for w in ("row", "face pull")):
        return "horizontal_pull"
    if any(w in t for w in ("overhead press", "shoulder press", "ohp", "military",
                            "pike", "handstand", "arnold")):
        return "vertical_push"
    if any(w in t for w in ("bench", "chest press", "dip", "push up", "push-up", "pushup")):
        return "horizontal_push"
    # muscle-group fallbacks for compound-ish lifts
    if "chest" in m:
        return "horizontal_push"
    if m in ("lats", "upper_back"):
        return "horizontal_pull"
    # everything else (curls, raises, extensions, flyes, calves, crunches, holds)
    return "isolation"


# ---------------------------------------------------------------- db helpers
def get_state(cur, key):
    cur.execute("SELECT value FROM sync_state WHERE key=%s", (key,))
    row = cur.fetchone()
    return row[0] if row else None


def set_state(cur, key, value):
    cur.execute("""INSERT INTO sync_state(key, value) VALUES (%s, %s)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                (key, value))


_template_cache = {}


def ensure_exercise(cur, template_id, title):
    """Return local exercises.id for a Hevy template, inserting + classifying on first sight."""
    cur.execute("SELECT id FROM exercises WHERE hevy_template_id=%s", (template_id,))
    row = cur.fetchone()
    if row:
        return row[0]

    # fetch template detail once for muscle/equipment
    muscle = equipment = None
    if template_id not in _template_cache:
        try:
            resp = api(f"/exercise_templates/{template_id}")
            tpl = resp.get("exercise_template", resp) if isinstance(resp, dict) else {}
            _template_cache[template_id] = tpl
        except Exception:
            _template_cache[template_id] = {}
    tpl = _template_cache.get(template_id, {})
    muscle = tpl.get("primary_muscle_group")
    equipment = tpl.get("equipment")

    name = (title or tpl.get("title") or "exercise").strip().lower()
    pattern = pattern_for(title or tpl.get("title"), muscle)
    is_compound = pattern in PATTERN_COMPOUND

    # name is UNIQUE in the guide schema; attach hevy_template_id, tolerate name clashes
    cur.execute("""
        INSERT INTO exercises (name, pattern, primary_muscle, equipment, is_compound, hevy_template_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (name) DO UPDATE
          SET hevy_template_id = COALESCE(exercises.hevy_template_id, EXCLUDED.hevy_template_id),
              pattern          = COALESCE(exercises.pattern, EXCLUDED.pattern),
              primary_muscle   = COALESCE(exercises.primary_muscle, EXCLUDED.primary_muscle),
              equipment        = COALESCE(exercises.equipment, EXCLUDED.equipment),
              is_compound      = COALESCE(exercises.is_compound, EXCLUDED.is_compound)
        RETURNING id
    """, (name, pattern, muscle, equipment, is_compound, template_id))
    return cur.fetchone()[0]


def latest_bodyweight_lbs(cur, on_or_before):
    cur.execute("""SELECT weight_lbs FROM body_metrics
                   WHERE weight_lbs IS NOT NULL AND recorded_at::date <= %s
                   ORDER BY recorded_at DESC LIMIT 1""", (on_or_before,))
    row = cur.fetchone()
    return row[0] if row else None


def parse_ts(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def upsert_workout(cur, w):
    start = parse_ts(w["start_time"])
    end = parse_ts(w["end_time"]) if w.get("end_time") else None
    session_date = start.date()
    duration_min = int((end - start).total_seconds() // 60) if end else None
    bodyweight = latest_bodyweight_lbs(cur, session_date)

    cur.execute("""
        INSERT INTO workouts (session_date, split, duration_min, bodyweight_lbs, hevy_id)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (hevy_id) DO UPDATE
          SET session_date=EXCLUDED.session_date, split=EXCLUDED.split,
              duration_min=EXCLUDED.duration_min, bodyweight_lbs=EXCLUDED.bodyweight_lbs
        RETURNING id
    """, (session_date, w.get("title"), duration_min, bodyweight, w["id"]))
    workout_id = cur.fetchone()[0]

    # re-run safe: wipe children, reinsert
    cur.execute("DELETE FROM workout_sets WHERE workout_id=%s", (workout_id,))

    n_sets = 0
    for ex in w.get("exercises", []):
        ex_id = ensure_exercise(cur, ex["exercise_template_id"], ex.get("title"))
        idx = 0
        for s in ex.get("sets", []):
            if s.get("type") == "warmup":
                continue
            weight_lbs = kg_to_lb(s.get("weight_kg"))
            reps = s.get("reps")
            rir = rpe_to_rir(s.get("rpe"))
            cur.execute("""
                INSERT INTO workout_sets (workout_id, exercise_id, set_index, weight_lbs, reps, rir)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (workout_id, ex_id, idx, weight_lbs, reps, rir))
            idx += 1
            n_sets += 1
    return n_sets


def delete_workout(cur, hevy_id):
    cur.execute("DELETE FROM workouts WHERE hevy_id=%s", (hevy_id,))
    return cur.rowcount


def sync_body_measurements(cur):
    """Full pull of body_measurements -> body_metrics (no incremental endpoint exists)."""
    page, page_count, n = 1, 1, 0
    while page <= page_count:
        resp = api("/body_measurements", {"page": page, "pageSize": 10})
        page_count = resp.get("page_count", 1)
        for bm in resp.get("body_measurements", []):
            recorded = bm.get("created_at") or (bm.get("date") + "T12:00:00Z")
            cur.execute("""
                INSERT INTO body_metrics (weight_lbs, recorded_at, hevy_measurement_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (hevy_measurement_id) DO UPDATE
                  SET weight_lbs=EXCLUDED.weight_lbs, recorded_at=EXCLUDED.recorded_at
            """, (kg_to_lb(bm.get("weight_kg")), recorded, bm.get("id")))
            n += 1
        page += 1
    return n


# ---------------------------------------------------------------- main
def main():
    run_start = dt.datetime.now(dt.timezone.utc)
    with psycopg.connect(_db_url()) as conn:
        with conn.cursor() as cur:
            n_body = sync_body_measurements(cur)

            since = get_state(cur, "last_workout_event_at") or "1970-01-01T00:00:00Z"
            page, page_count = 1, 1
            upserted = deleted = 0
            while page <= page_count:
                resp = api("/workouts/events",
                           {"since": since, "page": page, "pageSize": 10})
                page_count = resp.get("page_count", 1)
                for ev in resp.get("events", []):
                    if ev.get("type") == "deleted":
                        deleted += delete_workout(cur, ev["workout"]["id"])
                    else:
                        upsert_workout(cur, ev["workout"])
                        upserted += 1
                page += 1
                time.sleep(0.15)

            # advance the watermark to run start (small overlap next time is harmless: upserts are idempotent)
            set_state(cur, "last_workout_event_at",
                      run_start.strftime("%Y-%m-%dT%H:%M:%SZ"))
        conn.commit()

    print(f"[hevy_sync] since={since} bodyweight_rows={n_body} "
          f"workouts_upserted={upserted} workouts_deleted={deleted}")


if __name__ == "__main__":
    main()
