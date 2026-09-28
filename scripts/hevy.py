"""Shared Hevy API helper. Reads key from .env, never prints it.
Base: https://api.hevyapp.com/v1  Header: api-key: <key>
All weights sent to Hevy are in kilograms.
"""
import json, os, re, time, urllib.request, urllib.error, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(exist_ok=True)
BASE = "https://api.hevyapp.com/v1"

def _key():
    env = (ROOT / ".env").read_text(encoding="utf-8-sig", errors="replace")
    m = re.search(r"HEVY_API_KEY=(.*)", env)
    k = m.group(1).strip() if m else ""
    if not k or k == "PASTE_YOUR_KEY_HERE":
        raise SystemExit("HEVY_API_KEY not set in .env")
    return k

KEY = _key()

def request(method, path, params=None, body=None, retries=3):
    url = BASE + path
    if params:
        from urllib.parse import urlencode
        url += "?" + urlencode(params)
    data = json.dumps(body).encode() if body is not None else None
    headers = {"api-key": KEY, "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode()
                return r.status, (json.loads(raw) if raw.strip() else {})
        except urllib.error.HTTPError as e:
            body_txt = e.read().decode(errors="replace")
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return e.code, {"error": body_txt}
        except urllib.error.URLError as e:
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            return 0, {"error": str(e)}
    return 0, {"error": "unreachable"}

def save(name, obj):
    p = DATA / f"{name}.json"
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p

def get(path, params=None):
    return request("GET", path, params=params)

LB_TO_KG = 0.45359237
def lb_to_kg(lb):
    return lb * LB_TO_KG
