"""SeleniumBase UC Mode 拿 Turnstile token（借鉴 cloudflare-bypass-2026 的思路）:
- uc_open_with_reconnect: 打开页面瞬间断开 webdriver（CF 看到的是无主浏览器）
- uc_gui_handle_captcha: 检测到 Turnstile 复选框时用 pyautogui 发 OS 级点击
- 轮询 input[name=cf-turnstile-response] 拿 token
在 CI 上用 xvfb-run 提供虚拟显示。"""
import sys, time

PAGE = "https://platform.runbios.ai/register"

def main():
    from seleniumbase import SB
    deadline_total = time.time() + 150
    with SB(uc=True, locale="en") as sb:
        sb.uc_open_with_reconnect(PAGE, reconnect_time=4)
        tok = ""
        while time.time() < deadline_total and not tok:
            time.sleep(2)
            try:
                tok = sb.execute_script(
                    'var i=document.querySelector(\'input[name="cf-turnstile-response"]\');'
                    "return i ? i.value : '';") or ""
            except Exception:
                tok = ""
            if tok:
                break
            try:
                sb.uc_gui_handle_captcha()
            except Exception as e:
                print("[uc] gui_handle:", str(e)[:90])
            time.sleep(1)
        print("[uc] token_len", len(tok))
        if tok:
            with open("ts_token.txt", "w") as f:
                f.write(tok)
            print("[uc] OK")
        else:
            print("[uc] FAIL")
    sys.exit(0)

if __name__ == "__main__":
    main()
