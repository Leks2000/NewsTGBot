from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import random, time


def test_twitter_login():
    stealth = Stealth()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)  # visible для первого раза
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800},
        )
        page = context.new_page()
        stealth.apply_stealth_sync(page)
        page.goto('https://x.com/login', wait_until='networkidle')
        time.sleep(random.uniform(2, 4))

        # Медленный ввод (имитация человека)
        page.fill('input[name="text"]', 'alex.halle06@list.ru')
        time.sleep(random.uniform(1, 2))
        page.click('button:has-text("Next")')
        time.sleep(random.uniform(2, 5))

        page.fill('input[name="password"]', '07022004Gg')
        time.sleep(random.uniform(1, 3))
        page.click('button:has-text("Log in")')

        try:
            page.wait_for_selector('[data-testid="SideNav_NewTweet_Button"]', timeout=45000)
            print("✅ Залогинился!")
            context.storage_state(path="x_login_state.json")
        except:
            page.screenshot(path="login_failed.png")
            print("Провал — смотри скрин login_failed.png")

        browser.close()

if __name__ == "__main__":
    test_twitter_login()