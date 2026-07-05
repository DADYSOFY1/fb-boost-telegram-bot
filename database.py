import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Iterable


class DB:
    def __init__(self, path: str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.init()

    def init(self):
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            custom_name TEXT,
            joined_at TEXT NOT NULL,
            is_removed INTEGER DEFAULT 0,
            subscription_until TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS redeem_codes (
            code TEXT PRIMARY KEY,
            label TEXT,
            duration_hours INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            used_by INTEGER,
            used_at TEXT
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS stats (
            key TEXT PRIMARY KEY,
            value INTEGER NOT NULL DEFAULT 0
        )''')
        self.conn.commit()

    def now(self) -> str:
        return datetime.utcnow().isoformat(timespec='seconds')

    def add_user(self, user_id: int, username: str = '', first_name: str = ''):
        c = self.conn.cursor()
        c.execute(
            '''INSERT INTO users(user_id, username, first_name, joined_at, is_removed)
               VALUES(?,?,?,?,0)
               ON CONFLICT(user_id) DO UPDATE SET
               username=excluded.username,
               first_name=excluded.first_name''',
            (user_id, username or '', first_name or '', self.now())
        )
        self.conn.commit()

    def remove_user(self, user_id: int):
        self.conn.execute('UPDATE users SET is_removed=1 WHERE user_id=?', (user_id,))
        self.conn.commit()

    def set_custom_name(self, user_id: int, name: str):
        self.conn.execute('UPDATE users SET custom_name=? WHERE user_id=?', (name, user_id))
        self.conn.commit()

    def set_subscription_hours(self, user_id: int, hours: int):
        until = datetime.utcnow() + timedelta(hours=hours)
        self.conn.execute(
            '''INSERT INTO users(user_id, username, first_name, joined_at, is_removed, subscription_until)
               VALUES(?,?,?,?,0,?)
               ON CONFLICT(user_id) DO UPDATE SET
                   subscription_until=excluded.subscription_until,
                   is_removed=0''',
            (user_id, '', '', self.now(), until.isoformat(timespec='seconds'))
        )
        self.conn.commit()
        return until

    def add_subscription_hours(self, user_id: int, hours: int):
        """يمدد الاشتراك بعدد ساعات إضافية."""
        row = self.get_user(user_id)
        now = datetime.utcnow()
        base = now
        if row and row['subscription_until']:
            try:
                current = datetime.fromisoformat(row['subscription_until'])
                if current > now:
                    base = current
            except Exception:
                pass
        until = base + timedelta(hours=hours)
        self.conn.execute(
            '''INSERT INTO users(user_id, username, first_name, joined_at, is_removed, subscription_until)
               VALUES(?,?,?,?,0,?)
               ON CONFLICT(user_id) DO UPDATE SET
                   subscription_until=excluded.subscription_until,
                   is_removed=0''',
            (user_id, '', '', self.now(), until.isoformat(timespec='seconds'))
        )
        self.conn.commit()
        return until

    def get_user(self, user_id: int):
        return self.conn.execute('SELECT * FROM users WHERE user_id=?', (user_id,)).fetchone()

    def all_active_users(self) -> Iterable[sqlite3.Row]:
        return self.conn.execute('SELECT * FROM users WHERE is_removed=0').fetchall()

    def create_code(self, code: str, duration_hours: int, label: str = ''):
        self.conn.execute(
            'INSERT INTO redeem_codes(code,label,duration_hours,created_at) VALUES(?,?,?,?)',
            (code, label, duration_hours, self.now())
        )
        self.conn.commit()

    def get_code(self, code: str):
        return self.conn.execute('SELECT * FROM redeem_codes WHERE code=?', (code,)).fetchone()

    def use_code(self, code: str, user_id: int) -> Optional[int]:
        row = self.get_code(code)
        if not row or row['used_by']:
            return None
        self.conn.execute(
            'UPDATE redeem_codes SET used_by=?, used_at=? WHERE code=?',
            (user_id, self.now(), code)
        )
        self.conn.commit()
        return int(row['duration_hours'])

    def inc(self, key: str, amount: int = 1):
        self.conn.execute(
            'INSERT INTO stats(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=value+?',
            (key, amount, amount)
        )
        self.conn.commit()

    def get_stat(self, key: str) -> int:
        row = self.conn.execute('SELECT value FROM stats WHERE key=?', (key,)).fetchone()
        return int(row['value']) if row else 0

    def counts(self):
        users = self.conn.execute('SELECT COUNT(*) c FROM users WHERE is_removed=0').fetchone()['c']
        removed = self.conn.execute('SELECT COUNT(*) c FROM users WHERE is_removed=1').fetchone()['c']
        codes = self.conn.execute('SELECT COUNT(*) c FROM redeem_codes').fetchone()['c']
        unused = self.conn.execute('SELECT COUNT(*) c FROM redeem_codes WHERE used_by IS NULL').fetchone()['c']
        return dict(
            users=users,
            removed=removed,
            codes=codes,
            unused=unused,
            requests=self.get_stat('requests')
        )


def is_subscribed(row) -> bool:
    if not row or row['is_removed']:
        return False
    if not row['subscription_until']:
        return False
    try:
        return datetime.fromisoformat(row['subscription_until']) > datetime.utcnow()
    except Exception:
        return False
