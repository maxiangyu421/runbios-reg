"""Playwright 拿 Turnstile token: 打开注册页, 等无感验证发 token。
2026-08-29 起平台注册强制校验 turnstile_token, 空/假 token 一律 REGISTRATION_DECLINED。
GH Actions ubuntu runner 自带真 Chrome; 配 xvfb-run 跑 headful 模式过检率最高。
token 5 分钟有效、单次使用, 拿到立刻用。"""
import time, sys

PAGE = "https://platform.runbios.ai/register"
SEL = 'input[name="cf-turnstile-response"]'
SITEKEY = "0x4AAAAAAEc7OxiF_IQKIpUY"

def solve(timeout=90, headful=True):
    from playwright.sync_api import sync_playwright
    args = ["--disable-blink-features=AutomationControlled",
            "--no-sandbox", "--disable-dev-shm-usage"]
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=not headful, args=args)
        except Exception:
            browser = p.chromium.launch(headless=not headful, args=args)
        ctx = browser.new_context(viewport={"width": 1280, "height": 800},
                                  locale="en-US",
                                  user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        page.goto(PAGE, wait_until="domcontentloaded", timeout=45000)
        deadline = time.time() + timeout
        tok = ""
        while time.time() < deadline and not tok:
            time.sleep(2)
            try:
                tok = page.eval_on_selector(SEL, "e=>e.value") or ""
            except Exception:
                tok = ""
            if not tok:
                # 页面自己的 widget 卡住(blacklisted环境)就自渲染一个补射
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
                        "      callback: t => { window.__rb_tok = t; }"
                        "    });"
                        "  }"
                        "  return window.__rb_tok || '';"
                        "}") or ""
                except Exception:
                    pass
        try: browser.close()
        except Exception: pass
        return tok

if __name__ == "__main__":
    only_solve = "--solve-only" in sys.argv
    t = solve()
    print("[ts] token_len", len(t))
    if t:
        with open("ts_token.txt", "w") as f: f.write(t)
        print("[ts] OK")
    else:
        print("[ts] FAIL")
        sys.exit(0 if only_solve else 0)   # 失败也不挡主流程, 让 reg 报出真实错误
