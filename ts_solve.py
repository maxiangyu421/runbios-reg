"""Turnstile token 获取 v5: patchright + 住宅 SOCKS5 代理。
TS_PROXY 环境变量形如 socks5://1.2.3.4:4145 (chromium socks5://=本地解析, 发 IP ATYP, 实测可用)。
浏览器与后续注册 API 必须走同一出口 IP(token 可能绑解题 IP), 由 reg_action 统一选定并注入 TS_PROXY。
MITM 代理会重签证书 -> ignore_https_errors + --ignore-certificate-errors(账号为一次性, 用户已接受)。"""
import os, time, sys

PAGE = "https://platform.runbios.ai/register"
SEL = 'input[name="cf-turnstile-response"]'
SITEKEY = "0x4AAAAAAEc7OxiF_IQKIpUY"

def _launch_args(proxy):
    args = ["--disable-blink-features=AutomationControlled",
            "--no-sandbox", "--disable-dev-shm-usage",
            "--window-size=1280,800",
            "--ignore-certificate-errors"]
    if proxy:
        args.append("--proxy-server=" + proxy)
    return args

def _cf_frame_states(page):
    out = []
    try:
        for fr in page.frames:
            if "challenges.cloudflare.com" in (fr.url or ""):
                try:
                    txt = fr.evaluate("() => document.body ? document.body.innerText.slice(0,150) : ''")
                except Exception as e:
                    txt = "<eval err %s>" % str(e)[:40]
                out.append((fr.url[:70], txt.replace("\n", " | ")))
    except Exception:
        pass
    return out

def _one_attempt(p, headful, timeout, proxy):
    try:
        browser = p.chromium.launch(channel="chrome", headless=not headful,
                                    args=_launch_args(proxy),
                                    ignore_default_args=["--enable-automation"])
    except Exception:
        browser = p.chromium.launch(headless=not headful, args=_launch_args(proxy))
    try:
        ctx = browser.new_context(viewport={"width": 1280, "height": 800}, locale="en-US",
                                  ignore_https_errors=True)
        page = ctx.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            "window.chrome={runtime:{}};")
        page.goto(PAGE, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        for xy in ((400, 300), (700, 500), (900, 380)):
            page.mouse.move(*xy, steps=8); time.sleep(0.4)
        page.mouse.wheel(0, 120); time.sleep(0.5)
        deadline = time.time() + timeout
        clicks = 0
        last_click = 0.0
        while time.time() < deadline:
            time.sleep(2)
            tok = ""
            try:
                tok = page.eval_on_selector(SEL, "e=>e.value") or ""
            except Exception:
                pass
            if not tok:
                try:
                    tok = page.evaluate(
                        "() => {"
                        "  if (window.__rb_tok) return window.__rb_tok;"
                        "  if (!window.turnstile) return '';"
                        "  if (!window.__rb_wid) {"
                        "    const d = document.createElement('div');"
                        "    document.body.appendChild(d);"
                        "    window.__rb_wid = window.turnstile.render(d, {"
                        "      sitekey: '" + SITEKEY + "',"
                        "      callback: t => { window.__rb_tok = t; },"
                        "      'error-callback': c => { window.__rb_err = c; }"
                        "    });"
                        "  }"
                        "  return window.__rb_tok || '';"
                        "}") or ""
                    err = page.evaluate("() => window.__rb_err || ''")
                    if err: print("[ts] widget error-callback:", err)
                except Exception:
                    pass
            if tok:
                return tok
            try:
                if clicks < 6 and time.time() - last_click > 8:
                    frs = page.query_selector_all('iframe[src*="challenges.cloudflare.com"]')
                    for fr in frs:
                        box = fr.bounding_box()
                        if box and box["width"] > 50:
                            if clicks == 0:
                                print("[ts] 发现交互复选框 @", int(box["x"]), int(box["y"]))
                            page.mouse.click(box["x"] + 28, box["y"] + box["height"] / 2)
                            clicks += 1
                            last_click = time.time()
                            print(f"[ts] 第{clicks}次点击")
                            time.sleep(2)
                            break
            except Exception as e:
                print("[ts] click err:", str(e)[:80])
        for url, txt in _cf_frame_states(page):
            print(f"[ts] frame {url} => {txt}")
        page.screenshot(path="ts_debug.png")
        print("[ts] 超时, 已留截图")
        return ""
    finally:
        try: browser.close()
        except Exception: pass

def solve(timeout=70, attempts=3, headful=True):
    proxy = os.environ.get("TS_PROXY", "")
    print("[ts] proxy:", proxy or "(none)")
    try:
        from patchright.sync_api import sync_playwright
        eng = "patchright"
    except ImportError:
        from playwright.sync_api import sync_playwright
        eng = "playwright"
    print("[ts] engine:", eng, "headful:", headful)
    with sync_playwright() as p:
        for i in range(1, attempts + 1):
            print(f"[ts] 第 {i}/{attempts} 次尝试…")
            try:
                tok = _one_attempt(p, headful, timeout, proxy)
            except Exception as e:
                print("[ts] attempt exc:", str(e)[:150]); tok = ""
            if tok:
                print("[ts] GOT len", len(tok))
                return tok
            time.sleep(3)
    return ""

if __name__ == "__main__":
    t = solve()
    print("[ts] token_len", len(t))
    if t:
        with open("ts_token.txt", "w") as f: f.write(t)
        print("[ts] OK")
    else:
        print("[ts] FAIL")
    sys.exit(0)
