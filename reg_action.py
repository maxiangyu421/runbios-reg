#!/usr/bin/env python3
"""GitHub Actions 注册脚本 v2 (2026-08-29):
平台注册强制 Turnstile 校验后, 注册流量改走住宅 SOCKS5 代理。
安全边界(重要): 只有 platform.runbios.ai 的请求走代理(一次性账密/OTP, MITM 可接受);
tempmail.lol / mail.tm 与 api.github.com 一律直连 —— GIST_TOKEN 等真实凭证绝不经过代理。
代理从 proxies.txt 随机选一个, 注册与浏览器解 token 用同一个出口(token 可能绑 IP)。
2026-09-11: 平台 09-10 起接临时邮箱黑名单(tempmail.lol 全系域名被封, 含 26ai.art),
邮箱源改为 mail.tm 优先 + tempmail.lol 兜底; 邮箱生成挪到过盾之后(省配额)。"""
import json, os, re, sys, time, random, string, base64, socket, struct, ssl
import urllib.request as U

BASE = "https://platform.runbios.ai"
TM = "https://api.tempmail.lol"
MTM = "https://api.mail.tm"
# 2026-09-11: rb-mail = 自建 CF worker 邮箱(xinyu1.ggff.net 邮件路由 -> worker D1),
# 域名不在临时邮箱黑名单。凭证走 repo secrets(公开仓库, 不能硬编码)。mail.tm/tempmail.lol 降为兜底。
RB_URL = os.environ.get("RB_MAIL_URL", "").rstrip("/")
RB_SITE = os.environ.get("RB_MAIL_SITE", "")
RB_ADMIN = os.environ.get("RB_MAIL_ADMIN", "")
RB_DOMAINS = ["xinyu1.ggff.net", "xinapi.bond", "xinfr.cyou"]  # 09-12 扩域名轮换
GIST_TOKEN = os.environ["GIST_TOKEN"]
GIST_ID = os.environ["GIST_ID"]
GIST_FILE = "accounts.json"

# ---------------- 代理选择(轮换) ----------------
def load_proxies():
    try:
        return [l.strip() for l in open("proxies.txt") if l.strip() and not l.startswith("#")]
    except FileNotFoundError:
        return []

PX_LIST = load_proxies()
PROXY = os.environ.get("TS_PROXY") or ("socks5://" + random.choice(PX_LIST) if PX_LIST else "")
PX_HOST = PX_PORT = None
if PROXY:
    _hp = PROXY.split("://", 1)[1]
    PX_HOST, PX_PORT = _hp.split(":")
    PX_PORT = int(PX_PORT)
os.environ["TS_PROXY"] = PROXY   # 传给 ts_solve(浏览器同出口)

def set_proxy(px):
    """轮换代理: 同步改 jreq_px 的出口与浏览器的 TS_PROXY(保证 token 与注册同 IP)。"""
    global PROXY, PX_HOST, PX_PORT
    PROXY = px
    if px:
        _hp = px.split("://", 1)[1]
        PX_HOST, PX_PORT = _hp.split(":")
        PX_PORT = int(PX_PORT)
    os.environ["TS_PROXY"] = px

# ---------------- 通用请求 ----------------
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

# ---------------- SOCKS5 隧道(仅 platform.runbios.ai 用) ----------------
def socks5_connect(dst_host, dst_port, timeout=15):
    if not PX_HOST:
        raise RuntimeError("no proxy")
    dst_ip = socket.gethostbyname(dst_host)
    s = socket.create_connection((PX_HOST, PX_PORT), timeout=timeout)
    s.sendall(b"\x05\x01\x00")
    r = s.recv(2)
    if r != b"\x05\x00":
        s.close(); raise RuntimeError("socks5 greeting " + r.hex())
    s.sendall(b"\x05\x01\x00\x01" + socket.inet_aton(dst_ip) + struct.pack(">H", dst_port))
    r = s.recv(64)
    if len(r) < 2 or r[1] != 0:
        s.close(); raise RuntimeError("socks5 connect denied code=%d" % (r[1] if len(r) > 1 else -1))
    return s

def jreq_px(url, method="POST", data=None, hdrs=None, timeout=30):
    """platform.runbios.ai 专用: 走 SOCKS5 住宅出口 + 忽略代理的重签证书(用户已接受 MITM)。"""
    from urllib.parse import urlparse
    u = urlparse(url)
    host, path = u.hostname, (u.path or "/") + (("?" + u.query) if u.query else "")
    h = {"Content-Type": "application/json",
         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
         "Origin": BASE, "Referer": BASE + "/register"}
    if hdrs: h.update(hdrs)
    body = json.dumps(data).encode() if data is not None else None
    try:
        raw = socks5_connect(host, 443, timeout)
        ctx = ssl._create_unverified_context()
        tls = ctx.wrap_socket(raw, server_hostname=host)
        tls.sendall(("%s %s HTTP/1.1\r\nHost: %s\r\n" % (method, path, host)).encode()
                    + b"".join(("%s: %s\r\n" % kv).encode() for kv in h.items())
                    + (b"Content-Length: %d\r\n" % len(body) if body else b"")
                    + b"Connection: close\r\n\r\n" + (body or b""))
        tls.settimeout(timeout)
        resp = b""
        while len(resp) < 200000:
            c = tls.recv(65536)
            if not c: break
            resp += c
        tls.close()
        head, _, payload = resp.partition(b"\r\n\r\n")
        status = int(head.splitlines()[0].split()[1])
        try: return status, json.loads(payload.decode())
        except Exception: return status, {"raw": payload[:300].decode("utf-8", "ignore")}
    except Exception as e:
        return -1, {"error": str(e)[:150]}

def PX():
    return jreq_px if PROXY else jreq

# ---------------- tempmail.lol(直连, 不走代理) ----------------
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

# ---------------- rb-mail(自建 CF 邮箱, 直连; 2026-09-11 主力) ----------------
def rb_generate():
    """worker admin API 建地址, 返回 jwt; 失败/未配置返回 None 走兜底。"""
    if not (RB_URL and RB_SITE and RB_ADMIN):
        print("[box] rb-mail secrets 未配置, 跳过"); return None
    name = "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    st, d = jreq(RB_URL + "/admin/new_address", "POST",
                 {"name": name, "domain": random.choice(RB_DOMAINS), "enablePrefix": False},
                 {"x-admin-auth": RB_ADMIN, "x-custom-auth": RB_SITE})
    if not (d or {}).get("jwt"):
        print("[box] rb-mail 建址失败", st, str(d)[:80]); return None
    print("[box]", d["address"], "(rb-mail)")
    return {"address": d["address"], "jwt": d["jwt"], "rb": True}

def _mail_text(raw):
    """RFC822 -> Subject + 正文文本(raw_mails 只有 raw 全文, 头部数字多, 必须解析后再找码)。"""
    try:
        from email import policy
        import email as _em
        msg = _em.message_from_string(raw, policy=policy.default)
        parts = [str(msg.get("Subject") or "")]
        body = msg.get_body(preferencelist=("plain", "html"))
        if body is not None:
            parts.append(body.get_content())
        return " ".join(parts)
    except Exception:
        return raw

def rb_wait_otp(jwt, minutes=6):
    ah = {"Authorization": "Bearer " + jwt, "x-custom-auth": RB_SITE}
    seen, n = set(), 0
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        time.sleep(8)
        st, d = jreq(RB_URL + "/api/mails?limit=20&offset=0", hdrs=ah)
        for m in ((d or {}).get("results") or []):
            if m.get("id") in seen: continue
            seen.add(m.get("id"))
            mm = re.search(r"\b(\d{6})\b", _mail_text(m.get("raw") or ""))
            if mm: return mm.group(1)
        n += 1
        if n % 4 == 0: print("[box] 等 OTP", int(deadline - time.time()), "s…")
    return None

# ---------------- mail.tm(直连, 不走代理; 2026-09-11 降为兜底) ----------------
def mtm_generate():
    """mail.tm: 建账号收信。域名池动态(当前 1 个), 直连。"""
    st, d = jreq(MTM + "/domains?page=1")
    doms = [x.get("domain") for x in ((d or {}).get("hydra:member") or []) if x.get("isActive")]
    if not doms:
        print("[box] mail.tm 无可用域名:", str(d)[:80]); return None
    addr = "".join(random.choices(string.ascii_lowercase + string.digits, k=12)) + "@" + doms[0]
    pwd = "Rb" + "".join(random.choices(string.ascii_letters + string.digits, k=10)) + "!7"
    st, r = jreq(MTM + "/accounts", "POST", {"address": addr, "password": pwd})
    if st not in (200, 201):
        print("[box] mail.tm 建号失败", st, str(r)[:80]); return None
    st, r = jreq(MTM + "/token", "POST", {"address": addr, "password": pwd})
    jwt = (r or {}).get("token") or ""
    if not jwt:
        print("[box] mail.tm 取token失败", str(r)[:80]); return None
    print("[box]", addr)
    return {"address": addr, "token": jwt, "mtm": True}

def mtm_wait_otp(jwt, minutes=6):
    ah = {"Authorization": "Bearer " + jwt}
    deadline = time.time() + minutes * 60
    seen = set()
    while time.time() < deadline:
        time.sleep(8)
        st, d = jreq(MTM + "/messages?page=1", hdrs=ah)
        for m in ((d or {}).get("hydra:member") or []):
            if m.get("id") in seen: continue
            seen.add(m.get("id"))
            st2, full = jreq(MTM + "/messages/" + str(m.get("id")), hdrs=ah)
            txt = " ".join([str(full.get("subject") or ""), str(full.get("intro") or ""),
                            str(full.get("text") or ""), " ".join(full.get("html") or [])])
            mm = re.search(r"\b(\d{6})\b", txt)
            if mm: return mm.group(1)
    return None

# ---------------- Gist(直连, 凭证不过代理) ----------------
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

def gist_write_good_proxy(px):
    """记录本次成功过盾的代理(裸 host:port), 下次 run 置顶首选 —— 省掉坏代理试错(每轮 ~30s)。"""
    try:
        host = px.split("://", 1)[1] if "://" in px else px
        st, d = jreq(f"https://api.github.com/gists/{GIST_ID}", "PATCH",
                     {"files": {"good_proxy.txt": {"content": host}}},
                     {"Authorization": "token " + GIST_TOKEN})
        print("[gist] good_proxy <-", host, st)
    except Exception as e:
        print("[gist] good_proxy 写入失败:", str(e)[:100])

# ---------------- 注册主流程 ----------------
def get_turnstile_token():
    """UC 模式(子进程隔离, seleniumbase 全局态不污染本进程)解 token;
    成功后读回 ts_proxy.txt 并 set_proxy, 保证注册 API 与解题同出口 IP。"""
    import subprocess
    for f in ("ts_token.txt", "ts_proxy.txt"):
        if os.path.exists(f):
            os.remove(f)
    try:
        subprocess.run([sys.executable, "uc_ts.py"], timeout=560, check=False)
    except Exception as e:
        print("[ts] uc 子进程异常:", str(e)[:120])
    tok = px_used = ""
    if os.path.exists("ts_token.txt"):
        tok = open("ts_token.txt").read().strip()
    if os.path.exists("ts_proxy.txt"):
        px_used = open("ts_proxy.txt").read().strip()
    if tok and px_used:
        if "://" in px_used:
            px_used = px_used.split("://", 1)[1]
        set_proxy("socks5://" + px_used)
        print("[ts] token_len", len(tok), "via", PROXY)
    else:
        print("[ts] token_len 0")
    return tok

def register_one():
    # 09-11: 先过盾再生成邮箱(tempmail 时代是先拿邮箱, 白耗配额)
    ts_token = get_turnstile_token()
    if not ts_token:
        print("[reg] 无 turnstile token, 跳过本次注册(省邮箱配额)")
        return None
    box = rb_generate() or mtm_generate() or tm_generate()
    if not box:
        print("[reg] 邮箱源不可用"); return None
    r8 = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    pwd = "Rb" + "".join(random.choices(string.ascii_letters + string.digits, k=10)) + "!7"
    px = PX()
    st, resp = px(BASE + "/api/auth/register", "POST",
                  {"email": box["address"], "password": pwd, "name": "nb_" + r8,
                   "website": "", "turnstile_token": ts_token})
    if st != 201:
        print("[reg] 失败:", st, str(resp)[:150]); return None
    print("[reg] 已提交, 等OTP…")
    otp = (rb_wait_otp(box["jwt"]) if box.get("rb")
           else mtm_wait_otp(box["token"]) if box.get("mtm") else wait_otp(box["token"]))
    if not otp:
        print("[reg] OTP 超时"); return None
    fp = "".join(random.choices("0123456789abcdef", k=64))
    st, ver = px(BASE + "/api/auth/verify-otp", "POST",
                 {"email": box["address"], "otp": otp, "device_fp": fp})
    tok = (ver.get("tokens") or {}) if isinstance(ver, dict) else {}
    if not tok.get("access_token"):
        print("[reg] verify 失败:", str(ver)[:150]); return None
    acc = tok["access_token"]
    ah = {"Authorization": "Bearer " + acc}
    st, ws = px(BASE + "/api/workspaces", "GET", None, ah)
    m = re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", json.dumps(ws))
    wid = m.group(0) if m else None
    bal = None
    st, w = px(BASE + "/api/billing/wallet", "GET", None, ah)
    if st == 200:
        try: bal = float(w.get("balance_dollars") or w.get("available_balance_dollars") or 0)
        except Exception: pass
    return {"email": box["address"], "password": pwd, "access_token": acc,
            "refresh_token": tok.get("refresh_token"), "fp": fp, "workspace_id": wid,
            "balance": bal, "registered_at": int(time.time()), "active": True, "error": ""}

if __name__ == "__main__":
    print("[px] 代理池:", len(PX_LIST), "个")
    if "--solve-only" in sys.argv:
        import ts_solve
        ok = False
        for px in PX_LIST[:4]:
            set_proxy("socks5://" + px)
            print("[px] 换代理 ->", PROXY)
            try:
                tok = ts_solve.solve()   # solve() 每次读 TS_PROXY, 无需 reload
            except Exception as e:
                print("[ts] solver 异常:", str(e)[:150]); tok = ""
            print("[ts] token_len", len(tok))
            if tok:
                with open("ts_token.txt", "w") as f: f.write(tok)
                print("[ts] OK via", PROXY)
                ok = True
                break
        if not ok:
            print("[ts] FAIL(全部代理)")
        sys.exit(0)
    # 完整注册: 逐代理尝试(解题+注册同 IP)
    entry = None
    for px in PX_LIST[:4]:
        set_proxy("socks5://" + px)
        print("[px] 换代理 ->", PROXY)
        entry = register_one()
        if entry:
            break
    if not entry:
        sys.exit(1)
    print(f"[reg] ✅ {entry['email']} bal={entry.get('balance')}")
    gist_write_good_proxy(PROXY)   # 本次真正过盾+注册成功的出口, 供下次置顶
    accounts = gist_read()
    if any(a.get("email") == entry["email"] for a in accounts):
        print("[gist] 已存在, 跳过")
        sys.exit(0)
    accounts.append(entry)
    if len(accounts) > 12:
        accounts = accounts[-12:]
    gist_write(accounts)
    print("[gist] 池已更新, 共", len(accounts))
