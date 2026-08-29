"""SeleniumBase UC Mode v2: 静默等待 + OS 级点击。
v1 失败教训: 每 2s execute_script 轮询 token 会不断重连 webdriver,
CF 持续看到自动化协议信号 -> 断开失效。
v2: 打开后完全静默, 只靠 uc_gui_click_captcha(断开+pyautogui 点击+重连),
之后才读一次 token; 每轮之间也保持静默。"""
import sys, time

PAGE = "https://platform.runbios.ai/register"

def read_token(sb):
    try:
        return sb.execute_script(
            'var i=document.querySelector(\'input[name="cf-turnstile-response"]\');'
            "return i ? i.value : '';") or ""
    except Exception:
        return ""

def main():
    from seleniumbase import SB
    with SB(uc=True, locale="en", xvfb=int("--headless-host" in sys.argv)) as sb:
        sb.uc_open_with_reconnect(PAGE, reconnect_time=6)
        time.sleep(10)                       # 完全静默: 让 widget 自己初始化/无感通过
        tok = read_token(sb)
        print("[uc] 初始 token_len", len(tok))
        for attempt in range(1, 5):
            if tok:
                break
            # uc_gui_click_captcha: 内部先断开 driver -> pyautogui 找到复选框并 OS 级点击 -> 重连
            clicked = False
            for fn in ("uc_gui_click_captcha", "uc_gui_handle_captcha"):
                try:
                    getattr(sb, fn)()
                    print("[uc] attempt %d %s() OK" % (attempt, fn))
                    clicked = True
                    break
                except Exception as e:
                    print("[uc] attempt %d %s() err: %s" % (attempt, fn, str(e)[:100]))
            time.sleep(8)                    # 静默等 token 回调
            tok = read_token(sb)
            print("[uc] attempt %d token_len %d" % (attempt, len(tok)))
        if tok:
            with open("ts_token.txt", "w") as f:
                f.write(tok)
            print("[uc] OK")
        else:
            try:
                sb.save_screenshot("uc_debug.png")
                print("[uc] debug screenshot saved")
            except Exception:
                pass
            print("[uc] FAIL")
    sys.exit(0)

if __name__ == "__main__":
    main()
