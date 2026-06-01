import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime, timedelta
from typing import Optional, Iterable

DATABASE_URL = os.environ.get('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is required. Add PostgreSQL plugin in Railway.")


class DB:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self.init()

    def _conn(self):
        return psycopg2.connect(self.dsn, cursor_factory=RealDictCursor)

    def _execute(self, query: str, params=None, fetchone=False, fetchall=False, commit=False):
        conn = self._conn()
        cur = conn.cursor()
        cur.execute(query, params or ())
        result = None
        if fetchone:
            result = cur.fetchone()
        elif fetchall:
            result = cur.fetchall()
        if commit:
            conn.commit()
        conn.close()
        return result

    def init(self):
        conn = self._conn()
        c = conn.cursor()

        c.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                custom_name TEXT,
                joined_at TIMESTAMP NOT NULL,
                is_removed INTEGER DEFAULT 0,
                subscription_until TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS redeem_codes (
                code TEXT PRIMARY KEY,
                label TEXT,
                duration_hours INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL,
                used_by BIGINT,
                used_at TIMESTAMP
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS proxies (
                id SERIAL PRIMARY KEY,
                proxy TEXT NOT NULL,
                country TEXT,
                is_active INTEGER DEFAULT 1,
                added_at TIMESTAMP NOT NULL,
                added_by BIGINT
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')

        c.execute('''
            CREATE TABLE IF NOT EXISTS stats (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL DEFAULT 0
            )
        ''')

        conn.commit()
        conn.close()
        print("[DB] PostgreSQL tables initialized.")

    def now(self) -> str:
        return datetime.utcnow().isoformat(timespec='seconds')

    def add_user(self, user_id: int, username: str = '', first_name: str = ''):
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            '''INSERT INTO users(user_id, username, first_name, joined_at, is_removed)
               VALUES(%s,%s,%s,%s,0)
               ON CONFLICT(user_id) DO UPDATE SET
               username=EXCLUDED.username,
               first_name=EXCLUDED.first_name''',
            (user_id, username or '', first_name or '', self.now())
        )
        conn.commit()
        conn.close()

    def remove_user(self, user_id: int):
        self._execute('UPDATE users SET is_removed=1 WHERE user_id=%s', (user_id,), commit=True)

    def restore_user(self, user_id: int):
        self._execute('UPDATE users SET is_removed=0 WHERE user_id=%s', (user_id,), commit=True)

    def set_custom_name(self, user_id: int, name: str):
        self._execute('UPDATE users SET custom_name=%s WHERE user_id=%s', (name, user_id), commit=True)

    def set_subscription_hours(self, user_id: int, hours: int):
        until = datetime.utcnow() + timedelta(hours=hours)
        self._execute(
            '''INSERT INTO users(user_id, username, first_name, joined_at, is_removed, subscription_until)
               VALUES(%s,%s,%s,%s,0,%s)
               ON CONFLICT(user_id) DO UPDATE SET
                   subscription_until=EXCLUDED.subscription_until,
                   is_removed=0''',
            (user_id, '', '', self.now(), until),
            commit=True
        )
        return until

    def add_subscription_hours(self, user_id: int, hours: int):
        row = self.get_user(user_id)
        now = datetime.utcnow()
        base = now
        if row and row['subscription_until']:
            try:
                current = row['subscription_until']
                if current > now:
                    base = current
            except Exception:
                pass
        until = base + timedelta(hours=hours)
        self._execute(
            '''INSERT INTO users(user_id, username, first_name, joined_at, is_removed, subscription_until)
               VALUES(%s,%s,%s,%s,0,%s)
               ON CONFLICT(user_id) DO UPDATE SET
                   subscription_until=EXCLUDED.subscription_until,
                   is_removed=0''',
            (user_id, '', '', self.now(), until),
            commit=True
        )
        return until

    def get_user(self, user_id: int):
        return self._execute('SELECT * FROM users WHERE user_id=%s', (user_id,), fetchone=True)

    def all_active_users(self) -> Iterable:
        return self._execute('SELECT * FROM users WHERE is_removed=0', fetchall=True)

    def all_users(self) -> Iterable:
        return self._execute('SELECT * FROM users', fetchall=True)

    def create_code(self, code: str, duration_hours: int, label: str = ''):
        self._execute(
            'INSERT INTO redeem_codes(code,label,duration_hours,created_at) VALUES(%s,%s,%s,%s)',
            (code, label, duration_hours, self.now()),
            commit=True
        )

    def get_code(self, code: str):
        return self._execute('SELECT * FROM redeem_codes WHERE code=%s', (code,), fetchone=True)

    def use_code(self, code: str, user_id: int) -> Optional[int]:
        row = self.get_code(code)
        if not row or row['used_by']:
            return None
        self._execute(
            'UPDATE redeem_codes SET used_by=%s, used_at=%s WHERE code=%s',
            (user_id, self.now(), code),
            commit=True
        )
        return int(row['duration_hours'])

    def all_codes(self) -> Iterable:
        return self._execute('SELECT * FROM redeem_codes', fetchall=True)

    def delete_code(self, code: str):
        self._execute('DELETE FROM redeem_codes WHERE code=%s', (code,), commit=True)

    def add_proxy(self, proxy: str, country: str = '', added_by: int = 0):
        conn = self._conn()
        c = conn.cursor()
        c.execute(
            'INSERT INTO proxies(proxy, country, is_active, added_at, added_by) VALUES(%s,%s,1,%s,%s) RETURNING id',
            (proxy, country or '', self.now(), added_by)
        )
        proxy_id = c.fetchone()['id']
        conn.commit()
        conn.close()
        return proxy_id

    def get_proxy(self, proxy_id: int):
        return self._execute('SELECT * FROM proxies WHERE id=%s', (proxy_id,), fetchone=True)

    def all_proxies(self, active_only: bool = True) -> Iterable:
        if active_only:
            return self._execute('SELECT * FROM proxies WHERE is_active=1', fetchall=True)
        return self._execute('SELECT * FROM proxies', fetchall=True)

    def remove_proxy(self, proxy_id: int):
        self._execute('UPDATE proxies SET is_active=0 WHERE id=%s', (proxy_id,), commit=True)

    def delete_proxy_permanently(self, proxy_id: int):
        self._execute('DELETE FROM proxies WHERE id=%s', (proxy_id,), commit=True)

    def pick_random_proxy(self) -> Optional:
        return self._execute(
            'SELECT * FROM proxies WHERE is_active=1 ORDER BY RANDOM() LIMIT 1',
            fetchone=True
        )

    def set_setting(self, key: str, value: str):
        conn = self._conn()
        conn.execute(
            'INSERT INTO settings(key, value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value',
            (key, value)
        )
        conn.commit()
        conn.close()

    def get_setting(self, key: str, default: str = '') -> str:
        row = self._execute('SELECT value FROM settings WHERE key=%s', (key,), fetchone=True)
        return row['value'] if row else default

    def all_settings(self) -> Iterable:
        return self._execute('SELECT * FROM settings', fetchall=True)

    def inc(self, key: str, amount: int = 1):
        self._execute(
            'INSERT INTO stats(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=stats.value+%s',
            (key, amount, amount),
            commit=True
        )

    def get_stat(self, key: str) -> int:
        row = self._execute('SELECT value FROM stats WHERE key=%s', (key,), fetchone=True)
        return int(row['value']) if row else 0

    def counts(self):
        users = self._execute('SELECT COUNT(*) c FROM users WHERE is_removed=0', fetchone=True)['c']
        removed = self._execute('SELECT COUNT(*) c FROM users WHERE is_removed=1', fetchone=True)['c']
        codes = self._execute('SELECT COUNT(*) c FROM redeem_codes', fetchone=True)['c']
        unused = self._execute('SELECT COUNT(*) c FROM redeem_codes WHERE used_by IS NULL', fetchone=True)['c']
        proxies = self._execute('SELECT COUNT(*) c FROM proxies WHERE is_active=1', fetchone=True)['c']
        return dict(
            users=users,
            removed=removed,
            codes=codes,
            unused=unused,
            proxies=proxies,
            requests=self.get_stat('requests')
        )


db = DB(DATABASE_URL)


def is_subscribed(row) -> bool:
    if not row or row['is_removed']:
        return False
    if not row['subscription_until']:
        return False
    try:
        return row['subscription_until'] > datetime.utcnow()
    except Exception:
        return False


def get_subscription_remaining(row) -> str:
    if not row or not row['subscription_until']:
        return 'منتهي'
    try:
        until = row['subscription_until']
        remaining = until - datetime.utcnow()
        if remaining.total_seconds() <= 0:
            return 'منتهي'
        days = remaining.days
        hours = remaining.seconds // 3600
        if days > 0:
            return f'{days} يوم و {hours} ساعة'
        return f'{hours} ساعة'
    except Exception:
        return 'غير معروف'
