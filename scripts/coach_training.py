"""
Training coach (guide STEP 5), adapted to run on GitHub Actions against Supabase.

Adaptation note: the paper prompt groups by movement PATTERN. That conflates
different lifts (lat pulldown + weighted pull-up are both "vertical pull"), which
produces misleading prescriptions. We analyse PER EXERCISE (what you actually put
on a bar), and use the exercise's pattern only to decide the load increment
(+5 lb compound / +2.5 lb isolation). All of the prompt's branch logic is kept.

Your data has no RIR (Hevy RPE not logged) -> rising lifts get "repeat exactly",
which is exactly the prompt's null-RIR branch. Log RPE in Hevy to unlock auto-loading.
Weights are lbs (the sync converts kg->lbs), matching the prompt.
"""
import datetime as dt
from collections import defaultdict
import coach_common as cc

TODAY = dt.date.today()
# Guide uses 28 days; override with COACH_WINDOW_DAYS while you rebuild consistency.
WINDOW = int(cc.cfg("COACH_WINDOW_DAYS") or 28)
COMPOUND_PATTERNS = {"horizontal_push", "vertical_push", "horizontal_pull",
                     "vertical_pull", "hinge", "squat", "carry"}
MIN_SESSIONS = 3


def r1(x):
    return None if x is None else round(x)


def fetch(cur):
    since = TODAY - dt.timedelta(days=WINDOW)
    cur.execute("""
        SELECT e.id, e.name, e.pattern, w.session_date, max(ws.e1rm)::float
        FROM workout_sets ws
        JOIN workouts w  ON w.id = ws.workout_id
        JOIN exercises e ON e.id = ws.exercise_id
        WHERE ws.e1rm IS NOT NULL AND w.session_date >= %s
        GROUP BY e.id, e.name, e.pattern, w.session_date
        ORDER BY e.id, w.session_date
    """, (since,))
    series = defaultdict(lambda: {"name": None, "pattern": None, "pts": []})
    for eid, name, pat, d, e1 in cur.fetchall():
        series[eid]["name"] = name
        series[eid]["pattern"] = pat
        series[eid]["pts"].append((d, e1))

    # most recent session's working sets, per exercise
    cur.execute("""
        WITH latest AS (
          SELECT ws.exercise_id, max(w.session_date) AS d
          FROM workout_sets ws JOIN workouts w ON w.id = ws.workout_id
          GROUP BY ws.exercise_id
        )
        SELECT ws.exercise_id, l.d, ws.weight_lbs::float, ws.reps, ws.rir
        FROM latest l
        JOIN workouts w ON w.session_date = l.d
        JOIN workout_sets ws ON ws.workout_id = w.id AND ws.exercise_id = l.exercise_id
        ORDER BY ws.exercise_id, ws.id
    """)
    last = defaultdict(lambda: {"date": None, "sets": []})
    for eid, d, wt, reps, rir in cur.fetchall():
        last[eid]["date"] = d
        last[eid]["sets"].append({"weight": wt, "reps": reps, "rir": rir})

    cur.execute("""SELECT recorded_at::date, weight_lbs::float FROM body_metrics
                   WHERE weight_lbs IS NOT NULL AND recorded_at::date >= %s ORDER BY 1""", (since,))
    bw = cur.fetchall()
    cur.execute("SELECT DISTINCT session_date FROM workouts ORDER BY 1")
    sessions = [r[0] for r in cur.fetchall()]
    return series, last, bw, sessions


def median(xs):
    s = sorted(xs); n = len(s)
    if not n: return None
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


def prescribe(pattern, slope_wk, last_sets, bw_slope_wk):
    n_sets = len(last_sets)
    top = max(last_sets, key=lambda s: (s["weight"] or 0))
    load, reps, last_rir = top["weight"], top["reps"], last_sets[-1]["rir"]
    inc = 5 if pattern in COMPOUND_PATTERNS else 2.5
    stalled = slope_wk is not None and slope_wk <= 0
    rising = slope_wk is not None and slope_wk > 0

    if slope_wk is not None and load and slope_wk < -0.02 * load:
        return f"deload to {r1(load*0.9)} lb, repeat 2 sessions", (n_sets, reps, r1(load*0.9))
    if stalled:
        if bw_slope_wk is not None and bw_slope_wk < -0.3:
            return "hold — stall is a food problem (bodyweight falling), fix nutrition", (n_sets, reps, r1(load))
        return f"hold {r1(load)} lb, add 1 rep to every set", (n_sets, (reps + 1) if reps else None, r1(load))
    if rising:
        if last_rir is not None and last_rir >= 2:
            return f"add {inc} lb -> {r1((load or 0)+inc)} lb", (n_sets, reps, r1((load or 0)+inc))
        return f"repeat {r1(load)} lb exactly (log RPE to unlock +load)", (n_sets, reps, r1(load))
    return f"keep at {r1(load)} lb", (n_sets, reps, r1(load))


def main():
    with cc.db() as conn, conn.cursor() as cur:
        series, last, bw, sessions = fetch(cur)
    bw_slope = cc.lin_slope_per_week([d for d, _ in bw], [v for _, v in bw]) if len(bw) >= 2 else None

    if sessions:
        gaps = [(sessions[i] - sessions[i-1]).days for i in range(1, len(sessions))]
        recent = [g for i, g in enumerate(gaps) if sessions[i+1] >= TODAY - dt.timedelta(days=WINDOW)]
        med = median(recent or gaps) or 0
        days_since = (TODAY - sessions[-1]).days
        if med and days_since > med:
            cc.tg_send(f"🏋️ Coach: last trained {days_since}d ago (usual ~{med:.0f}d). Get a session in.")
            print("[training] nudge sent"); return

    lines, ignored = [], []
    for eid, s in series.items():
        dates = [d for d, _ in s["pts"]]
        if len(set(dates)) < MIN_SESSIONS:
            ignored.append(f"{s['name']}({len(set(dates))})"); continue
        slope = cc.lin_slope_per_week(dates, [v for _, v in s["pts"]])
        best = max(v for _, v in s["pts"])
        action, (ns, reps, load) = prescribe(s["pattern"], slope, last[eid]["sets"], bw_slope)
        trend = f"{'+' if slope >= 0 else ''}{slope:.1f} lb/wk"
        rx = f"{ns}×{reps} @ {load} lb" if load else f"{ns}×{reps}"
        lines.append((last[eid]["date"], s["name"],
                      f"• <b>{s['name']}</b>: {rx}  (e1RM {best:.0f}, {trend}) → {action}"))

    lines.sort(key=lambda t: (t[0], t[1]), reverse=True)
    header = f"🏋️ <b>Training coach</b> — {TODAY:%a %d %b}"
    body = "\n".join(t[2] for t in lines) or f"No lift has {MIN_SESSIONS}+ sessions in the last {WINDOW} days yet."
    foot = f"\n<i>skipped (&lt;{MIN_SESSIONS} sessions): {', '.join(ignored)}</i>" if ignored else ""
    cc.tg_send(f"{header}\n{body}{foot}")
    print("[training] sent")


if __name__ == "__main__":
    main()
