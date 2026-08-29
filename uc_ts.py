"""SeleniumBase UC Mode + 住宅代理: OS 级点击对照实验。
TS_PROXY 未设时从 proxies.txt 轮换(最多4个), 每个代理内: 静默打开 -> click_captcha -> 读 token。"""
import sys, time, os, random

PAGE = "https://platform.runbios.ai/register"

def load_proxies():
    try:
        return [l.strip() for l in open("proxies.txt") if l.strip() and not l.startswith("#")]
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
        print("[uc] 初始 token_len", len(tok))
        for attempt in range(1, 4):
            if tok: break
            for fn in ("uc_gui_click_captcha", "uc_gui_handle_captcha"):
                try:
                    getattr(sb, fn)()
                    print("[uc] attempt %d %s() OK" % (attempt, fn))
                    break
                except Exception as e:
                    print("[uc] attempt %d %s() err: %s" % (attempt, fn, str(e)[:90]))
            time.sleep(8)
            tok = read_token(sb)
            print("[uc] attempt %d token_len %d" % (attempt, len(tok)))
        if tok:
            with open("ts_token.txt", "w") as f: f.write(tok)
            print("[uc] OK via", px)
        else:
            try: sb.save_screenshot("uc_debug.png")
            except Exception: pass
        return tok

if __name__ == "__main__":
    px_list = ([os.environ["TS_PROXY"].split("://",1)[1]] if os.environ.get("TS_PROXY")
               else random.sample(load_proxies(), min(3, len(load_proxies()))))
    print("[uc] 代理队列:", px_list)
    got = ""
    for px in px_list:
        print("[uc] === 代理", px, "===")
        try:
            got = try_one("socks5://" + px)
        except Exception as e:
            print("[uc] exc:", str(e)[:120])
        if got: break
    print("[uc] 最终:", "OK" if got else "FAIL")
    sys.exit(0)
