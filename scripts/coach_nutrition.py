"""
Nutrition coach (guide STEP 4), adapted to Supabase + Telegram.

7 days of macros vs where bodyweight is actually heading, and ONE change for
tomorrow. Reads food_log / body_metrics / daily_plan. Faithful to the prompt:
- <5 weigh-ins in 14 days -> skip the rate trend and say so.
- protein floor 1.6 g/kg of most recent bodyweight; a day with no food_log is
  "not covered", not "under the floor".
- if <4 of the last 7 days have any food_log, say so and prescribe nothing.
"""
import datetime as dt
import coach_common as cc

TODAY = dt.date.today()


def main():
    with cc.db() as conn, conn.cursor() as cur:
        # last 7 whole days (yesterday back 6)
        cur.execute("""
            SELECT consumed_at::date d, sum(calories), sum(protein_g), sum(carbs_g), sum(fat_g)
            FROM food_log
            WHERE consumed_at::date BETWEEN %s AND %s
            GROUP BY 1 ORDER BY 1
        """, (TODAY - dt.timedelta(days=7), TODAY - dt.timedelta(days=1)))
        days = {r[0]: r[1:] for r in cur.fetchall()}

        cur.execute("""SELECT recorded_at::date, weight_kg FROM body_metrics
                       WHERE weight_kg IS NOT NULL AND recorded_at::date >= %s ORDER BY 1""",
                    (TODAY - dt.timedelta(days=14),))
        # keep latest weigh-in per day
        bw = {}
        for d, w in cur.fetchall():
            bw[d] = float(w)

        cur.execute("SELECT weight_kg FROM body_metrics WHERE weight_kg IS NOT NULL ORDER BY recorded_at DESC LIMIT 1")
        r = cur.fetchone()
        cur_bw = float(r[0]) if r else None

        cur.execute("SELECT label, target_value FROM daily_plan WHERE item_type='goal'")
        goals = {k: float(v) for k, v in cur.fetchall() if v is not None}

        cur.execute("SELECT target_ref FROM daily_plan WHERE active AND item_type='meal'")
        planned_meals = [r[0] for r in cur.fetchall() if r[0]]

    n_logged_days = len(days)
    if n_logged_days < 4:
        cc.tg_send(f"🥗 Nutrition coach — only {n_logged_days}/7 days logged. "
                   f"Log your food for a few days and I'll have something to say.")
        print("[nutrition] insufficient data"); return

    # rate trend
    rate_txt = ""
    if len(bw) >= 5:
        slope_wk = cc.lin_slope_per_week(list(bw.keys()), list(bw.values()))
        goal_rate = goals.get("weight_rate")
        rate_txt = f"Weight trend {slope_wk:+.2f} kg/wk"
        if goal_rate is not None:
            if slope_wk > goal_rate + 0.1:
                rate_txt += f" (faster than target {goal_rate:+.2f} — you can eat a bit more)"
            elif slope_wk < goal_rate - 0.1:
                rate_txt += f" (slower than target {goal_rate:+.2f} — tighten intake)"
            else:
                rate_txt += f" (on target {goal_rate:+.1f})"
    else:
        rate_txt = f"Weight trend: need 5+ weigh-ins in 14 days (have {len(bw)})."

    # protein floor
    floor = 1.6 * cur_bw if cur_bw else None
    under_floor = 0
    if floor:
        for d, vals in days.items():
            p = float(vals[1] or 0)
            if p < floor:
                under_floor += 1

    # missed planned meals yesterday
    yest = TODAY - dt.timedelta(days=1)
    missed_meals = []
    if planned_meals:
        with cc.db() as conn, conn.cursor() as cur:
            for ref in planned_meals:
                cur.execute("""SELECT 1 FROM food_log fl JOIN foods f ON f.id=fl.food_id
                               WHERE fl.consumed_at::date=%s AND lower(f.name)=lower(%s) LIMIT 1""", (yest, ref))
                if not cur.fetchone():
                    missed_meals.append(ref)

    # yesterday totals
    y = days.get(yest)
    ytxt = (f"Yesterday: {round(float(y[0] or 0))} kcal / {round(float(y[1] or 0))}P / "
            f"{round(float(y[2] or 0))}C / {round(float(y[3] or 0))}F" if y else "Yesterday: nothing logged")

    # pick ONE gap: protein-floor days > missed meals > avg cal off goal
    change = None
    if floor and under_floor > 0:
        gap = f"protein under {floor:.0f} g on {under_floor}/{n_logged_days} days"
        change = f"add a 40 g protein serving (whey/eggs) to your lightest meal tomorrow"
    elif missed_meals:
        gap = f"missed planned meal(s): {', '.join(missed_meals)}"
        change = f"hit {missed_meals[0]} tomorrow"
    else:
        cal_goal = goals.get("calories")
        if cal_goal:
            avg = sum(float(v[0] or 0) for v in days.values()) / n_logged_days
            off = avg - cal_goal
            gap = f"averaging {round(avg)} kcal vs {round(cal_goal)} target ({off:+.0f})"
            change = ("cut ~%d kcal/day tomorrow" % round(off) if off > 100
                      else "add ~%d kcal/day tomorrow" % round(-off) if off < -100
                      else "hold — you're on your calorie target")
        else:
            gap = "no calorie goal set"; change = "set a calorie target"

    cc.tg_send(f"🥗 <b>Nutrition coach</b> — {TODAY:%a %d %b}\n"
               f"{ytxt}\n{rate_txt}\nGap: {gap}\n➡️ Tomorrow: {change}")
    print("[nutrition] sent")


if __name__ == "__main__":
    main()
