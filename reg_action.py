#!/usr/bin/env python3
"""GitHub Actions 里跑的注册脚本: 注册新号 -> base64 混淆后追加到 Gist accounts.json"""
import json, os, re, sys, time, random, string, base64
import urllib.request as U

BASE = "https://platform.runbios.ai"
TM = "https://api.tempmail.lol"
GIST_TOKEN = os.environ["GIST_TOKEN"]
GIST_ID = os.environ["GIST_ID"]
GIST_FILE = "accounts.json"

def jreq(url, method="GET", data=None, hdrs=None, timeout=30):
    h = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0 Chrome/131"}
    if hdrs: h.update(hdrs)
    body = json.dumps(data).encode() if data is not None else None
    r = U.Request(url, data=body, headers=h, method=method)
    try:
        with U.urlopen(r, timeout=timeout) as res:
            return res.status, json.loads(res.read().decode())
    except Exception as e:
        try: return getattr(e, "code", -1) or -1, json.loads(e.read().decode())
        except Exception: return -1, {"error": str(e)}

def tm_generate():
    for i in range(5):
        st, d = jreq(TM + "/generate")
        if d.get("address") and d.get("token"):
            print("[box]", d["address"])
            return d
        print(f"[box] generate 失败 {i+1}/5:", str(d)[:60])
        time.sleep(15)
    return None

def wait_otp(token, minutes=6):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(8)
        st, d = jreq(f"{TM}/auth/{token}")
        for m in (d.get("email") or []):
            mm = re.search(r"\b(\d{6})\b", m.get("subject", "") + " " + (m.get("body") or ""))
            if mm: return mm.group(1)
    return None

def gist_read():
    st, d = jreq(f"https://api.github.com/gists/{GIST_ID}",
                 hdrs={"Authorization": "token " + GIST_TOKEN})
    raw = (d.get("files") or {}).get(GIST_FILE, {}).get("content") or ""
    try:
        return json.loads(base64.b64decode(raw).decode())
    except Exception:
        return []

def gist_write(accounts):
    blob = base64.b64encode(json.dumps(accounts, ensure_ascii=False).encode()).decode()
    st, d = jreq(f"https://api.github.com/gists/{GIST_ID}", "PATCH",
                 {"files": {GIST_FILE: {"content": blob}}},
                 {"Authorization": "token " + GIST_TOKEN})
    print("[gist] write", st)

def register_one():
    box = tm_generate()
    if not box:
        print("[reg] tempmail 不可用"); return None
    r8 = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    pwd = "Rb" + "".join(random.choices(string.ascii_letters + string.digits, k=10)) + "!7"
    st, resp = jreq(BASE + "/api/auth/register", "POST",
                    {"email": box["address"], "password": pwd, "name": "nb_" + r8,
                     "website": "", "turnstile_token": ""})
    if st != 201:
        print("[reg] 失败:", st, str(resp)[:120]); return None
    print("[reg] 已提交, 等OTP…")
    otp = wait_otp(box["token"])
    if not otp:
        print("[reg] OTP 超时"); return None
    fp = "".join(random.choices("0123456789abcdef", k=64))
    st, ver = jreq(BASE + "/api/auth/verify-otp", "POST",
                   {"email": box["address"], "otp": otp, "device_fp": fp})
    tok = (ver.get("tokens") or {}) if isinstance(ver, dict) else {}
    if not tok.get("access_token"):
        print("[reg] verify 失败:", str(ver)[:120]); return None
    acc = tok["access_token"]
    # workspace
    st, ws = jreq(BASE + "/api/workspaces", hdrs={"Authorization": "Bearer " + acc})
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", json.dumps(ws))
    wid = m.group(0) if m else None
    # 余额
    bal = None
    st, w = jreq(BASE + "/api/billing/wallet", hdrs={"Authorization": "Bearer " + acc})
    if st == 200:
        try: bal = float(w.get("available_balance_dollars") or 0)
        except Exception: pass
    return {"email": box["address"], "password": pwd, "access_token": acc,
            "refresh_token": tok.get("refresh_token"), "fp": fp, "workspace_id": wid,
            "balance": bal, "registered_at": int(time.time()), "active": True, "error": ""}

if __name__ == "__main__":
    entry = register_one()
    if not entry:
        sys.exit(1)
    print(f"[reg] ✅ {entry['email']} bal={entry.get('balance')}")
    accounts = gist_read()
    # 去重
    if any(a.get("email") == entry["email"] for a in accounts):
        print("[gist] 已存在, 跳过")
        sys.exit(0)
    accounts.append(entry)
    if len(accounts) > 12:      # 只保留最近12个
        accounts = accounts[-12:]
    gist_write(accounts)
    print("[gist] 池已更新, 共", len(accounts))
