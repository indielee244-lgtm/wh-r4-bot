"""
WH Rule 4 scraper using Playwright.
Visits each race on the WH meetings page and returns Rule 4 deductions.
"""

import re
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

MEETINGS_URL = "https://sports.williamhill.com/betting/en-gb/horse-racing/meetings"

VALID_DEDS = {5,10,15,20,25,30,35,40,45,50,55,60,65,70,75,80,90}

def parse_slug(url):
    """Extract race time and course from WH URL slug."""
    m = re.search(r'/(\d{4})-([a-z0-9][a-z0-9-]*)(?:/|$)', url, re.IGNORECASE)
    if m:
        raw    = m.group(1)
        time   = raw[:2] + ':' + raw[2:]
        course = m.group(2).replace('-', ' ').title()
        return time, course
    return '', ''

def parse_rule4(text, race_time):
    """Parse Win Rule 4 deductions, filtering out previous-day withdrawals."""
    results = []
    seen    = set()
    race_mins = time_to_mins(race_time)

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
        # Filter prev-day: To time > race time + 2 hours
        to_m = time_to_mins(tt)
        if race_mins > 0 and to_m > race_mins + 120:
            continue
        results.append({'ded_p': ded, 'from_time': tf, 'to_time': tt})
    return results

def time_to_mins(t):
    if not t: return -1
    p = t.strip().split(':')
    try: return int(p[0]) * 60 + int(p[1])
    except: return -1

async def get_race_links(page):
    """Get all race URLs from the WH meetings page."""
    await page.goto(MEETINGS_URL, wait_until='networkidle', timeout=30000)
    await page.wait_for_timeout(4000)

    links = await page.eval_on_selector_all(
        'a[href*="/OB_EV"]',
        '''els => [...new Set(els.map(e => e.href))].filter(h => h.includes('/OB_EV'))'''
    )
    return links

async def scrape_race(page, url):
    """Visit a race page and extract Rule 4 data."""
    try:
        await page.goto(url, wait_until='networkidle', timeout=20000)
        await page.wait_for_timeout(3000)
    except Exception:
        return None

    text = await page.evaluate('() => document.body.innerText || document.body.textContent || ""')
    time_, course = parse_slug(url)

    # Get race name from title
    title = await page.title()
    race_name = ''
    m = re.search(r'\d{1,2}:\d{2}\s+\S+\s*[-–]\s*(.+?)(?:\s*\||$)', title)
    if m:
        race_name = m.group(1).strip()

    rule4s = parse_rule4(text, time_)
    return {
        'url':       url,
        'time':      time_,
        'course':    course,
        'race_name': race_name,
        'rule4s':    rule4s,
    }

async def run_scraper(status_callback=None):
    """
    Main scraper. Returns list of Rule 4 results.
    status_callback(msg) called with progress updates.
    """
    results = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 800}
        )
        page = await context.new_page()

        # Step 1: Get race links
        if status_callback:
            await status_callback("🔍 Opening William Hill meetings page...")
        try:
            links = await get_race_links(page)
        except Exception as e:
            await browser.close()
            return None, f"Could not load WH meetings page: {e}"

        if not links:
            await browser.close()
            return None, "No races found on WH meetings page."

        if status_callback:
            await status_callback(f"📋 Found {len(links)} races. Checking each one...")

        # Step 2: Visit each race
        for i, url in enumerate(links):
            if status_callback and i % 5 == 0:
                await status_callback(f"⏳ Checking race {i+1}/{len(links)}...")
            data = await scrape_race(page, url)
            if data and data['rule4s']:
                results.append(data)
            await asyncio.sleep(0.5)

        await browser.close()

    return results, None
