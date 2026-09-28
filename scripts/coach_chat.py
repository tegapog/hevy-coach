"""
Conversational coach: answer free-text questions ("how's my squat?", "what should
I add on bench?") grounded in the user's own Supabase data.

Builds a compact context (per-exercise e1RM + trend + last load, bodyweight,
nutrition, goals) and asks Gemini to answer as the user's strength coach.
Used by telegram_food.py when a message contains a question.
"""
import datetime as dt
from collections import defaultdict
import coach_common as cc

CHAT_MODEL = cc.cfg("GEMINI_CHAT_MODEL") or "gemini-flash-latest"


def build_context(cur, days=120):
    today = dt.date.today()
    since = today - dt.timedelta(days=days)

    # per-exercise: best e1rm per session -> trend + best + last load/reps
    cur.execute("""
        SELECT e.name, e.pattern, w.session_date, max(ws.e1rm)::float,
               (array_agg(ws.weight_kg::float ORDER BY ws.weight_kg DESC))[1],
               (array_agg(ws.reps ORDER BY ws.weight_kg DESC))[1]
        FROM workout_sets ws
        JOIN workouts w  ON w.id = ws.workout_id
        JOIN exercises e ON e.id = ws.exercise_id
        WHERE ws.e1rm IS NOT NULL AND w.session_date >= %s
        GROUP BY e.name, e.pattern, w.session_date
        ORDER BY e.name, w.session_date
    """, (since,))
    ex = defaultdict(lambda: {"pattern": None, "dates": [], "e1rm": [], "last_load": None, "last_reps": None, "last_date": None})
    for name, pat, d, e1, wt, reps in cur.fetchall():
        r = ex[name]
        r["pattern"] = pat
        r["dates"].append(d); r["e1rm"].append(e1)
        if r["last_date"] is None or d >= r["last_date"]:
            r["last_date"] = d; r["last_load"] = wt; r["last_reps"] = reps

    lines = ["EXERCISES (last %d days):" % days]
    for name, r in sorted(ex.items(), key=lambda kv: kv[1]["last_date"] or dt.date.min, reverse=True):
        if len(set(r["dates"])) < 2:
            continue
        slope = cc.lin_slope_per_week(r["dates"], r["e1rm"])
        lines.append(f"- {name} [{r['pattern']}]: best e1RM {max(r['e1rm']):.1f}kg, "
                     f"trend {slope:+.1f}kg/wk over {len(set(r['dates']))} sessions, "
                     f"last {r['last_load']}kg×{r['last_reps']} on {r['last_date']}")

    cur.execute("SELECT recorded_at::date, weight_kg::float FROM body_metrics WHERE weight_kg IS NOT NULL ORDER BY recorded_at DESC LIMIT 5")
    bw = cur.fetchall()
    if bw:
        lines.append(f"BODYWEIGHT: latest {bw[0][1]}kg ({bw[0][0]}); {len(bw)} recent weigh-ins.")

    cur.execute("""SELECT coalesce(avg(day_cal),0), coalesce(avg(day_p),0) FROM (
                     SELECT consumed_at::date d, sum(calories) day_cal, sum(protein_g) day_p
                     FROM food_log WHERE consumed_at::date >= %s GROUP BY 1) t""",
                (today - dt.timedelta(days=7),))
    a = cur.fetchone()
    if a and a[0]:
        lines.append(f"NUTRITION (7d avg): {float(a[0]):.0f} kcal, {float(a[1]):.0f}g protein/day.")

    cur.execute("SELECT label, target_value, target_unit FROM daily_plan WHERE item_type='goal'")
    goals = cur.fetchall()
    if goals:
        lines.append("GOALS: " + "; ".join(f"{l}={v}{u or ''}" for l, v, u in goals))

    has_rpe = False
    cur.execute("SELECT count(*) FROM workout_sets WHERE rir IS NOT NULL")
    if cur.fetchone()[0] > 0:
        has_rpe = True
    lines.append(f"NOTE: RPE/RIR logged = {has_rpe}. All weights in kg.")
    return "\n".join(lines)


SYSTEM = """You are this lifter's strength & hypertrophy coach. Answer their question
using ONLY the data below — cite their actual numbers (kg, e1RM, trend). Be direct and
concise (a Telegram message, no more than ~120 words). Give specific progressive-overload
guidance: what to add and when. If RPE/RIR is not logged, note that logging RPE on top
sets unlocks precise load jumps. If the data can't answer it, say so plainly. No hype.

THEIR DATA:
{context}

QUESTION: {q}"""


def answer(cur, question):
    key = cc.cfg("GEMINI_API_KEY")
    if not key:
        return "Coach chat needs GEMINI_API_KEY set."
    ctx = build_context(cur)
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{CHAT_MODEL}:generateContent?key={key}")
    body = {"contents": [{"parts": [{"text": SYSTEM.format(context=ctx, q=question)}]}],
            "generationConfig": {"temperature": 0.3}}
    st, resp = cc.http_json(url, data=body, headers={"Content-Type": "application/json"})
    if st != 200:
        return f"(coach chat error {st})"
    try:
        return resp["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        return "(couldn't generate an answer)"
