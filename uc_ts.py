"""SeleniumBase UC Mode + 住宅代理轮换 (2026-08-29 实测成功路线)。
成功签名: uc_gui_click_captcha OS 级点击 + Cox 家宽出口, 第二个代理即出 token(773字节)。
patchright/CDP 点击在同类 IP 上被 CF 识破(对照实验), 勿换回去。
成功后写 ts_token.txt + ts_proxy.txt(token 5分钟有效单次用, 注册必须走同一代理)。"""
import sys, time, os, random

PAGE = "https://platform.runbios.ai/register"

def load_proxies():
    try:
        return [l.strip() for l in open("proxies.txt") if l.strip() and not l.startswith("#")]
    except FileNotFoundError:
        return []

def load_good():
    try:
        return [l.strip() for l in open("good_proxy.txt") if l.strip()]
    except FileNotFoundError:
        return []

def read_token(sb):
    try:
        return sb.execute_script(
            'var i=document.querySelector(\'input[name="cf-turnstile-response"]\');'
            "return i ? i.value : '';") or ""
    except Exception:
        return ""

def try_one(px):
    from seleniumbase import SB
    with SB(uc=True, locale="en", proxy=px,
            chromium_arg="--ignore-certificate-errors") as sb:
        sb.uc_open_with_reconnect(PAGE, reconnect_time=6)
        time.sleep(10)
        tok = read_token(sb)
        print("[uc] 初始 token_len", len(tok), flush=True)
        # 坏代理试再多轮也解不出(实测), 2 轮就换: 每个死代理省 ~12s
        for attempt in range(1, 3):
            if tok: break
            for fn in ("uc_gui_click_captcha", "uc_gui_handle_captcha"):
                try:
                    getattr(sb, fn)()
                    print("[uc] attempt %d %s() OK" % (attempt, fn), flush=True)
                    break
                except Exception as e:
                    print("[uc] attempt %d %s() err: %s" % (attempt, fn, str(e)[:90]), flush=True)
            time.sleep(8)
            tok = read_token(sb)
            print("[uc] attempt %d token_len %d" % (attempt, len(tok)), flush=True)
        if tok:
            with open("ts_token.txt", "w") as f: f.write(tok)
            with open("ts_proxy.txt", "w") as f: f.write(px)
            print("[uc] OK via", px, flush=True)
        else:
            try: sb.save_screenshot("uc_debug.png")
            except Exception: pass
        return tok

if __name__ == "__main__":
    single = os.environ.get("SINGLE_PROXY", "")   # ip-sift 阶段2: 只测这一个
    if single:
        px_list = [single.replace("socks5://", "")]
    else:
        pl = load_proxies()
        pl = load_proxies()
        # 优先用上次成功的代理(Gist good_proxy.txt, workflow 已下载到本地): 实测坏代理一轮要烧 35s,
        # 把最近一次能过盾的代理置顶可把解盾从 3~4 分钟压到 ~45s。读不到再退回随机。
        good = [p for p in load_good() if p in pl]
        rest = [p for p in pl if p not in good]
        random.shuffle(rest)
        px_list = good + rest
        px_list = px_list[:4]
    print("[uc] 代理队列:", px_list, flush=True)
    got = ""
    for px in px_list:
        print("[uc] === 代理", px, "===", flush=True)
        try:
            got = try_one("socks5://" + px)
        except Exception as e:
            print("[uc] exc:", str(e)[:120], flush=True)
        if got: break
    print("[uc] 最终:", "OK" if got else "FAIL", flush=True)
    sys.exit(0)
