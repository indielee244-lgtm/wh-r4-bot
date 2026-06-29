"""
WH Rule 4 scraper using Playwright with residential proxy and anti-detection measures
"""

import re
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

MEETINGS_URL = "https://sports.williamhill.com/betting/en-gb/horse-racing/meetings"
VALID_DEDS   = {5,10,15,20,25,30,35,40,45,50,55,60,65,70,75,80,90}

PROXY = {
    "server":   "http://31.59.20.176:6754",
    "username": "fvylnpij",
    "password": "ahmpytc5mpss"
}

def time_to_mins(t):
    if not t: return -1
    p = t.strip().split(':')
    try: return int(p[0]) * 60 + int(p[1])
    except: return -1

def parse_slug(url):
    m = re.search(r'/(\d{4})-([a-z0-9][a-z0-9-]*)(?:/|$)', url, re.IGNORECASE)
    if m:
        raw = m.group(1)
        return raw[:2]+':'+raw[2:], m.group(2).replace('-',' ').title()
    return '', ''

def parse_rule4(text, race_time):
    results  = []
    seen     = set()
    race_min = time_to_mins(race_time)
    pat = re.compile(
        r'([A-Za-z][^-\n]{2,60}?)\s*-\s*(\d+)p\s+reductions?\s+on\s+bets?\s+placed\s+between\s+'
        r'(\d{1,2}:\d{2}(?::\d{2})?)\s+and\s+(\d{1,2}:\d{2}(?::\d{2})?)',
        re.IGNORECASE
    )
    for m in pat.finditer(text):
        market, ded, tf, tt = m.group(1).strip(), int(m.group(2)), m.group(3), m.group(4)
        if ded not in VALID_DEDS: continue
        if not re.match(r'^win\b', market, re.IGNORECASE): continue
        key = f"{ded}|{tf}|{tt}"
        if key in seen: continue
        seen.add(key)
        to_m = time_to_mins(tt)
        if race_min > 0 and to_m > race_min + 120: continue
        results.append({'ded_p': ded, 'from_time': tf, 'to_time': tt})
    return results

async def make_browser(pw):
    browser = await pw.chromium.launch(
        headless=True,
        proxy=PROXY,
        args=[
            '--no-sandbox',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
            '--disable-infobars',
            '--disable-popup-blocking',
        ]
    )
    context = await browser.new_context(
        proxy=PROXY,
        user_agent='Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        viewport={'width': 390, 'height': 844},
        locale='en-GB',
        timezone_id='Europe/London',
        extra_http_headers={'Accept-Language': 'en-GB,en;q=0.9'}
    )
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3]});
        Object.defineProperty(navigator, 'languages', {get: () => ['en-GB', 'en']});
        window.chrome = { runtime: {} };
    """)
    return browser, context

async def get_race_links(page):
    await page.goto(MEETINGS_URL, wait_until='networkidle', timeout=30000)
    await page.wait_for_timeout(5000)
    try:
        await page.click('.acceptButton', timeout=3000)
        await page.wait_for_timeout(1000)
    except: pass
    try:
        await page.click('.cookie-disclaimer__button', timeout=3000)
        await page.wait_for_timeout(1000)
    except: pass
    links = await page.eval_on_selector_all(
        'a[href*="/OB_EV"]',
        'els => [...new Set(els.map(e => e.href))].filter(h => h.includes("/OB_EV"))'
    )
    return links

async def scrape_race(page, url):
    try:
        await page.goto(url, wait_until='networkidle', timeout=20000)
        await page.wait_for_timeout(2500)
    except: return None
    text = await page.evaluate('() => document.body.innerText || document.body.textContent || ""')
    time_, course = parse_slug(url)
    title = await page.title()
    race_name = ''
    m = re.search(r'\d{1,2}:\d{2}\s+\S+\s*[-–]\s*(.+?)(?:\s*\||$)', title)
    if m: race_name = m.group(1).strip()
    rule4s = parse_rule4(text, time_)
    if not rule4s: return None
    return {'time': time_, 'course': course, 'race_name': race_name, 'rule4s': rule4s}

async def run_scraper(status_callback=None):
    results = []
    async with async_playwright() as pw:
        browser, context = await make_browser(pw)
        page = await context.new_page()
        if status_callback:
            await status_callback("🔍 Opening William Hill meetings page...")
        try:
            links = await get_race_links(page)
        except Exception as e:
            await browser.close()
            return None, f"Could not load WH meetings page: {e}"
        if not links:
            await browser.close()
            return None, "No races found. WH may be blocking this server's IP."
        if status_callback:
            await status_callback(f"📋 Found {len(links)} races. Checking each one...")
        for i, url in enumerate(links):
            if status_callback and i % 5 == 0:
                await status_callback(f"⏳ Checking race {i+1}/{len(links)}...")
            data = await scrape_race(page, url)
            if data: results.append(data)
            await asyncio.sleep(0.8)
        await browser.close()
    return results, None
