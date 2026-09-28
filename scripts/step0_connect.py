"""STEP 0: Connection check."""
import hevy

def main():
    # 1. user info
    st, user = hevy.get("/user/info")
    if st in (401, 403):
        print(f"AUTH_FAIL {st}")
        print("A 401/403 on the first call means the key is wrong or the account is not Hevy Pro.")
        print("The API is Pro-only. Stopping.")
        return
    if st != 200:
        print(f"UNEXPECTED {st}: {user}")
        return
    hevy.save("user_info", user)
    username = user.get("username") or user.get("name") or "(unknown)"
    print(f"USERNAME={username}")

    # 2. workouts count
    st, cnt = hevy.get("/workouts/count")
    hevy.save("workouts_count", cnt)
    print(f"WORKOUT_COUNT_STATUS={st} BODY={cnt}")

    # 3. routines + folders
    st, routines = hevy.get("/routines", {"page": 1, "pageSize": 10})
    hevy.save("routines_page1", routines)
    print(f"ROUTINES_STATUS={st}")
    if isinstance(routines, dict):
        rlist = routines.get("routines", [])
        print(f"ROUTINE_COUNT_FIELD page_count={routines.get('page_count')} shown={len(rlist)}")
        for r in rlist:
            print(f"  ROUTINE id={r.get('id')} title={r.get('title')!r} folder={r.get('folder_id')}")

    st, folders = hevy.get("/routine_folders", {"page": 1, "pageSize": 10})
    hevy.save("routine_folders_page1", folders)
    print(f"FOLDERS_STATUS={st}")
    if isinstance(folders, dict):
        flist = folders.get("routine_folders", [])
        for f in flist:
            print(f"  FOLDER id={f.get('id')} title={f.get('title')!r}")

if __name__ == "__main__":
    main()
