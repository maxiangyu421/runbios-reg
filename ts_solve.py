"""Turnstile token 获取 v2:
- patchright(反检测 playwright 补丁)优先, 装了 playwright 就退回
- headful + xvfb; 三次尝试; 检测到交互复选框就模拟点击
- 失败留截图 ts_debug_N.png 供诊断
token 5 分钟有效、单次使用。"""
import time, sys, os

PAGE = "https://platform.runbios.ai/register"
SEL = 'input[name="cf-turnstile-response"]'
SITEKEY = "0x4AAAAAAEc7OxiF_IQKIpUY"

def _launch(p, headful):
    args = ["--disable-blink-features=AutomationControlled",
            "--no-sandbox", "--disable-dev-shm-usage",
            "--window-size=1280,800"]
    try:
        return p.chromium.launch(channel="chrome", headless=not headful, args=args,
                                 ignore_default_args=["--enable-automation"])
    except Exception:
        return p.chromium.launch(headless=not headful, args=args)

def _cf_frame_states(page):
    """钻进 cloudflare iframe 读状态文字(交叉诊断用)"""
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

def _one_attempt(p, headful, timeout):
    browser = _launch(p, headful)
    try:
        ctx = browser.new_context(viewport={"width": 1280, "height": 800}, locale="en-US")
        page = ctx.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            "window.chrome={runtime:{}};")
        page.goto(PAGE, wait_until="domcontentloaded", timeout=45000)
        time.sleep(3)
        # 拟人: 随机晃一下鼠标 + 滚动
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
            # 交互式复选框: 找 cloudflare iframe, 反复点(每次点击间隔 8s, 最多 5 次)
            try:
                if clicks < 5 and time.time() - last_click > 8:
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
        print("[ts] 超时, 已留截图 ts_debug.png")
        return ""
    finally:
        try: browser.close()
        except Exception: pass

def solve(timeout=60, attempts=3, headful=True):
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
                tok = _one_attempt(p, headful, timeout)
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
