"""
Telegram food/supplement/bodyweight logger (guide STEP 2 + 3 combined), no n8n.

Runs on a GitHub Actions cron. Each tick:
  1. Poll Telegram getUpdates (offset saved in sync_state).
  2. For each message: transcribe voice via Groq (if key set), else use the text.
     Insert a row in `messages` (status pending).  [STEP 2]
  3. Parse the text with Gemini -> {foods, supplements, body}.               [STEP 3]
     Look up macros in USDA, write food_log / supplement_log / body_metrics.
  4. Reply with what was logged.

WORKOUTS ARE NOT LOGGED HERE — they come from Hevy. If you mention lifting, the
bot tells you it's already handled by the Hevy sync.

Degrades gracefully: missing GROQ -> voice notes flagged needs_review; missing
USDA -> foods flagged needs_review; missing GEMINI -> message flagged needs_review.
"""
import json
import mimetypes
import uuid
import datetime as dt
import urllib.request
import urllib.error
import coach_common as cc

TG = "https://api.telegram.org/bot{tok}/{method}"
GEMINI_MODEL = cc.cfg("GEMINI_MODEL") or "gemini-flash-lite-latest"


# ----------------------------------------------------------------- telegram io
def tg(method, params=None, token=None):
    token = token or cc.cfg("TELEGRAM_BOT_TOKEN", required=True)
    st, resp = cc.http_json(TG.format(tok=token, method=method),
                            data=params, headers={"Content-Type": "application/json"} if params else None,
                            method="POST" if params else "GET")
    return resp


def tg_download(file_id, token):
    resp = tg("getFile", {"file_id": file_id}, token)
    path = resp.get("result", {}).get("file_path")
    if not path:
        return None
    url = f"https://api.telegram.org/file/bot{token}/{path}"
    with urllib.request.urlopen(url, timeout=60) as r:
        return r.read()


def reply(chat_id, text, token):
    tg("sendMessage", {"chat_id": chat_id, "text": text}, token)


# ----------------------------------------------------------------- groq (voice)
def transcribe(audio_bytes):
    key = cc.cfg("GROQ_API_KEY")
    if not key:
        return None
    boundary = "----" + uuid.uuid4().hex
    parts = []
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\nwhisper-large-v3-turbo\r\n")
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"response_format\"\r\n\r\ntext\r\n")
    pre = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"voice.ogg\"\r\n"
           f"Content-Type: audio/ogg\r\n\r\n").encode()
    body = "".join(parts).encode() + pre + audio_bytes + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/transcriptions", data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.read().decode().strip()
    except urllib.error.HTTPError as e:
        print("[groq]", e.code, e.read().decode(errors="replace")[:200])
        return None


# ----------------------------------------------------------------- gemini (parse)
PARSE_PROMPT = """You extract a fitness log from one message. Return ONLY JSON:
{"foods":[{"name":"","brand":"","grams":0}],
 "supplements":[{"name":"","quantity":1}],
 "body":{"weight_kg":null,"bodyfat_pct":null,"waist_in":null,"resting_hr":null},
 "mentioned_food":false,"mentioned_lifting":false}
Rules: lower-case names. Estimate grams for each food from the text (e.g. "2 eggs"~100,
"30g whey"=30). If you cannot estimate grams, use 0. Bodyweight in KILOGRAMS
(if stated in lb, convert: 1 lb = 0.453592 kg). Never invent numbers not implied.
Empty arrays where nothing applies.
Message: """


def parse_message(text):
    key = cc.cfg("GEMINI_API_KEY")
    if not key:
        return None
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{GEMINI_MODEL}:generateContent?key={key}")
    body = {"contents": [{"parts": [{"text": PARSE_PROMPT + text}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0}}
    st, resp = cc.http_json(url, data=body, headers={"Content-Type": "application/json"})
    if st != 200:
        print("[gemini]", st, str(resp)[:200])
        return None
    try:
        txt = resp["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(txt)
    except Exception as e:
        print("[gemini parse]", e, str(resp)[:200])
        return None


# ----------------------------------------------------------------- usda (macros)
def usda_lookup(name):
    key = cc.cfg("USDA_API_KEY")
    if not key:
        return None
    from urllib.parse import urlencode
    url = ("https://api.nal.usda.gov/fdc/v1/foods/search?"
           + urlencode({"query": name, "pageSize": 1, "api_key": key}))
    st, resp = cc.http_json(url)
    if st != 200 or not resp.get("foods"):
        return None
    f = resp["foods"][0]
    want = {1008: "cal", 1003: "protein", 1004: "fat", 1005: "carbs"}
    macros = {v: None for v in want.values()}
    for n in f.get("foodNutrients", []):
        nid = n.get("nutrientId")
        if nid in want:
            macros[want[nid]] = n.get("value")            # per 100 g
    return {"desc": (f.get("description") or name).lower(),
            "url": f"https://fdc.nal.usda.gov/food-details/{f.get('fdcId')}/nutrients",
            **macros}


# ----------------------------------------------------------------- db writes
def get_food_id(cur, name):
    cur.execute("SELECT id, calories, protein_g, carbs_g, fat_g FROM foods "
                "WHERE lower(name)=lower(%s) ORDER BY id LIMIT 1", (name,))
    return cur.fetchone()


def ensure_food(cur, name):
    row = get_food_id(cur, name)
    if row:
        return row
    m = usda_lookup(name)
    if not m or m["cal"] is None:
        return None
    cur.execute("""INSERT INTO foods (name, serving_size, serving_unit, calories, protein_g, carbs_g, fat_g, source_url)
                   VALUES (%s, 100, 'g', %s, %s, %s, %s, %s)
                   ON CONFLICT (name, brand, serving_size, serving_unit) DO NOTHING
                   RETURNING id, calories, protein_g, carbs_g, fat_g""",
                (m["desc"], m["cal"], m["protein"], m["carbs"], m["fat"], m["url"]))
    r = cur.fetchone()
    return r or get_food_id(cur, m["desc"])


def process(cur, msg_id, chat_id, text, token):
    parsed = parse_message(text)
    if parsed is None:
        cur.execute("UPDATE messages SET status='needs_review' WHERE id=%s", (msg_id,))
        reply(chat_id, "Couldn't read that one — logged for review.", token)
        return
    cur.execute("UPDATE messages SET parsed_data=%s WHERE id=%s", (json.dumps(parsed), msg_id))

    logged, review = [], False
    tot_cal = tot_p = 0.0
    for fd in parsed.get("foods", []):
        grams = fd.get("grams") or 0
        food = ensure_food(cur, fd.get("name", ""))
        if not food or not grams:
            review = True
            continue
        fid, cal, p, cbs, fat = food
        s = float(grams) / 100.0
        cal_l, p_l, c_l, f_l = (round(float(cal or 0)*s, 1), round(float(p or 0)*s, 1),
                                round(float(cbs or 0)*s, 1), round(float(fat or 0)*s, 1))
        cur.execute("""INSERT INTO food_log (food_id, quantity, calories, protein_g, carbs_g, fat_g, consumed_at, message_id)
                       VALUES (%s,%s,%s,%s,%s,%s, now(), %s)""",
                    (fid, grams, cal_l, p_l, c_l, f_l, msg_id))
        tot_cal += cal_l; tot_p += p_l
        logged.append(f"{fd['name']} {int(grams)}g")

    for sup in parsed.get("supplements", []):
        cur.execute("SELECT id FROM supplements WHERE lower(name)=lower(%s) LIMIT 1", (sup.get("name", ""),))
        r = cur.fetchone()
        if not r:
            cur.execute("INSERT INTO supplements (name) VALUES (%s) RETURNING id", (sup.get("name", "").lower(),))
            r = cur.fetchone()
        cur.execute("INSERT INTO supplement_log (supplement_id, quantity, taken_at, message_id) VALUES (%s,%s,now(),%s)",
                    (r[0], sup.get("quantity", 1), msg_id))
        logged.append(sup.get("name", "supplement"))

    b = parsed.get("body") or {}
    if any(b.get(k) is not None for k in ("weight_kg", "bodyfat_pct", "waist_in", "resting_hr")):
        cur.execute("""INSERT INTO body_metrics (weight_kg, bodyfat_pct, waist_in, resting_hr, recorded_at, message_id)
                       VALUES (%s,%s,%s,%s, now(), %s)""",
                    (b.get("weight_kg"), b.get("bodyfat_pct"), b.get("waist_in"), b.get("resting_hr"), msg_id))
        logged.append("bodyweight")

    if parsed.get("mentioned_lifting") and not parsed.get("foods"):
        reply(chat_id, "Log lifts in Hevy — they sync here automatically. This chat is for food, supplements & bodyweight.", token)

    status = "needs_review" if (review or ((parsed.get("mentioned_food")) and not logged)) else "parsed"
    cur.execute("UPDATE messages SET status=%s WHERE id=%s", (status, msg_id))

    # remaining-calories reply
    cur.execute("SELECT target_value FROM daily_plan WHERE item_type='goal' AND label='calories' LIMIT 1")
    goal = cur.fetchone()
    if logged:
        cur.execute("SELECT coalesce(sum(calories),0), coalesce(sum(protein_g),0) FROM food_log WHERE consumed_at::date = current_date")
        day_cal, day_p = cur.fetchone()
        tail = ""
        if goal and goal[0]:
            tail = f" {max(0, round(goal[0]-float(day_cal)))} kcal left today."
        reply(chat_id, f"Logged: {', '.join(logged)}. "
                       f"Today {round(float(day_cal))} kcal / {round(float(day_p))}g protein.{tail}", token)
    elif not parsed.get("mentioned_lifting"):
        reply(chat_id, "Nothing to log there.", token)


def main():
    token = cc.cfg("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[telegram_food] TELEGRAM_BOT_TOKEN not set — nothing to poll."); return
    with cc.db() as conn, conn.cursor() as cur:
        offset = cc.cfg("_") or None
        cur.execute("SELECT value FROM sync_state WHERE key='telegram_offset'")
        row = cur.fetchone()
        offset = int(row[0]) if row else None

        params = {"timeout": 0}
        if offset is not None:
            params["offset"] = offset + 1
        from urllib.parse import urlencode
        st, resp = cc.http_json(TG.format(tok=token, method="getUpdates") + "?" + urlencode(params))
        updates = resp.get("result", []) if isinstance(resp, dict) else []

        processed = 0
        max_uid = offset
        for u in updates:
            max_uid = u["update_id"]
            m = u.get("message") or u.get("edited_message")
            if not m:
                continue
            chat_id = m["chat"]["id"]
            kind, raw_text, transcript = "text", None, None
            if m.get("voice"):
                audio = tg_download(m["voice"]["file_id"], token)
                transcript = transcribe(audio) if audio else None
                kind = "voice"
            elif m.get("text"):
                raw_text = m["text"]; transcript = m["text"]
            else:
                continue  # ignore photos/docs for now

            status = "pending" if transcript else "needs_review"
            cur.execute("""INSERT INTO messages (source, chat_id, kind, raw_text, transcript, status, received_at)
                           VALUES ('telegram', %s, %s, %s, %s, %s, now()) RETURNING id""",
                        (chat_id, kind, raw_text, transcript, status))
            msg_id = cur.fetchone()[0]
            reply(chat_id, "Got it — logging now.", token)
            if not transcript:
                reply(chat_id, "Couldn't transcribe that voice note.", token)
                continue
            process(cur, msg_id, chat_id, transcript, token)
            processed += 1

        if max_uid is not None:
            cur.execute("""INSERT INTO sync_state (key, value) VALUES ('telegram_offset', %s)
                           ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value""", (str(max_uid),))
        conn.commit()
    print(f"[telegram_food] updates={len(updates)} processed={processed}")


if __name__ == "__main__":
    main()
