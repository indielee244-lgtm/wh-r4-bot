"""
WH Rule 4 Telegram Bot
Send /r4 to get today's Rule 4 deductions from William Hill.
"""

import os
import asyncio
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from scraper import run_scraper

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TELEGRAM_TOKEN')

def format_results(results):
    """Format Rule 4 results as a Telegram message."""
    if not results:
        return "✅ No Rule 4 deductions found today."

    today = datetime.now().strftime('%d/%m/%Y')
    lines = [f"🏇 *WH Rule 4 Deductions — {today}*\n"]

    # Sort by race time
    all_r4s = []
    for race in results:
        for r4 in race['rule4s']:
            all_r4s.append({
                'time':      race['time'],
                'course':    race['course'],
                'race_name': race['race_name'],
                'ded_p':     r4['ded_p'],
                'from_time': r4['from_time'],
                'to_time':   r4['to_time'],
            })

    all_r4s.sort(key=lambda x: x['time'])

    for r in all_r4s:
        label = f"{r['time']} {r['course']}"
        if r['race_name']:
            label += f" — {r['race_name']}"
        lines.append(
            f"*{r['ded_p']}p* in the £\n"
            f"_{label}_\n"
            f"Bets: {r['from_time']} → {r['to_time']}\n"
        )

    lines.append(f"_{len(all_r4s)} deduction(s) found_")
    return '\n'.join(lines)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏇 *WH Rule 4 Bot*\n\n"
        "Commands:\n"
        "/r4 — Fetch today's Rule 4 deductions from William Hill\n\n"
        "The scan takes 3–5 minutes. You'll get progress updates as it runs.",
        parse_mode='Markdown'
    )

async def r4_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⏳ Starting scan... this takes 3–5 minutes.")

    async def status_callback(text):
        try:
            await msg.edit_text(text)
        except Exception:
            pass

    try:
        results, error = await run_scraper(status_callback=status_callback)

        if error:
            await msg.edit_text(f"❌ Error: {error}")
            return

        formatted = format_results(results)
        await msg.edit_text(formatted, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Scraper error: {e}")
        await msg.edit_text(f"❌ Unexpected error: {str(e)[:200]}")

def main():
    if not TOKEN:
        raise ValueError("TELEGRAM_TOKEN environment variable not set")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("r4", r4_command))

    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
