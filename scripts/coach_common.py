"""Shared helpers for the coaches + Telegram food pipeline.

Reads config from environment, falling back to ../.env for local runs:
  DATABASE_URL         Supabase Postgres (required)
  TELEGRAM_BOT_TOKEN   from BotFather (to send/receive)
  TELEGRAM_CHAT_ID     your chat id (where coaches message you)
  GEMINI_API_KEY       parsing brain (food/supp/body -> JSON)
  GROQ_API_KEY         voice-note transcription (optional; text works without it)
  USDA_API_KEY         FoodData Central (macros)
"""
import os
import re
import json
import pathlib
import urllib.request
import urllib.error

ROOT = pathlib.Path(__file__).resolve().parent.parent


def cfg(name, required=False):
    v = os.environ.get(name)
    if not v:
        envf = ROOT / ".env"
        if envf.exists():
            m = re.search(rf"^{name}=(.*)$", envf.read_text(encoding="utf-8-sig"), re.M)
            if m:
                v = m.group(1).strip()
    if required and not v:
        raise SystemExit(f"{name} not set")
    return v


def db():
    import psycopg
    return psycopg.connect(cfg("DATABASE_URL", required=True), connect_timeout=30)


def http_json(url, data=None, headers=None, method=None, timeout=60):
    body = None
    if data is not None:
        body = data if isinstance(data, (bytes, bytearray)) else json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw.strip() else {})
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode(errors="replace")}
    except urllib.error.URLError as e:
        return 0, {"error": str(e)}


def tg_send(text):
    """Send a Telegram message. If creds are missing, print instead (so dry-runs still work)."""
    token = cfg("TELEGRAM_BOT_TOKEN")
    chat = cfg("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("[no telegram creds — message below]\n" + text)
        return False
    st, resp = http_json(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data={"chat_id": chat, "text": text, "parse_mode": "HTML"},
        headers={"Content-Type": "application/json"},
    )
    if st != 200:
        print(f"[telegram send failed {st}] {resp}")
    return st == 200


def lin_slope_per_week(dates, values):
    """Least-squares slope (units/day * 7) of values against date ordinals. None if <2 points."""
    pts = [(d.toordinal(), float(v)) for d, v in zip(dates, values) if v is not None]
    n = len(pts)
    if n < 2:
        return None
    mx = sum(p[0] for p in pts) / n
    my = sum(p[1] for p in pts) / n
    denom = sum((p[0] - mx) ** 2 for p in pts)
    if denom == 0:
        return 0.0
    slope_day = sum((p[0] - mx) * (p[1] - my) for p in pts) / denom
    return slope_day * 7
