# Hevy → Supabase sync — setup

Every time you save a workout in Hevy, a cloud cron (GitHub Actions, every 15 min)
copies it into your Supabase database. No Telegram texting for lifts. Your laptop
can be off. The three coaches from the guide read the same database.

> **Not instant:** Hevy has no webhooks, so this polls every ~15 min. Nothing is
> ever missed — it always asks Hevy "what changed since last time".

## What the sync does
- Pulls only what changed (`GET /workouts/events?since=<last sync>`).
- Stores weights in **kg** (metric throughout); e1RM is computed in kg.
- Converts **RPE → RIR** (`rir = 10 − rpe`).
- Skips **warmup** sets so e1RM trends stay clean.
- Classifies each exercise into the coach's 8 movement patterns.
- Also syncs your Hevy **bodyweight** logs → `body_metrics`.
- First run **backfills your whole history** (all ~80 workouts).

---

## Step 1 — Create the Supabase database
1. Go to https://supabase.com → sign up → **New project**.
2. Name it, pick a region near you (London/EU), and **save the database password** it shows you.
3. Wait ~2 min for it to provision.

## Step 2 — Create the tables
1. In Supabase: **SQL Editor → New query**.
2. Paste the entire contents of `sql/schema.sql` and click **Run**.
3. Check **Table Editor** — you should see 10 tables + `sync_state`, and a `v_adherence` view.
   (Your goal rows — 2,265 kcal, −1 lb/wk — are pre-inserted; edit in Table Editor if wrong.)

## Step 3 — Get your connection string
1. Supabase: **Project Settings → Database → Connection string → URI**.
2. Copy it. It looks like:
   `postgresql://postgres:[YOUR-PASSWORD]@db.xxxx.supabase.co:5432/postgres`
3. Replace `[YOUR-PASSWORD]` with the password from Step 1. Append `?sslmode=require` if not present.
   *(If GitHub's runner can't reach the direct host, use the **Session pooler** URI from the same page instead.)*

## Step 4 — Put the code on GitHub
1. Create a **new GitHub repo** (private is fine).
2. Push this `hevy-coach` folder to it. `.env` and `data/` are gitignored, so **no secrets get committed** — verify `.env` is NOT in the pushed files.
3. In the repo: **Settings → Secrets and variables → Actions → New repository secret**. Add two:
   - `HEVY_API_KEY` = your Hevy key (the one in `.env`)
   - `DATABASE_URL` = the connection string from Step 3

## Step 5 — Run it
1. Repo → **Actions** tab → enable workflows if prompted.
2. Open **"Hevy → Supabase sync" → Run workflow** (manual first run = full backfill).
3. Watch the log: `workouts_upserted=80 ...`. Then check Supabase Table Editor → `workout_sets`
   has rows with the `e1rm` column filled in automatically.
4. After that it runs itself every 15 min.

### Cost note
Scheduled Actions on a **public** repo are free/unlimited. On a **private** repo, every-15-min
(~2,900 runs/mo × <1 min) can exceed the 2,000 free minutes — either make the repo public
(the code holds no secrets) or change the cron in `.github/workflows/hevy-sync.yml` to
`*/30` or hourly.

## Local test (optional, before GitHub)
```bash
pip install -r requirements.txt
export DATABASE_URL='postgresql://postgres:...@db.xxxx.supabase.co:5432/postgres?sslmode=require'
python scripts/hevy_sync.py     # HEVY_API_KEY is read from .env locally
```
