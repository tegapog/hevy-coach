"""STEP 1 analysis: frequency, best sets, trend, balance, RPE.
Today is fixed to the session date so results are reproducible.
"""
import hevy, json
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

TODAY = datetime(2026, 9, 23, tzinfo=timezone.utc)
D = hevy.DATA

W = json.loads((D / "workouts_all.json").read_text())["workouts"]
TPLS = {t["id"]: t for t in json.loads((D / "exercise_templates_all.json").read_text())["exercise_templates"]}
BW = 68.0  # latest logged bodyweight kg

def dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def epley(weight, reps):
    return weight * (1 + reps / 30.0)

# ---------- FREQUENCY ----------
dates = sorted({dt(w["start_time"]).date() for w in W})
start_all, end_all = dates[0], dates[-1]
twelve_wk_ago = (TODAY - timedelta(weeks=12)).date()
recent_sessions = [d for d in dates if d >= twelve_wk_ago]
weeks_span = 12
freq_per_week = len(recent_sessions) / weeks_span
# longest gap across all history
gaps = [(dates[i] - dates[i-1]).days for i in range(1, len(dates))]
longest_gap = max(gaps) if gaps else 0
print("=== FREQUENCY ===")
print(f"logged span: {start_all} -> {end_all} ({len(dates)} distinct days, {len(W)} workouts)")
print(f"last 12 wk sessions: {len(recent_sessions)}  => {freq_per_week:.2f}/week")
print(f"longest gap ever: {longest_gap} days")

# ---------- BEST SETS + TREND ----------
# main lifts = top 6 by set count
top = json.loads((D / "top_lifts_by_sets.json").read_text())[:6]
# build per-template flat set list from workouts
sets_by_tpl = defaultdict(list)  # tid -> list of (date, set)
for w in W:
    d = dt(w["start_time"]).date()
    for ex in w["exercises"]:
        tid = ex["exercise_template_id"]
        for s in ex["sets"]:
            sets_by_tpl[tid].append((d, s))

def is_working(s):
    return s.get("type") not in ("warmup",)

BW_MOVES = {"729237D1", "29472BE1"}  # weighted pull-up, weighted dip -> add bodyweight
print("\n=== BEST SETS (working sets, reps<=10) ===")
best_rows = []
for t in top:
    tid = t["id"]; title = t["title"]
    tpl = TPLS.get(tid, {})
    cand = []
    for d, s in sets_by_tpl[tid]:
        if not is_working(s):
            continue
        wt, reps = s.get("weight_kg"), s.get("reps")
        if wt is None or reps is None or reps == 0 or reps > 10:
            continue
        load = wt + (BW if tid in BW_MOVES else 0)
        cand.append((d, load, wt, reps, epley(load, reps)))
    if not cand:
        best_rows.append((title, None))
        note = "duration/bodyweight-only" if tpl.get("type") in ("duration","bodyweight_reps","weight_duration") else "no qualifying sets"
        print(f"{title:32s} -> ({note})")
        continue
    heaviest = max(cand, key=lambda c: c[2])   # by logged weight
    best1rm = max(cand, key=lambda c: c[4])
    added = " (+bodyweight)" if tid in BW_MOVES else ""
    best_rows.append((title, best1rm))
    print(f"{title:32s} heaviest={heaviest[2]:.1f}kg x{heaviest[3]}  best e1RM={best1rm[4]:.1f}kg{added} (from {best1rm[2]:.1f}kg x{best1rm[3]})")

# ---------- TREND: e1RM now vs 8 weeks ago ----------
eight_ago = (TODAY - timedelta(weeks=8)).date()
print("\n=== TREND (best e1RM: last 8 wk  vs  the 8 wk before) ===")
for t in top:
    tid = t["id"]; title = t["title"]
    def best_e1rm(lo, hi):
        vals = []
        for d, s in sets_by_tpl[tid]:
            if not is_working(s): continue
            wt, reps = s.get("weight_kg"), s.get("reps")
            if wt is None or reps is None or reps == 0 or reps > 10: continue
            if lo <= d < hi:
                load = wt + (BW if tid in BW_MOVES else 0)
                vals.append(epley(load, reps))
        return max(vals) if vals else None
    now = best_e1rm(eight_ago, TODAY.date() + timedelta(days=1))
    prev = best_e1rm((TODAY - timedelta(weeks=16)).date(), eight_ago)
    if now is None and prev is None:
        continue
    def fmt(x): return f"{x:.1f}kg" if x is not None else "  --  "
    delta = f"{now-prev:+.1f}kg" if (now is not None and prev is not None) else "n/a"
    print(f"{title:32s} 8wk_ago={fmt(prev)}  now={fmt(now)}  Δ={delta}")

# ---------- BALANCE (last 8 weeks, working sets by primary muscle) ----------
print("\n=== BALANCE (working sets last 8 wk by primary_muscle_group) ===")
muscle_sets = Counter()
for w in W:
    d = dt(w["start_time"]).date()
    if d < eight_ago:
        continue
    for ex in w["exercises"]:
        tpl = TPLS.get(ex["exercise_template_id"], {})
        pmg = tpl.get("primary_muscle_group", "unknown")
        for s in ex["sets"]:
            if is_working(s):
                muscle_sets[pmg] += 1
if muscle_sets:
    avg = sum(muscle_sets.values()) / len(muscle_sets)
    for m, c in muscle_sets.most_common():
        flag = "  <-- UNDER HALF AVG" if c < avg/2 else ""
        print(f"  {m:16s} {c:3d} sets{flag}")
    print(f"  (avg per muscle = {avg:.1f})")
    # push vs pull
    PUSH = {"chest","shoulders","triceps"}
    PULL = {"lats","upper_back","biceps","lower_back","traps"}
    push = sum(c for m,c in muscle_sets.items() if m in PUSH)
    pull = sum(c for m,c in muscle_sets.items() if m in PULL)
    ratio = push/pull if pull else float('inf')
    print(f"  PUSH sets={push}  PULL sets={pull}  push:pull={ratio:.2f}:1" + ("  <-- >1.5 IMBALANCE" if ratio>1.5 else ""))

# ---------- RPE ----------
print("\n=== RPE ===")
rpes = [s.get("rpe") for w in W for ex in w["exercises"] for s in ex["sets"] if s.get("rpe") is not None]
if rpes:
    print(f"  logged RPE on {len(rpes)} sets, avg={sum(rpes)/len(rpes):.1f}")
else:
    print("  No RPE logged.")

# save summary
hevy.save("analysis_summary", {
    "today": TODAY.date().isoformat(),
    "workouts": len(W), "distinct_days": len(dates),
    "span": [start_all.isoformat(), end_all.isoformat()],
    "freq_per_week_12wk": round(freq_per_week,2), "longest_gap_days": longest_gap,
    "bodyweight_kg": BW,
})
