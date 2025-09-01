# server.py
import os, asyncio, json, time, logging, random, smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.utils import formatdate
from fastapi import FastAPI
from playwright.async_api import async_playwright

# ====== 자격증명/환경 설정(직접 채우기) ======
BARO_ID   = "calm56@naver.com"
BARO_PW   = "kkb0506!"

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
SMTP_USER = "meowns11@gmail.com"     # 보내는 메일 주소
SMTP_PASS = "foeupbqothdqoyxp"           # Gmail이면 앱비번

MAIL_TO   = ["meowns@kakao.com"]  # 수신자 목록
TARGET_VENDOR = "인천약품"          # 감시할 도매상 이름
HEADLESS = True                        # Cloud Run 기본 headless
ALERT_COOLTIME_SEC = 60 * 60           # 동일 결과 재알림 쿨타임(초)
# =========================================

HOME_URL    = "https://www.baropharm.com/"
LOGIN_URL   = "https://www.baropharm.com/?from=/order"
EMOTON_URL  = "https://www.baropharm.com/order?q=%EC%9D%B4%EB%AA%A8%ED%8A%BC"

STATE_PATH  = "state.json"
ALERT_STATE = ".alert_state.json"

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger(__name__)

app = FastAPI()

def load_alert_state():
    try:
        with open(ALERT_STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"last_alert_ts": 0, "last_signature": ""}

def save_alert_state(d):
    with open(ALERT_STATE, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def send_mail(subject: str, body: str):
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and MAIL_TO):
        log.warning("메일 설정 비어있음. 콘솔 출력만 합니다.")
        print("제목:", subject); print("내용:\n", body)
        return
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"]    = SMTP_USER
    msg["To"]      = ", ".join(MAIL_TO)
    msg["Date"]    = formatdate(localtime=True)
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as s:
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(SMTP_USER, MAIL_TO, msg.as_string())

# --- UI 방해 tooltip 제거 ---
async def kill_tooltips(page):
    sel_tip = "[role='tooltip'], .tooltip-comp"
    try:
        tip = page.locator(sel_tip).first
        if await tip.count() > 0 and await tip.is_visible():
            close_btn = page.locator(".button-tooltip-close").first
            if await close_btn.count() > 0 and await close_btn.is_visible():
                await close_btn.click(force=True)
    except: pass
    try:
        if await page.locator(sel_tip).count() > 0:
            await page.keyboard.press("Escape")
    except: pass
    try:
        if await page.locator(sel_tip).count() > 0:
            await page.add_style_tag(content=f"{sel_tip}{{display:none!important;visibility:hidden!important;}}")
    except: pass
    try:
        if await page.locator(sel_tip).count() > 0:
            await page.evaluate("""
                document.querySelectorAll("[role='tooltip'], .tooltip-comp")
                        .forEach(el => el.remove());
            """)
    except: pass

# --- 셀렉터(바로몰 전용) ---
USER_TAB_SELECTORS = {
    "30": ["ul.list-detail li.item-detail button:has(span.name-text:has-text('300밀리그램 30 캡슐(병)'))"],
    "90": ["ul.list-detail li.item-detail button:has(span.name-text:has-text('300밀리그램 90 캡슐(병)'))"],
}
USER_TAB_ACTIVE = {
    "30": "ul.list-detail li.item-detail.active:has(span.name-text:has-text('30'))",
    "90": "ul.list-detail li.item-detail.active:has(span.name-text:has-text('90'))",
}
BARO_MALL_ROOT = "#baro-mall-list"
BARO_LIST_SEL  = "#baro-mall-list ul#list-inventory, #baro-mall-list .list-inventory"
BARO_ITEM_SEL  = "#baro-mall-list .list-inventory li.inventory-item"

async def is_login_ui_visible(page) -> bool:
    try:
        pw = page.locator("input[type='password'], input[placeholder*='비밀번호']")
        if await pw.count() > 0 and await pw.first.is_visible(): return True
        btn = page.locator("button:has-text('로그인'), [role=button]:has-text('로그인'), a:has-text('로그인')")
        if await btn.count() > 0 and await btn.first.is_visible(): return True
    except: pass
    return False

async def is_logged_in(page) -> bool:
    await page.goto(EMOTON_URL, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(300)
    return not (await is_login_ui_visible(page))

async def pick(page, selectors):
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            if await loc.count() > 0 and await loc.is_visible(): return loc
        except: pass
    return None

async def login_flow(page) -> bool:
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
    await page.wait_for_timeout(300)
    if not await is_login_ui_visible(page):
        return True
    id_box = await pick(page, [
        "input[name='id']", "input[name='userid']", "input[name='loginId']",
        "input[type='text']", "input[type='email']",
        "input[placeholder*='아이디']", "input[placeholder*='ID']",
    ])
    pw_box = await pick(page, [
        "input[type='password']", "input[name*='pw']",
        "input[placeholder*='비밀번호']",
    ])
    if not id_box or not pw_box:
        ok = await is_logged_in(page)
        if ok: return True
        await page.screenshot(path="login_fail.png", full_page=True)
        return False
    await id_box.fill(BARO_ID)
    await pw_box.fill(BARO_PW)
    submit_btn = await pick(page, [
        "button[type='submit']", "input[type='submit']",
        "button:has-text('로그인')", "[role=button]:has-text('로그인')",
    ])
    if submit_btn: await submit_btn.click()
    else: await page.keyboard.press("Enter")
    await page.wait_for_timeout(900)
    return await is_logged_in(page)

async def try_click_tab(page, key: str) -> bool:
    for sel in USER_TAB_SELECTORS.get(key, []):
        loc = page.locator(sel).first
        if await loc.count() > 0:
            await loc.scroll_into_view_if_needed()
            await kill_tooltips(page)
            await loc.click()
            act = USER_TAB_ACTIVE.get(key)
            if act:
                try: await page.locator(act).first.wait_for(state="visible", timeout=4000)
                except: pass
            return True
    return False

async def find_baro_list(page):
    try:
        await page.wait_for_selector(BARO_LIST_SEL, timeout=10000)
    except: pass
    loc = page.locator(BARO_LIST_SEL).first
    return loc if await loc.count() > 0 else None

async def load_all_in_baro(page, max_ms: int = 30000):
    start = time.time(); last = -1; stable = 0
    while (time.time() - start) * 1000 < max_ms:
        items = page.locator(BARO_ITEM_SEL)
        cnt = await items.count()
        stable = stable + 1 if cnt == last else 0
        last = cnt
        if stable >= 3: break
        if cnt > 0:
            await items.last.scroll_into_view_if_needed()
        await page.wait_for_timeout(400)
    log.info("바로몰 로드: %d개", max(0, last))

async def detect_vendor(page, target: str) -> bool:
    if not await find_baro_list(page):
        log.warning("바로몰 컨테이너 미발견")
        return False
    try:
        await page.wait_for_selector(BARO_ITEM_SEL, timeout=10000)
    except: await page.wait_for_timeout(300)
    await load_all_in_baro(page)
    names = []
    vendors = page.locator(f"{BARO_MALL_ROOT} .wholesaler-name-box .text-ellipsis")
    for i in range(await vendors.count()):
        try:
            names.append((await vendors.nth(i).inner_text()).strip())
        except: pass
    log.info("바로몰 업체들: %s", names)
    return any(target in n for n in names)

async def run_once() -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=HEADLESS, args=["--no-sandbox"])
        try:
            context = await browser.new_context(
                locale="ko-KR",
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/125.0.0.0 Safari/537.36"),
                viewport={"width": 1366, "height": 900},
            )
            # 저장 세션 재사용(있으면)
            if os.path.exists(STATE_PATH):
                await context.close()
                context = await browser.new_context(storage_state=STATE_PATH, locale="ko-KR")
            page = await context.new_page()

            # 로그인
            if not await is_logged_in(page):
                ok = await login_flow(page)
                if not ok:
                    await context.close(); await browser.close()
                    return {"ok": False, "error": "login_failed"}
                await context.storage_state(path=STATE_PATH)

            # 대상 페이지
            await page.goto(EMOTON_URL, wait_until="domcontentloaded", timeout=20000)
            await kill_tooltips(page)
            await page.wait_for_selector("ul.list-detail li.item-detail button span.name-text", timeout=15000)

            # 30/90 검사
            results = {}
            for key in ("30", "90"):
                clicked = False
                for _ in range(3):
                    if await try_click_tab(page, key):
                        clicked = True; break
                    await asyncio.sleep(0.3 + random.random()*0.2)
                await asyncio.sleep(0.6)
                results[key] = await detect_vendor(page, TARGET_VENDOR)

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            any_found = results["30"] or results["90"]
            signature = f"{TARGET_VENDOR}-30:{results['30']}-90:{results['90']}"

            st = load_alert_state()
            now = int(time.time())
            if any_found:
                if signature == st.get("last_signature") and (now - st.get("last_alert_ts", 0)) < ALERT_COOLTIME_SEC:
                    log.info("중복 억제(쿨타임). 메일 생략.")
                else:
                    subject = f"[바로팜] '{TARGET_VENDOR}' 감지 (바로몰 30/90)"
                    body = f"""이모튼(바로몰) '{TARGET_VENDOR}' 감지

시간: {ts}
URL:  {EMOTON_URL}

- 30캡슐: {'감지됨' if results['30'] else '없음'}
- 90캡슐: {'감지됨' if results['90'] else '없음'}
"""
                    send_mail(subject, body)
                    st["last_signature"] = signature
                    st["last_alert_ts"]  = now
                    save_alert_state(st)

            await context.close()
            return {"ok": True, "found": any_found, "details": results}
        finally:
            await browser.close()

# Cloud Run 엔드포인트
@app.get("/")
async def health():
    return {"ok": True}

@app.post("/run")
async def trigger():
    return await run_once()
