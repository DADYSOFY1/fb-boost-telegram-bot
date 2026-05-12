"""
start.py - runs both the Telegram bot and the web dashboard concurrently
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dashboard.server import make_app, DASHBOARD_PORT
from aiohttp import web

import os
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')


async def run_dashboard():
    app = make_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', DASHBOARD_PORT)
    await site.start()
    print(f'Dashboard running on http://0.0.0.0:{DASHBOARD_PORT}')


async def run_bot():
    if not TOKEN:
        print('WARNING: TELEGRAM_BOT_TOKEN not set — bot will not start')
        return
    import main as bot_main
    await bot_main.dp.start_polling(bot_main.bot, skip_updates=True)


async def main():
    await asyncio.gather(
        run_dashboard(),
        run_bot(),
    )


if __name__ == '__main__':
    asyncio.run(main())
