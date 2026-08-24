"""轻量级 SQLite 持久化层（过渡方案）

用单表 key-value（value 为 JSON 文本）替换原来的 JSON 文件存储，
提供原子性、并发安全和单一数据源。后续拆模块时可平滑升级为 SQLAlchemy 多表。
"""
import json
import os
import sqlite3

# 数据库文件放在 backend 的上一级 data/ 目录下（与 models/、users/ 同级，运行时数据）
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'ea.db')


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化数据库（建表）。幂等，可重复调用。"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS store (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        ''')


def get(key, default=None):
    """读取一个 key 对应的 JSON 值；不存在或解析失败返回 default。"""
    with _conn() as conn:
        row = conn.execute('SELECT value FROM store WHERE key = ?', (key,)).fetchone()
    if row is None:
        return default
    try:
        return json.loads(row['value'])
    except (json.JSONDecodeError, TypeError):
        return default


def set(key, value):
    """写入一个 key 对应的 JSON 值（upsert）。"""
    with _conn() as conn:
        conn.execute(
            'INSERT INTO store (key, value) VALUES (?, ?) '
            'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
            (key, json.dumps(value, ensure_ascii=False))
        )


def delete(key):
    """删除一个 key。"""
    with _conn() as conn:
        conn.execute('DELETE FROM store WHERE key = ?', (key,))


def keys(prefix=''):
    """列出所有以 prefix 开头的 key。"""
    with _conn() as conn:
        rows = conn.execute('SELECT key FROM store WHERE key LIKE ?', (prefix + '%',)).fetchall()
    return [r['key'] for r in rows]
