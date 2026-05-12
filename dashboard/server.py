"""
Dashboard Web Server - لوحة تحكم البوت
"""
import asyncio
import html
import json
import os
import re
import sys
from pathlib import Path

from aiohttp import web

BOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BOT_DIR))

from database import DB
from services.proxy_manager import ProxyManager
from services.redeem import generate_code

DASHBOARD_PORT = int(os.environ.get('PORT', 5000))

db            = DB(str(BOT_DIR / 'data' / 'bot.db'))
proxy_manager = ProxyManager(str(BOT_DIR / 'proxies.txt'))

TEMPLATES_DIR = Path(__file__).parent / 'templates'

# ─── علامات HTML المسموح بها في الـ Broadcast ───
_ALLOWED_TAGS = {'b', 'strong', 'i', 'em', 'u', 's', 'strike', 'code', 'pre', 'a'}
_TAG_RE       = re.compile(r'<(/?)(\w+)([^>]*)>', re.IGNORECASE)


def _sanitize_html(text: str) -> str:
    """
    يسمح فقط بعلامات Telegram HTML المدعومة ويحذف الباقي.
    يمنع XSS وهياكل HTML المكسورة في الـ broadcast.
    """
    def _replace(m):
        closing = m.group(1)
        tag     = m.group(2).lower()
        attrs   = m.group(3)
        if tag not in _ALLOWED_TAGS:
            return ''
        # احتفظ بـ href فقط في وسم <a>
        safe_attrs = ''
        if tag == 'a':
            href = re.search(r'href=["\']([^"\']+)["\']', attrs)
            if href:
                safe_attrs = f' href="{html.escape(href.group(1))}"'
        return f'<{closing}{tag}{safe_attrs}>'

    return _TAG_RE.sub(_replace, text)


def json_resp(data, status=200):
    return web.Response(
        text=json.dumps(data, ensure_ascii=False, default=str),
        content_type='application/json',
        status=status
    )


# ─────────── API Routes ───────────

async def get_stats(request):
    return json_resp(db.counts())


async def get_users(request):
    rows  = db.all_active_users()
    users = [dict(r) for r in rows]
    return json_resp({'users': users})


async def post_user(request):
    data    = await request.json()
    user_id = int(data.get('user_id', 0))
    name    = data.get('name', '')
    hours   = int(data.get('hours', 24))
    if not user_id:
        return json_resp({'error': 'user_id مطلوب'}, 400)
    db.add_user(user_id)
    if name:
        db.set_custom_name(user_id, name)
    until = db.set_subscription_hours(user_id, hours)
    return json_resp({'success': True, 'until': until.isoformat()})


async def delete_user(request):
    user_id = int(request.match_info['user_id'])
    db.remove_user(user_id)
    return json_resp({'success': True})


async def get_codes(request):
    rows  = db.conn.execute(
        'SELECT * FROM redeem_codes ORDER BY created_at DESC LIMIT 100'
    ).fetchall()
    codes = [dict(r) for r in rows]
    return json_resp({'codes': codes})


async def post_code(request):
    data  = await request.json()
    hours = int(data.get('hours', 24))
    label = data.get('label', f'{hours}h code')
    code  = generate_code()
    db.create_code(code, hours, label)
    return json_resp({'code': code, 'hours': hours})


async def get_proxies(request):
    proxies = proxy_manager.all()
    return json_resp({'proxies': proxies, 'count': len(proxies)})


async def post_proxies(request):
    data  = await request.json()
    text  = data.get('proxies', '')
    count = proxy_manager.add_many(text)
    return json_resp({'added': count, 'total': proxy_manager.count()})


async def delete_proxies(request):
    proxy_manager.clear()
    return json_resp({'success': True})


async def check_proxies(request):
    """فحص صحة كل البروكسيات وحذف التالف تلقائياً."""
    result = await proxy_manager.check_all_and_remove_bad()
    return json_resp(result)


async def post_broadcast(request):
    data    = await request.json()
    message = data.get('message', '').strip()
    if not message:
        return json_resp({'error': 'الرسالة فارغة'}, 400)

    # تنظيف HTML لمنع الرسائل المكسورة
    message = _sanitize_html(message)

    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if not token:
        return json_resp({'error': 'لا يوجد TELEGRAM_BOT_TOKEN'}, 500)

    import httpx
    users  = db.all_active_users()
    sent   = failed = 0
    async with httpx.AsyncClient(timeout=10) as client:
        for u in users:
            try:
                resp = await client.post(
                    f'https://api.telegram.org/bot{token}/sendMessage',
                    json={
                        'chat_id':    u['user_id'],
                        'text':       message,
                        'parse_mode': 'HTML',
                    }
                )
                if resp.status_code == 200:
                    sent += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
    return json_resp({'sent': sent, 'failed': failed})


async def index(request):
    html_page = (TEMPLATES_DIR / 'index.html').read_text(encoding='utf-8')
    return web.Response(text=html_page, content_type='text/html')


def make_app():
    app = web.Application()
    app.router.add_get('/',                        index)
    app.router.add_get('/api/stats',               get_stats)
    app.router.add_get('/api/users',               get_users)
    app.router.add_post('/api/users',              post_user)
    app.router.add_delete('/api/users/{user_id}',  delete_user)
    app.router.add_get('/api/codes',               get_codes)
    app.router.add_post('/api/codes',              post_code)
    app.router.add_get('/api/proxies',             get_proxies)
    app.router.add_post('/api/proxies',            post_proxies)
    app.router.add_delete('/api/proxies',          delete_proxies)
    app.router.add_post('/api/proxies/check',      check_proxies)
    app.router.add_post('/api/broadcast',          post_broadcast)
    return app


async def main():
    app    = make_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', DASHBOARD_PORT)
    # Allow all hosts for Replit proxy compatibility
    await site.start()
    print(f'🌐 Bot Dashboard يعمل على: http://0.0.0.0:{DASHBOARD_PORT}')
    print(f'📊 قاعدة البيانات: {BOT_DIR / "data" / "bot.db"}')
    await asyncio.Event().wait()


if __name__ == '__main__':
    asyncio.run(main())
