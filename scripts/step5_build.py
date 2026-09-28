"""STEP 5: create folder + 7 routines in Hevy. Only CREATE, never edit/delete."""
import hevy, json, time

# ---------- set builders ----------
def wr(weight, lo, hi, n, warm=None):
    """weight_reps working sets w/ rep_range; optional warmups [(w,reps),...]. weight=None -> RPE (null)."""
    sets = []
    for w, r in (warm or []):
        sets.append({"type": "warmup", "weight_kg": w, "reps": r})
    for _ in range(n):
        sets.append({"type": "normal", "weight_kg": weight, "rep_range": {"start": lo, "end": hi}})
    return sets

def bw(added, lo, hi, n):
    """bodyweight_weighted (pull up): weight_kg = added load."""
    return [{"type": "normal", "weight_kg": added, "rep_range": {"start": lo, "end": hi}} for _ in range(n)]

def reps(lo, hi, n):
    return [{"type": "normal", "rep_range": {"start": lo, "end": hi}} for _ in range(n)]

def dur(secs, n):
    return [{"type": "normal", "duration_seconds": secs} for _ in range(n)]

def ex(tid, rest, note, sets, ss=None):
    return {"exercise_template_id": tid, "superset_id": ss, "rest_seconds": rest, "notes": note, "sets": sets}

PROG = ("PROGRESSION: start at the bottom of each rep range. Hit the top of the range on all sets "
        "for 2 sessions in a row -> add load (+2.5kg barbell, next DB / +1-2kg isolation) and reset to the bottom. "
        "Miss the bottom or speed dies -> hold. INJURED lifts (pressing, weighted pull-ups, curls): add load ONLY after a fully pain-free session; pain = hold or drop.")

routines = []

# ===== PHASE 1 (Wk1-3) =====
routines.append({
 "title": "Wk1-3 Lower (Rebuild)",
 "notes": "PHASE 1 goal: drive legs hard while the shoulder/elbow heal. " + PROG,
 "exercises": [
   ex("D04AC939",150,"Brace hard, knees track over toes, control the descent.",
      wr(70,6,8,4,warm=[(40,8),(60,5)])),
   ex("2B4B7310",150,"Push hips back, bar close, feel hamstrings. Sub Back Extension if lower back complains.",
      wr(60,8,10,3,warm=[(40,8)])),
   ex("C7973E0E",120,"[RPE 8 - no history, effort-based] Full depth, no lockout.", wr(None,10,12,3)),
   ex("11A123F3",75,"[RPE 8] Slow the negative.", wr(None,12,15,3)),
   ex("75A4F6C4",60,"[RPE 8] 1-sec squeeze at top.", wr(None,12,15,3), ss=0),
   ex("062AB91A",60,"[RPE 8] Pause & stretch at the bottom.", wr(None,12,15,4), ss=0),
 ]})

routines.append({
 "title": "Wk1-3 Upper Rehab (pain-free only)",
 "notes": "PHASE 1: pain-free rehab ONLY. If a set hurts under load, drop weight or skip and tell your coach. Do NOT push through shoulder/elbow pain.",
 "exercises": [
   ex("6A6C31A5",90,"Light. Only pull through a range that does not pinch.", wr(40,12,15,3)),
   ex("0393F233",90,"Light, neutral grip, no jerking, pain-free.", wr(None,12,15,3)),
   ex("BE640BA0",60,"Very light. Elbows high - this is rehab.", wr(None,15,20,3)),
   ex("C315DC2A",60,"Very light, lead with the elbows.", wr(None,15,20,3)),
   ex("BE289E45",60,"~5kg, ONLY if pain-free. Stop below shoulder height if it pinches.", wr(5,15,20,3)),
 ]})

routines.append({
 "title": "Wk1-3 Core + Conditioning",
 "notes": "PHASE 1: core + easy cardio. Finish with 15 min incline walk or bike (LISS, zone 2) - builds the base, spares recovery.",
 "exercises": [
   ex("23A48484",60,"[RPE 8] Crunch ribs toward pelvis.", wr(None,15,15,4)),
   ex("C6C9B8A0",45,"Squeeze glutes, no sag.", dur(45,3)),
   ex("E3EDA509",45,"Stack the hips, straight line.", dur(30,3)),
 ]})

# ===== PHASE 2 (Wk4-9) =====
routines.append({
 "title": "Wk4-9 Lower",
 "notes": "PHASE 2-3 goal: build legs (your weak area). Wk7 = DELOAD (2 sets/exercise, ~60% load). Wk8-9 = intensify: top of ranges, add load, keep 1 rep in reserve on squat/RDL. " + PROG,
 "exercises": [
   ex("D04AC939",180,"Brace, hit depth, control.", wr(75,6,8,4,warm=[(40,8),(60,5)])),
   ex("2B4B7310",150,"Hips back, bar close. Sub Back Extension if lower back complains.", wr(67.5,8,10,4,warm=[(40,8)])),
   ex("C7973E0E",120,"[RPE 8] Full depth, no lockout.", wr(None,12,12,3)),
   ex("11A123F3",75,"[RPE 8] Control the negative.", wr(None,12,15,4)),
   ex("75A4F6C4",60,"[RPE 8] 1-sec top squeeze.", wr(None,15,15,3), ss=0),
   ex("062AB91A",60,"[RPE 8] Pause + stretch.", wr(None,12,15,4), ss=0),
 ]})

routines.append({
 "title": "Wk4-9 Upper A (Push + Biceps)",
 "notes": "PHASE 2-3: CHEST PRIORITY (your lagging area) + biceps so triceps arent pre-fatigued. Reintroduce pressing pain-guided. Phase 3: add handstand/pike skill practice up front if pain-free. Wk7 deload. " + PROG,
 "exercises": [
   ex("FBF92739",120,"[RPE 7-8] Chest priority - machine spares the shoulder. Press pain-free.", wr(None,8,12,4)),
   ex("07B38369",90,"Start 20kg, build to 30. Add load only after a pain-free session.", wr(20,10,12,3,warm=[(12,10)])),
   ex("78683336",75,"[RPE 8] Big stretch, hard squeeze - grows the lagging chest.", wr(None,12,15,3)),
   ex("BE289E45",60,"~6-7.5kg. Strict, no swing - builds width.", wr(6,15,20,4), ss=0),
   ex("37FCC2BB",60,"[RPE 8] Fresh biceps here. Stop if the elbow flares.", wr(None,10,12,3), ss=0),
 ]})

routines.append({
 "title": "Wk4-9 Upper B (Pull + Triceps)",
 "notes": "PHASE 2-3: back width + triceps so biceps arent pre-fatigued. Phase 3: add tuck front-lever holds up front if pain-free. Wk7 deload. " + PROG,
 "exercises": [
   ex("729237D1",150,"Start at BODYWEIGHT (weight=0). Full hang to chin, no kipping. Add load only when pain-free AND >=10 reps.", bw(0,6,10,4)),
   ex("6A6C31A5",90,"~50kg. Drive elbows to hips.", wr(50,10,12,3)),
   ex("0393F233",90,"[RPE 8] Squeeze the shoulder blades.", wr(None,10,12,3)),
   ex("C315DC2A",60,"[RPE 8] Lead with the elbows.", wr(None,15,20,3), ss=0),
   ex("93A552C6",60,"[RPE 8] Fresh triceps here. Elbows pinned; stop if the elbow flares.", wr(None,12,15,3), ss=0),
 ]})

routines.append({
 "title": "Wk4-9 Delts + Arms + Core",
 "notes": "PHASE 2-3: optional 5th day / frame pump. Skip if recovery is short in the cut. Wk7 deload. " + PROG,
 "exercises": [
   ex("BE289E45",45,"[RPE 8] Width, width, width.", wr(None,15,20,4), ss=0),
   ex("D8281C62",45,"[RPE 8] Squeeze rear delts.", wr(None,15,20,3), ss=0),
   ex("651F844C",60,"[RPE 8] Big stretch, hard squeeze.", wr(None,12,15,3)),
   ex("93A552C6",60,"[RPE 8] Elbows pinned.", wr(None,12,15,3), ss=1),
   ex("ADA8623C",60,"[RPE 8] No swing.", wr(None,12,15,3), ss=1),
   ex("23A48484",45,"[RPE 8] Crunch ribs to pelvis.", wr(None,15,15,4), ss=2),
   ex("F8356514",45,"Only if grip/shoulder pain-free.", reps(12,15,3), ss=2),
 ]})

# ---------- create folder ----------
st, f = hevy.request("POST", "/routine_folders", body={"routine_folder": {"title": "Aesthetic Hypertrophy Block"}})
hevy.save("created_folder", {"status": st, "body": f})
print(f"FOLDER status={st} body={json.dumps(f)[:200]}")
if st not in (200, 201):
    raise SystemExit("Folder creation failed, stopping.")
folder_id = f.get("routine_folder", {}).get("id") or f.get("id")
print(f"folder_id={folder_id}")

# ---------- create routines ----------
created = []
for r in routines:
    payload = {"routine": {"title": r["title"], "folder_id": folder_id,
                           "notes": r["notes"], "exercises": r["exercises"]}}
    st, resp = hevy.request("POST", "/routines", body=payload)
    ok = st in (200, 201)
    safe = "".join(c if c.isalnum() else "_" for c in r["title"])
    hevy.save(f"created_routine_{safe}", {"status": st, "body": resp})
    rid = None
    if ok:
        rr = resp.get("routine")
        if isinstance(rr, list): rr = rr[0] if rr else {}
        rid = (rr or {}).get("id")
    created.append((r["title"], st, rid, len(r["exercises"])))
    print(f"ROUTINE '{r['title']}' status={st} id={rid}")
    if not ok:
        print("   ERROR body:", json.dumps(resp)[:400])
    time.sleep(0.3)

hevy.save("created_routines_index", {"folder_id": folder_id, "created": created})
print("\nSUMMARY:")
for t, st, rid, n in created:
    print(f"  [{ 'OK' if st in (200,201) else 'FAIL '+str(st)}] {t}  ({n} exercises)  id={rid}")
