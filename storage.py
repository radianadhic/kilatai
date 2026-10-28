# -*- coding: utf-8 -*-
"""
Lapisan penyimpanan Kilat AI - bergaya platform AI modern, TANPA dependensi eksternal.

Arsitektur berlapis (mirip platform AI besar, versi lokal):
  1. SQLite  -> database relasional : percakapan, pesan, jejak audit   [stdlib]
  2. Valkey  -> cache & antrean event (pengganti Redis, protokol RESP) [socket murni]
  3. File    -> workspace sebagai object-storage sederhana

Valkey bersifat OPSIONAL: kalau tidak berjalan, semua fitur tetap bekerja
(cache dilewati, event hanya masuk tabel audit di SQLite).

Env (dibaca app.py):
  ARENA_DB_PATH     - lokasi file SQLite (default: <folder app>/data/kilat.db)
  ARENA_VALKEY_URL  - alamat Valkey     (default: redis://127.0.0.1:6379)
"""

import json
import os
import socket
import sqlite3
import time
import urllib.parse

DB_PATH = None
VALKEY = None  # {"host","port","password","down_until"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations(
    id      TEXT PRIMARY KEY,
    title   TEXT DEFAULT '',
    created INTEGER,
    updated INTEGER
);
CREATE TABLE IF NOT EXISTS messages(
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_id TEXT NOT NULL,
    seq     INTEGER,
    role    TEXT,
    content TEXT DEFAULT '',
    data    TEXT,
    created INTEGER
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conv_id, seq);
CREATE TABLE IF NOT EXISTS audit(
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    ts     INTEGER,
    kind   TEXT,
    detail TEXT
);
"""


# ----------------------------------------------------------------------------
# Inisialisasi
# ----------------------------------------------------------------------------
def init(db_path, valkey_url):
    global DB_PATH, VALKEY
    DB_PATH = db_path
    try:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        conn = _db()
        with conn:
            conn.executescript(SCHEMA)
        conn.close()
    except OSError as e:
        print("  [storage] SQLite gagal: %s" % e)

    if valkey_url:
        VALKEY = _parse_valkey_url(valkey_url)
        if not _valkey_alive():
            print("  [storage] Valkey tidak merespons di %s - fitur cache/event dilewati (opsional)" % valkey_url)
    return {"db": DB_PATH, "valkey": bool(VALKEY and _valkey_alive())}


def _db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ----------------------------------------------------------------------------
# Percakapan & pesan (relasional)
# ----------------------------------------------------------------------------
def list_conversations():
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT id,title,created,updated FROM conversations ORDER BY updated DESC"
        ).fetchall()
        conn.close()
        return [
            {"id": r[0], "title": r[1] or "", "created": r[2] or 0, "updated": r[3] or 0}
            for r in rows
        ]
    except sqlite3.Error:
        return []


def get_messages(conv_id):
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT role,content,data FROM messages WHERE conv_id=? ORDER BY seq", (conv_id,)
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []
    msgs = []
    for role, content, data in rows:
        m = {"role": role or "user", "content": content or ""}
        if data:
            try:
                extra = json.loads(data)
                if isinstance(extra, dict):
                    m.update(extra)
            except ValueError:
                pass
        msgs.append(m)
    return msgs


def save_conversation(conv):
    """Upsert satu percakapan (metdata + seluruh pesan)."""
    now = int(time.time() * 1000)
    cid = str(conv.get("id") or "")
    if not cid:
        return False
    title = str(conv.get("title") or "")[:200]
    created = int(conv.get("created") or now)
    conn = _db()
    try:
        with conn:
            conn.execute(
                """INSERT INTO conversations(id,title,created,updated) VALUES(?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET title=excluded.title, updated=excluded.updated""",
                (cid, title, created, now),
            )
            conn.execute("DELETE FROM messages WHERE conv_id=?", (cid,))
            for i, m in enumerate(conv.get("messages") or []):
                role = str(m.get("role") or "user")
                content = str(m.get("content") or "")
                extra = {k: v for k, v in m.items() if k not in ("role", "content")}
                conn.execute(
                    "INSERT INTO messages(conv_id,seq,role,content,data,created) VALUES(?,?,?,?,?,?)",
                    (cid, i, role, content, json.dumps(extra, ensure_ascii=False) if extra else None, now),
                )
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def delete_conversation(conv_id):
    conn = _db()
    try:
        with conn:
            conn.execute("DELETE FROM messages WHERE conv_id=?", (conv_id,))
            conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
        return True
    except sqlite3.Error:
        return False
    finally:
        conn.close()


# ----------------------------------------------------------------------------
# Jejak audit (penting untuk pemakaian treasury)
# ----------------------------------------------------------------------------
def audit(kind, detail=""):
    """Catat event: selalu ke SQLite, plus kirim ke antrean Valkey (best-effort)."""
    ts = int(time.time() * 1000)
    try:
        conn = _db()
        with conn:
            conn.execute("INSERT INTO audit(ts,kind,detail) VALUES(?,?,?)", (ts, kind, str(detail)[:500]))
        conn.close()
    except sqlite3.Error:
        pass
    event_valkey(kind, detail, ts)


def audit_recent(limit=50):
    try:
        conn = _db()
        rows = conn.execute(
            "SELECT ts,kind,detail FROM audit ORDER BY id DESC LIMIT ?", (int(limit),)
        ).fetchall()
        conn.close()
        return [{"ts": r[0], "kind": r[1], "detail": r[2] or ""} for r in rows]
    except sqlite3.Error:
        return []


# ----------------------------------------------------------------------------
# Klien Valkey (protokol RESP) - murni socket, tanpa dependensi
# ----------------------------------------------------------------------------
def _parse_valkey_url(url):
    try:
        u = urllib.parse.urlparse(url)
        return {
            "host": u.hostname or "127.0.0.1",
            "port": u.port or 6379,
            "password": u.password or "",
            "down_until": 0,
        }
    except (ValueError, AttributeError):
        return None


def _valkey_command(*args):
    """Kirim perintah RESP, kembalikan hasilnya. None jika server tidak aktif."""
    if not VALKEY or time.time() < VALKEY.get("down_until", 0):
        return None
    try:
        with socket.create_connection((VALKEY["host"], VALKEY["port"]), timeout=2) as sock:
            f = sock.makefile("rb")
            try:
                if VALKEY.get("password"):
                    _resp_send(sock, ("AUTH", VALKEY["password"]))
                    _resp_read(f)  # buang balasan AUTH
                _resp_send(sock, tuple(str(a) for a in args))
                return _resp_read(f)
            finally:
                f.close()
    except (OSError, ValueError):
        VALKEY["down_until"] = time.time() + 10  # jangan hantam server tiap request
        return None


def _resp_send(sock, args):
    buf = ["*%d\r\n" % len(args)]
    for a in args:
        b = a.encode("utf-8")
        buf.append("$%d\r\n" % len(b))
        buf.append(b.decode("latin-1") + "\r\n")
    sock.sendall("".join(buf).encode("latin-1"))
    return sock


def _resp_read(f):
    line = f.readline()
    if not line:
        return None
    t, rest = line[:1], line[1:-2]
    if t == b"+":
        return rest.decode("utf-8", "replace")
    if t == b"-":
        raise ValueError("Valkey error: " + rest.decode("utf-8", "replace"))
    if t == b":":
        return int(rest)
    if t == b"$":
        n = int(rest)
        if n == -1:
            return None
        data = f.read(n)
        f.read(2)  # CRLF
        return data.decode("utf-8", "replace")
    if t == b"*":
        n = int(rest)
        if n == -1:
            return None
        return [_resp_read(f) for _ in range(n)]
    return None


def _valkey_alive():
    try:
        return _valkey_command("PING") == "PONG"
    except ValueError:
        return False


def valkey_ok():
    return bool(VALKEY and _valkey_alive())


# ---- fitur cache (pengganti Redis cache) ----
def cache_get(key):
    return _valkey_command("GET", key)


def cache_set(key, ttl, value):
    return _valkey_command("SETEX", key, int(ttl), value)


def cache_invalidate(*keys):
    return _valkey_command("DEL", *keys) if keys else None


# ---- antrean event (pengganti Redis list/stream) ----
def event_valkey(kind, detail="", ts=None):
    if not VALKEY:
        return
    ev = json.dumps({"ts": ts or int(time.time() * 1000), "kind": kind, "detail": str(detail)[:500]},
                    ensure_ascii=False)
    _valkey_command("LPUSH", "events:audit", ev)
    _valkey_command("LTRIM", "events:audit", 0, 999)  # simpan 1000 event terakhir


def event_recent(limit=20):
    return _valkey_command("LRANGE", "events:audit", 0, int(limit) - 1)
