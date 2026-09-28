"""STEP 1: Pull baseline data and save raw JSON to data/."""
import hevy, json, time

def pull_all_workouts():
    st, first = hevy.get("/workouts", {"page": 1, "pageSize": 10})
    if st != 200:
        print(f"WORKOUTS_FAIL {st}: {first}")
        return None
    page_count = first.get("page_count", 1)
    workouts = list(first.get("workouts", []))
    for p in range(2, page_count + 1):
        st, pg = hevy.get("/workouts", {"page": p, "pageSize": 10})
        if st != 200:
            print(f"  page {p} failed {st}")
            continue
        workouts.extend(pg.get("workouts", []))
        time.sleep(0.15)
    hevy.save("workouts_all", {"count": len(workouts), "workouts": workouts})
    print(f"WORKOUTS pulled={len(workouts)} page_count={page_count}")
    return workouts

def pull_templates():
    st, first = hevy.get("/exercise_templates", {"page": 1, "pageSize": 100})
    if st != 200:
        print(f"TEMPLATES_FAIL {st}: {first}")
        return None
    page_count = first.get("page_count", 1)
    tpls = list(first.get("exercise_templates", []))
    for p in range(2, page_count + 1):
        st, pg = hevy.get("/exercise_templates", {"page": p, "pageSize": 100})
        if st != 200:
            print(f"  tpl page {p} failed {st}")
            continue
        tpls.extend(pg.get("exercise_templates", []))
        time.sleep(0.15)
    hevy.save("exercise_templates_all", {"count": len(tpls), "exercise_templates": tpls})
    custom = [t for t in tpls if t.get("is_custom")]
    print(f"TEMPLATES pulled={len(tpls)} custom={len(custom)}")
    return tpls

def pull_body():
    st, bm = hevy.get("/body_measurements", {"page": 1, "pageSize": 10})
    if st != 200:
        print(f"BODY_MEAS status={st} body={bm}")
        hevy.save("body_measurements", {"status": st, "body": bm})
        return None
    hevy.save("body_measurements_page1", bm)
    print(f"BODY_MEAS status={st} keys={list(bm.keys()) if isinstance(bm,dict) else type(bm)}")
    return bm

def main():
    w = pull_all_workouts()
    t = pull_templates()
    pull_body()

    # Rank lifts by number of sets across all workouts
    if w is not None:
        from collections import Counter
        set_counts = Counter()
        name_by_id = {}
        for wk in w:
            for ex in wk.get("exercises", []):
                tid = ex.get("exercise_template_id")
                name_by_id[tid] = ex.get("title")
                set_counts[tid] += len(ex.get("sets", []))
        top = set_counts.most_common(10)
        print("TOP LIFTS BY SET COUNT:")
        for tid, c in top:
            print(f"  {c:4d} sets  {name_by_id.get(tid)!r}  id={tid}")
        hevy.save("top_lifts_by_sets",
                  [{"id": tid, "title": name_by_id.get(tid), "sets": c} for tid, c in set_counts.most_common(30)])

if __name__ == "__main__":
    main()
