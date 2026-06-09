import argparse
import random
import string
import sys
import time
from dataclasses import dataclass

from appium import webdriver
from appium.options.android import UiAutomator2Options
from selenium.common.exceptions import StaleElementReferenceException, WebDriverException
from selenium.webdriver.common.by import By

try:
    from config import ACCEPT_TERMS, ANDROID_DEVICE, APPIUM_SERVER, GMAIL_USERNAME_PREFIX
except ImportError:
    ACCEPT_TERMS = False
    ANDROID_DEVICE = "127.0.0.1:5675"
    APPIUM_SERVER = "http://127.0.0.1:4723"
    GMAIL_USERNAME_PREFIX = ""


FIRST_NAMES = [
    "Alex",
    "Casey",
    "Drew",
    "Jordan",
    "Morgan",
    "Riley",
    "Taylor",
]

LAST_NAMES = [
    "Hayes",
    "Lane",
    "Parker",
    "Reed",
    "Stone",
    "Wells",
    "Young",
]

MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


@dataclass
class Account:
    username: str
    password: str
    first_name: str
    last_name: str
    month: str
    day: int
    year: int


def log(message: str) -> None:
    print(message.encode("ascii", "backslashreplace").decode("ascii"), flush=True)


def generate_account(prefix: str = "") -> Account:
    alphabet = string.ascii_lowercase + string.digits
    stem = prefix or "gm" + "".join(random.choice(string.ascii_lowercase) for _ in range(6))
    suffix = "".join(random.choice(alphabet) for _ in range(8))
    username = (stem + suffix)[:28]
    password = (
        random.choice(string.ascii_uppercase)
        + "".join(random.choice(string.ascii_lowercase) for _ in range(5))
        + "".join(random.choice(string.digits) for _ in range(4))
        + random.choice("!@#")
    )
    return Account(
        username=username,
        password=password,
        first_name=random.choice(FIRST_NAMES),
        last_name=random.choice(LAST_NAMES),
        month=random.choice(MONTHS),
        day=random.randint(1, 28),
        year=random.randint(1985, 2000),
    )


def make_driver(
    server_url: str,
    device_name: str,
    no_reset: bool,
    launch_gmail: bool = True,
) -> webdriver.Remote:
    options = UiAutomator2Options()
    options.platform_name = "Android"
    options.device_name = device_name
    options.automation_name = "UiAutomator2"
    options.no_reset = no_reset
    options.new_command_timeout = 600
    if launch_gmail:
        options.app_package = "com.google.android.gm"
        options.app_activity = "com.google.android.gm.ConversationListActivityGmail"
        options.set_capability(
            "appWaitActivity",
            ",".join(
                [
                    "com.google.android.gm.ConversationListActivityGmail",
                    "com.google.android.gm.welcome.SetupAddressesActivity",
                    "com.google.android.gm.welcome.WelcomeTourActivity",
                    "com.google.android.gms.*",
                ]
            ),
        )
        options.set_capability("appWaitDuration", 90000)
    options.set_capability("adbExecTimeout", 90000)
    options.set_capability("uiautomator2ServerInstallTimeout", 90000)
    options.set_capability("uiautomator2ServerLaunchTimeout", 90000)
    # BlueStacks ADB 兼容性：跳过会搞崩 ADB 的初始化/清理步骤
    options.set_capability("skipDeviceInitialization", True)
    options.set_capability("skipServerInstallation", False)
    options.set_capability("ignoreHiddenApiPolicyError", True)
    options.set_capability("suppressKillServer", True)
    options.set_capability("remoteAdbHost", "127.0.0.1")
    options.set_capability("adbPort", 5037)
    return webdriver.Remote(server_url, options=options)


def is_element_visible(el) -> bool:
    try:
        rect = el.rect
        return rect.get("width", 0) > 0 and rect.get("height", 0) > 0
    except (StaleElementReferenceException, WebDriverException):
        return False


def visible_texts(driver: webdriver.Remote) -> list[str]:
    for _ in range(4):
        texts: list[str] = []
        try:
            for el in driver.find_elements(By.XPATH, "//*[@text or @content-desc]"):
                if not is_element_visible(el):
                    continue
                text = (el.get_attribute("text") or el.get_attribute("content-desc") or "").strip()
                if text and text not in texts:
                    texts.append(text)
            return texts
        except (StaleElementReferenceException, WebDriverException) as exc:
            if not is_stale_error(exc):
                raise
            time.sleep(1)
    return []


def dump_state(driver: webdriver.Remote, title: str) -> list[str]:
    texts = visible_texts(driver)
    log(f"\n--- {title} ---")
    log(" | ".join(texts[:80]))
    return texts


def find_text(driver: webdriver.Remote, text: str, contains: bool = False):
    if contains:
        xpath = (
            "//*[contains(translate(@text,"
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
            f"'{text.lower()}') or contains(translate(@content-desc,"
            "'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),"
            f"'{text.lower()}')]"
        )
    else:
        xpath = f"//*[@text={xpath_literal(text)} or @content-desc={xpath_literal(text)}]"
    els = driver.find_elements(By.XPATH, xpath)
    visible = [el for el in els if is_element_visible(el)]
    return visible[0] if visible else None


def find_resource_id(driver: webdriver.Remote, resource_id: str):
    xpath = f"//*[@resource-id={xpath_literal(resource_id)}]"
    els = driver.find_elements(By.XPATH, xpath)
    visible = [el for el in els if is_element_visible(el)]
    return visible[0] if visible else None


def is_stale_error(exc: Exception) -> bool:
    return isinstance(exc, StaleElementReferenceException) or "stale element reference" in str(exc).lower()


def xpath_literal(value: str) -> str:
    if "'" not in value:
        return f"'{value}'"
    if '"' not in value:
        return f'"{value}"'
    parts = value.split("'")
    return "concat(" + ", \"'\", ".join(f"'{part}'" for part in parts) + ")"


def click_text(driver: webdriver.Remote, text: str, contains: bool = False, timeout: int = 10) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        el = find_text(driver, text, contains=contains)
        if el:
            try:
                log(f"click: {text}")
                el.click()
                time.sleep(0.5)
                return True
            except (StaleElementReferenceException, WebDriverException) as exc:
                if not is_stale_error(exc):
                    raise
                time.sleep(0.5)
        time.sleep(0.5)
    return False


def tap_text_center(driver: webdriver.Remote, text: str, contains: bool = False, timeout: int = 10) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        el = find_text(driver, text, contains=contains)
        if el:
            rect = el.rect
            x = int(rect["x"] + rect["width"] / 2)
            y = int(rect["y"] + rect["height"] / 2)
            log(f"tap: {text} at {x},{y}")
            driver.execute_script("mobile: clickGesture", {"x": x, "y": y})
            time.sleep(0.5)
            return True
        time.sleep(0.5)
    return False


def click_or_tap_text(driver: webdriver.Remote, text: str, contains: bool = False, timeout: int = 10) -> bool:
    if not click_text(driver, text, contains=contains, timeout=timeout):
        return False
    time.sleep(0.5)
    return True


def click_next(driver: webdriver.Remote, timeout: int = 10) -> bool:
    """填完表单后立刻找 Next 按钮点击，不做长时间轮询。"""
    for label in ("Next", "NEXT", "next"):
        el = find_text(driver, label)
        if el:
            try:
                log(f"click: {label}")
                el.click()
                time.sleep(0.5)
                return True
            except (StaleElementReferenceException, WebDriverException):
                pass
    return click_text(driver, "Next", timeout=timeout)


def require_page(driver: webdriver.Remote, needles: list[str], title: str, timeout: int = 30) -> list[str]:
    texts = wait_until_any(driver, needles, timeout=timeout)
    joined = "\n".join(texts).lower()
    if not any(needle.lower() in joined for needle in needles):
        dump_state(driver, f"unexpected page while waiting for {title}")
        raise RuntimeError(f"Expected {title}, but none of these were visible: {', '.join(needles)}")
    return texts


def input_by_text_hint(driver: webdriver.Remote, hint: str, value: str, timeout: int = 20) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        el = find_text(driver, hint, contains=True)
        if el:
            log(f"type into {hint}: {mask(value)}")
            el.click()
            time.sleep(0.5)
            el.send_keys(value)
            time.sleep(0.5)
            return True
        time.sleep(1)
    return False


def input_by_resource_id(driver: webdriver.Remote, resource_id: str, value: str, timeout: int = 20) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        el = find_resource_id(driver, resource_id)
        if el:
            log(f"type into {resource_id}: {mask(value)}")
            el.click()
            time.sleep(0.5)
            try:
                el.clear()
            except WebDriverException:
                pass
            el.send_keys(value)
            time.sleep(0.5)
            return True
        time.sleep(1)
    return False


def input_edittexts(driver: webdriver.Remote, values: list[str]) -> bool:
    edits = [el for el in driver.find_elements(By.CLASS_NAME, "android.widget.EditText") if is_element_visible(el)]
    if len(edits) < len(values):
        return False
    for el, value in zip(edits, values):
        el.click()
        time.sleep(0.4)
        log(f"type: {mask(value)}")
        el.send_keys(value)
        time.sleep(0.4)
    return True


def input_edittext_index(driver: webdriver.Remote, index: int, value: str, timeout: int = 20) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        edits = [el for el in driver.find_elements(By.CLASS_NAME, "android.widget.EditText") if is_element_visible(el)]
        if len(edits) > index:
            el = edits[index]
            el.click()
            time.sleep(0.4)
            try:
                el.clear()
            except WebDriverException:
                pass
            log(f"type into edittext[{index}]: {mask(value)}")
            el.send_keys(value)
            time.sleep(0.4)
            return True
        time.sleep(1)
    return False


def mask(value: str) -> str:
    if len(value) >= 8 and any(ch.isdigit() for ch in value):
        return "*" * len(value)
    return value


def wait_until_any(driver: webdriver.Remote, needles: list[str], timeout: int = 60) -> list[str]:
    end = time.time() + timeout
    while time.time() < end:
        texts = visible_texts(driver)
        joined = "\n".join(texts).lower()
        if any(needle.lower() in joined for needle in needles):
            return texts
        time.sleep(2)
    return visible_texts(driver)


def select_spinner_item(driver: webdriver.Remote, field_text: str, item_text: str) -> bool:
    if not click_or_tap_text(driver, field_text, contains=True, timeout=5):
        return False
    time.sleep(0.5)
    return click_or_tap_text(driver, item_text, contains=True, timeout=5)


def select_spinner_by_index(driver: webdriver.Remote, index: int, item_text: str) -> bool:
    spinners = [el for el in driver.find_elements(By.CLASS_NAME, "android.widget.Spinner") if is_element_visible(el)]
    if len(spinners) <= index:
        return False
    spinners[index].click()
    time.sleep(1)
    return click_or_tap_text(driver, item_text, contains=True, timeout=10)


def click_button(driver: webdriver.Remote, text: str, timeout: int = 20) -> bool:
    return click_or_tap_text(driver, text, contains=False, timeout=timeout)


def proceed_gmail_onboarding(driver: webdriver.Remote) -> None:
    for _ in range(12):
        texts = dump_state(driver, "gmail onboarding")
        joined = "\n".join(texts)
        if ("Welcome to Gmail" in joined or "New in Gmail" in joined) and "SKIP" in texts:
            click_text(driver, "SKIP", timeout=5)
        elif ("Welcome to Gmail" in joined or "New in Gmail" in joined) and "Next" in texts:
            click_text(driver, "Next", timeout=5)
        elif ("Welcome to Gmail" in joined or "New in Gmail" in joined) and "GOT IT" in texts:
            click_text(driver, "GOT IT", timeout=5)
        elif "GOT IT" in texts:
            click_text(driver, "GOT IT", timeout=5)
        elif "OK" in texts and "Please add at least one email address." in joined:
            click_text(driver, "OK", timeout=5)
        elif "Add an email address" in texts:
            click_text(driver, "Add an email address", timeout=5)
        elif "Google" in texts:
            click_text(driver, "Google", timeout=5)
            wait_until_any(driver, ["Sign in", "Create account", "Checking info"], timeout=60)
            return
        elif "Create account" in joined or "Sign in" in joined:
            return
        elif "Basic information" in joined or "Enter your name" in joined:
            return
        else:
            time.sleep(3)


def complete_post_phone_flow(driver: webdriver.Remote, accept_terms: bool) -> str:
    for _ in range(30):
        texts = dump_state(driver, "post-phone flow")
        joined = "\n".join(texts).lower()

        if "conversationlistactivitygmail" in driver.current_activity.lower():
            return "gmail_opened"

        if "review your account info" in joined:
            click_next(driver, timeout=10)
            continue

        if "privacy and terms" in joined:
            if not accept_terms:
                return "terms_waiting_for_user"
            for _ in range(6):
                if click_button(driver, "I agree", timeout=3):
                    break
                driver.swipe(450, 1450, 450, 350, 700)
                time.sleep(1)
            else:
                raise RuntimeError("Could not find I agree on Privacy and Terms page")
            continue

        if "google services" in joined:
            if not click_button(driver, "ACCEPT", timeout=10):
                driver.swipe(450, 1450, 450, 350, 700)
                click_button(driver, "ACCEPT", timeout=10)
            continue

        if "take me to gmail" in joined:
            click_button(driver, "TAKE ME TO GMAIL", timeout=10)
            continue

        if "add another email address" in joined and any("@gmail.com" in text for text in texts):
            click_button(driver, "TAKE ME TO GMAIL", timeout=10)
            continue

        if "this may take a few moments" in joined or "loading" in joined:
            time.sleep(5)
            continue

        if "verify it's you" in joined or "try another way" in joined or "unusual about your activity" in joined:
            return "manual_verification"

        if any("phone number" in text.lower() or "verification code" in text.lower() for text in texts):
            return "phone_verification"

        time.sleep(2)

    return "unknown_post_phone_step"


def create_account_flow(
    driver: webdriver.Remote,
    account: Account,
    stop_after_create_account: bool = False,
    wait_phone_verification: bool = False,
    accept_terms: bool = False,
) -> str:
    proceed_gmail_onboarding(driver)

    # 等 Sign-in 页面真正加载完（"Checking info..." 过渡页可能延迟数秒）
    wait_until_any(driver, ["Sign in", "Create account", "Enter your name", "Basic information"], timeout=60)
    texts = dump_state(driver, "google sign-in")
    if any("Sign in" in t or "Create account" in t for t in texts):
        if not click_or_tap_text(driver, "Create account", contains=True, timeout=20):
            raise RuntimeError("Could not find Create account on Google sign-in page")
        if stop_after_create_account:
            dump_state(driver, "after create account")
            return "stopped_after_create_account"
        wait_until_any(driver, ["For my personal use", "Enter your name", "Create a Google Account"], timeout=20)
        click_or_tap_text(driver, "For my personal use", contains=True, timeout=5)

    require_page(driver, ["First name", "Enter your name", "Basic information"], "name or birthday page", timeout=45)
    texts = dump_state(driver, "name page")
    if "First name" in "\n".join(texts) or "Enter your name" in "\n".join(texts):
        if not input_by_resource_id(driver, "firstName", account.first_name, timeout=5):
            input_edittexts(driver, [account.first_name, account.last_name])
        else:
            input_by_resource_id(driver, "lastName", account.last_name, timeout=5)
        click_next(driver)

    require_page(driver, ["Basic information", "birthday", "gender"], "birthday page", timeout=45)
    dump_state(driver, "birthday page")

    # Google 注册页在 WebView 里渲染，原生 Spinner 操作月份经常失效。
    # 优先切到 WEBVIEW context 用 web select 操作，最可靠。
    month_num = MONTHS.index(account.month) + 1 if account.month in MONTHS else 1
    bday_filled_via_web = False
    try:
        contexts = driver.contexts
        log(f"available contexts: {contexts}")
        webview_ctx = next((c for c in contexts if "WEBVIEW" in c), None)
        if webview_ctx:
            driver.switch_to.context(webview_ctx)
            time.sleep(1)
            # Month: <select id="month"> or first <select>
            from selenium.webdriver.support.ui import Select
            selects = driver.find_elements(By.TAG_NAME, "select")
            if selects:
                Select(selects[0]).select_by_value(str(month_num))
                log(f"web select month: {month_num}")
            # Day
            day_input = driver.find_elements(By.CSS_SELECTOR, "input#day, input[name='day']")
            if day_input:
                day_input[0].clear()
                day_input[0].send_keys(str(account.day))
            # Year
            year_input = driver.find_elements(By.CSS_SELECTOR, "input#year, input[name='year']")
            if year_input:
                year_input[0].clear()
                year_input[0].send_keys(str(account.year))
            # Gender: <select id="gender"> or second <select>
            if len(selects) > 1:
                Select(selects[1]).select_by_value("3")
            bday_filled_via_web = True
            driver.switch_to.context("NATIVE_APP")
            time.sleep(1)
            click_next(driver)
    except Exception as e:
        log(f"webview birthday fill failed: {e}, falling back to native")
        try:
            driver.switch_to.context("NATIVE_APP")
        except Exception:
            pass

    if not bday_filled_via_web:
        # 原生模式 fallback
        for _retry in range(3):
            if select_spinner_item(driver, "Month", account.month):
                break
            time.sleep(1)
            if select_spinner_by_index(driver, 0, account.month):
                break
            time.sleep(1)
        time.sleep(1)
        if not input_by_resource_id(driver, "day", str(account.day), timeout=5):
            if not input_by_text_hint(driver, "Day", str(account.day), timeout=8):
                raise RuntimeError("Could not fill birth day")
        if not input_by_resource_id(driver, "year", str(account.year), timeout=5):
            if not input_by_text_hint(driver, "Year", str(account.year), timeout=8):
                raise RuntimeError("Could not fill birth year")
        if not select_spinner_item(driver, "Gender", "Rather not say"):
            if not select_spinner_by_index(driver, 1, "Rather not say"):
                select_spinner_by_index(driver, 1, "Prefer not to say")
        click_next(driver)

    time.sleep(2)
    retry_texts = visible_texts(driver)
    retry_joined = "\n".join(retry_texts).lower()
    if "please fill in a complete birthday" in retry_joined:
        log("birthday still incomplete after retry")
        raise RuntimeError("Could not fill birthday — month selection keeps failing")

    require_page(
        driver,
        ["Create an email address", "Gmail address", "Choose your Gmail address", "How you'll sign in"],
        "Gmail address page",
        timeout=90,
    )
    texts = dump_state(driver, "gmail address page")
    joined = "\n".join(texts)
    # 优先选 Google 推荐的完整邮箱地址（排除纯 "@gmail.com" 后缀标签）
    suggested = [t for t in texts if "@gmail.com" in t and t.strip() != "@gmail.com" and len(t) > len("@gmail.com")]
    if suggested:
        chosen = suggested[0]
        log(f"selecting suggested address: {chosen}")
        if click_text(driver, chosen, timeout=10):
            account.username = chosen.replace("@gmail.com", "")
        else:
            click_or_tap_text(driver, chosen, contains=True, timeout=10)
            account.username = chosen.replace("@gmail.com", "")
    elif "How you" in joined and "sign in" in joined.lower():
        if not input_edittext_index(driver, 0, account.username, timeout=10):
            if not input_by_text_hint(driver, "Gmail address", account.username, timeout=5):
                input_by_text_hint(driver, "Username", account.username, timeout=5)
    elif click_text(driver, "Create your own Gmail address", contains=True, timeout=5):
        wait_until_any(driver, ["Gmail address", "Username", "How you'll sign in"], timeout=20)
        if not input_by_text_hint(driver, "Gmail address", account.username, timeout=5):
            if not input_by_text_hint(driver, "Username", account.username, timeout=5):
                input_edittexts(driver, [account.username])
    else:
        candidate = next((text for text in texts if text.endswith("@gmail.com")), "")
        if not candidate:
            raise RuntimeError("Could not find or enter a Gmail address")
        account.username = candidate.removesuffix("@gmail.com")
        click_text(driver, candidate, timeout=10)
    click_next(driver)

    require_page(driver, ["Create a strong password", "Password", "Show password"], "password page", timeout=90)
    dump_state(driver, "password page")
    edits = [el for el in driver.find_elements(By.CLASS_NAME, "android.widget.EditText") if is_element_visible(el)]
    if len(edits) >= 2:
        if not input_edittexts(driver, [account.password, account.password]):
            raise RuntimeError("Could not fill password fields")
    elif not input_edittext_index(driver, 0, account.password, timeout=10):
        if not input_by_text_hint(driver, "Password", account.password, timeout=10):
            raise RuntimeError("Could not fill password")
        input_by_text_hint(driver, "Confirm", account.password, timeout=5)
    click_next(driver)

    texts = wait_until_any(
        driver,
        ["Verify your phone number", "Get a verification code", "phone number", "Confirm you're not a robot", "Skip"],
        timeout=90,
    )
    dump_state(driver, "after password")
    if any("phone number" in text.lower() or "verification code" in text.lower() for text in texts):
        if not wait_phone_verification:
            return "phone_verification"
        log("Waiting for manual phone/SMS verification to complete...")
        wait_until_any(
            driver,
            ["Review your account info", "Privacy and Terms", "Google services", "TAKE ME TO GMAIL"],
            timeout=900,
        )
        return complete_post_phone_flow(driver, accept_terms=accept_terms)
    if any("Skip" == text or "Skip" in text for text in texts):
        return "optional_phone_or_recovery"
    return complete_post_phone_flow(driver, accept_terms=accept_terms)


def main() -> int:
    parser = argparse.ArgumentParser(description="Drive Gmail account signup locally.")
    parser.add_argument("--server", default=APPIUM_SERVER)
    parser.add_argument("--device", default=ANDROID_DEVICE)
    parser.add_argument("--prefix", default=GMAIL_USERNAME_PREFIX)
    parser.add_argument("--no-reset", action="store_true", default=True)
    parser.add_argument("--stop-after-create-account", action="store_true")
    parser.add_argument(
        "--wait-phone-verification",
        action="store_true",
        help="Wait up to 15 minutes for manual phone/SMS verification, then continue.",
    )
    parser.add_argument(
        "--resume-after-phone",
        action="store_true",
        help="Attach to the current screen and continue after manual phone/SMS verification.",
    )
    parser.add_argument(
        "--accept-terms",
        action="store_true",
        default=ACCEPT_TERMS,
        help="Click I agree on Privacy and Terms and ACCEPT on Google services.",
    )
    args = parser.parse_args()

    account = None
    if args.resume_after_phone:
        log("Resuming from the current emulator screen.")
    else:
        account = generate_account(args.prefix)
        log("Generated account:")
        log(f"  email: {account.username}@gmail.com")
        log(f"  password: {account.password}")
        log(f"  name: {account.first_name} {account.last_name}")
        log(f"  birthday: {account.month} {account.day}, {account.year}")
        if args.wait_phone_verification:
            log("The script will wait at phone/SMS/CAPTCHA verification and continue after you complete it manually.")
        else:
            log("The script will stop at phone/SMS/CAPTCHA verification.")

    driver = None
    try:
        driver = make_driver(args.server, args.device, args.no_reset, launch_gmail=not args.resume_after_phone)
        if args.resume_after_phone:
            result = complete_post_phone_flow(driver, accept_terms=args.accept_terms)
        else:
            if account is None:
                raise RuntimeError("Account generation failed")
            result = create_account_flow(
                driver,
                account,
                stop_after_create_account=args.stop_after_create_account,
                wait_phone_verification=args.wait_phone_verification,
                accept_terms=args.accept_terms,
            )
        log(f"\nResult: {result}")
        if account:
            log(f"Email: {account.username}@gmail.com")
            log(f"Password: {account.password}")
        if result == "phone_verification":
            log("Please complete phone verification manually in the emulator, then continue from the UI.")
            log("After verification, run again with --resume-after-phone. Add --accept-terms if you want the script to finish the consent pages.")
        elif result == "manual_verification":
            log("Google is asking for an additional manual verification step. Complete it in the emulator, then re-run with --resume-after-phone.")
        elif result == "terms_waiting_for_user":
            log("Privacy and Terms is waiting for confirmation. Re-run with --resume-after-phone --accept-terms to continue.")
        return 0
    except WebDriverException as exc:
        log(f"Appium/WebDriver error: {exc}")
        return 2
    except Exception as exc:
        log(f"Error: {exc}")
        return 1
    finally:
        # Keep the emulator and current page open for manual phone verification.
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
