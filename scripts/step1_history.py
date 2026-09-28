"""STEP 1 cont: pull exercise_history for top-6 lifts by set count."""
import hevy, json, time

top = json.loads((hevy.DATA / "top_lifts_by_sets.json").read_text())
top6 = top[:6]
print("Pulling history for top 6:")
for t in top6:
    tid = t["id"]
    st, hist = hevy.get(f"/exercise_history/{tid}")
    safe = "".join(c if c.isalnum() else "_" for c in t["title"])[:40]
    hevy.save(f"history_{safe}_{tid[:8]}", {"template": t, "status": st, "history": hist})
    n = 0
    if isinstance(hist, dict):
        # try to count sessions/sets
        n = len(hist.get("exercises", hist.get("history", []))) if isinstance(hist, dict) else 0
    print(f"  {t['title']!r} status={st} keys={list(hist.keys()) if isinstance(hist,dict) else type(hist)}")
    time.sleep(0.2)

# also dump body measurements content shape
bm = json.loads((hevy.DATA / "body_measurements_page1.json").read_text())
print("BODY sample:", json.dumps(bm)[:400])
