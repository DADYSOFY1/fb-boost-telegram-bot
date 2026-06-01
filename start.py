"""
start.py - runs both the Telegram bot and the web dashboard concurrently
"""
import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# ── Initialize database first ────────────────────────
from database import db
# db auto-initializes on import via DB(path) instance

from dashboard.server import make_app, DASHBOARD_PORT
from aiohttp import web

import os
from aiogram import Bot

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

    # ⬅️ CRITICAL: delete any existing webhook before polling
    # This prevents "Conflict: terminated by other getUpdates request" errors
    await bot_main.bot.delete_webhook(drop_pending_updates=True)
    print('[BOT] Webhook deleted, starting polling...')

    try:
        await bot_main.dp.start_polling(bot_main.bot, skip_updates=True)
    finally:
        # Graceful cleanup
        await bot_main.bot.session.close()
        print('[BOT] Session closed.')


async def shutdown(signal_name: str = 'SIGTERM'):
    """Graceful shutdown handler."""
    print(f'\n[{signal_name}] Received shutdown signal. Cleaning up...')
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    print(f'[{signal_name}] Cancelled {len(tasks)} tasks.')


async def main():
    loop = asyncio.get_running_loop()

    # Register signal handlers for graceful shutdown
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(signal.Signals(s).name)))

    await asyncio.gather(
        run_dashboard(),
        run_bot(),
    )


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print('\n[start.py] Exited cleanly.')
