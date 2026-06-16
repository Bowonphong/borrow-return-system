"""
database.py — SQLite operations for Borrow & Return System
Tables: users, items, borrow_records
"""

import sqlite3
import os
from config import DB_PATH


# ─────────────────────────────────────────────
#  Connection helper
# ─────────────────────────────────────────────
def get_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)  # รอ 10 วิถ้า DB ถูก lock
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")  # WAL mode รองรับ concurrent read+write
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─────────────────────────────────────────────
#  Init / Create tables
# ─────────────────────────────────────────────
def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            name             TEXT    NOT NULL,
            face_encoding    BLOB,
            face_image_path  TEXT,
            created_at       TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            barcode     TEXT    UNIQUE NOT NULL,
            name        TEXT    NOT NULL,
            description TEXT    DEFAULT '',
            created_at  TEXT    DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS borrow_records (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL REFERENCES users(id),
            item_id     INTEGER NOT NULL REFERENCES items(id),
            borrow_time TEXT    DEFAULT (datetime('now','localtime')),
            return_time TEXT,
            status      TEXT    DEFAULT 'borrowed'
        );
    """)

    conn.commit()
    conn.close()


# ─────────────────────────────────────────────
#  Users
# ─────────────────────────────────────────────
def add_user(name: str, face_encoding_bytes: bytes | None, face_image_path: str | None) -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO users (name, face_encoding, face_image_path) VALUES (?,?,?)",
        (name, face_encoding_bytes, face_image_path),
    )
    conn.commit()
    uid = cur.lastrowid
    conn.close()
    return uid


def get_all_users() -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        """SELECT id, name, face_image_path, created_at,
                  (face_encoding IS NOT NULL) AS has_encoding
           FROM users ORDER BY name"""
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_users_with_encodings() -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, face_encoding FROM users WHERE face_encoding IS NOT NULL"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_user(user_id: int):
    conn = get_db()
    try:
        # ดึง path รูปก่อนลบ
        row = conn.execute("SELECT face_image_path FROM users WHERE id=?", (user_id,)).fetchone()
        # ลบ borrow_records ที่ผูกกับ user นี้ก่อน (cascade)
        conn.execute("DELETE FROM borrow_records WHERE user_id=?", (user_id,))
        # ลบ user
        conn.execute("DELETE FROM users WHERE id=?", (user_id,))
        conn.commit()
        # ลบไฟล์รูปหลัง commit
        if row and row["face_image_path"]:
            try:
                os.remove(row["face_image_path"])
            except OSError:
                pass
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_user(user_id: int, name: str | None,
                face_encoding_bytes: bytes | None = None,
                face_image_path: str | None = None,
                replace_image: bool = False):
    """อัปเดตชื่อและ/หรือ face encoding ของผู้ใช้"""
    conn = get_db()
    try:
        if name is not None:
            conn.execute("UPDATE users SET name=? WHERE id=?", (name, user_id))
        if replace_image and face_encoding_bytes is not None:
            # ดึง path รูปเก่า
            row = conn.execute("SELECT face_image_path FROM users WHERE id=?", (user_id,)).fetchone()
            conn.execute(
                "UPDATE users SET face_encoding=?, face_image_path=? WHERE id=?",
                (face_encoding_bytes, face_image_path, user_id),
            )
            conn.commit()
            # ลบไฟล์รูปเก่า
            if row and row["face_image_path"]:
                try:
                    os.remove(row["face_image_path"])
                except OSError:
                    pass
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────
#  Items
# ─────────────────────────────────────────────
def add_item(barcode: str, name: str, description: str = "") -> int:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO items (barcode, name, description) VALUES (?,?,?)",
        (barcode, name, description),
    )
    conn.commit()
    iid = cur.lastrowid
    conn.close()
    return iid


def get_all_items() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM items ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_item_by_barcode(barcode: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM items WHERE barcode=?", (barcode,)).fetchone()
    conn.close()
    return dict(row) if row else None


def delete_item(item_id: int):
    conn = get_db()
    try:
        # ลบ borrow_records ที่ผูกกับ item นี้ก่อน (cascade)
        conn.execute("DELETE FROM borrow_records WHERE item_id=?", (item_id,))
        conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def update_item(item_id: int, name: str | None, description: str | None):
    """อัปเดตชื่อและคำอธิบายสิ่งของ"""
    conn = get_db()
    try:
        if name is not None:
            conn.execute("UPDATE items SET name=? WHERE id=?", (name, item_id))
        if description is not None:
            conn.execute("UPDATE items SET description=? WHERE id=?", (description, item_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ─────────────────────────────────────────────
#  Borrow / Return
# ─────────────────────────────────────────────
def borrow_item(user_id: int, item_id: int) -> tuple[int | None, str]:
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM borrow_records WHERE item_id=? AND status='borrowed'",
        (item_id,),
    ).fetchone()
    if existing:
        conn.close()
        return None, "สิ่งของนี้ถูกยืมอยู่แล้ว"

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO borrow_records (user_id, item_id) VALUES (?,?)",
        (user_id, item_id),
    )
    conn.commit()
    rid = cur.lastrowid
    conn.close()
    return rid, "success"


def return_item_by_barcode(barcode: str) -> tuple[dict | None, str]:
    conn = get_db()
    record = conn.execute(
        """
        SELECT br.id, br.user_id, br.item_id,
               u.name AS user_name, i.name AS item_name, i.barcode
        FROM borrow_records br
        JOIN items  i ON br.item_id  = i.id
        JOIN users  u ON br.user_id  = u.id
        WHERE i.barcode = ? AND br.status = 'borrowed'
        """,
        (barcode,),
    ).fetchone()

    if not record:
        conn.close()
        return None, "ไม่พบรายการยืมของชิ้นนี้"

    conn.execute(
        "UPDATE borrow_records SET status='returned', return_time=datetime('now','localtime') WHERE id=?",
        (record["id"],),
    )
    conn.commit()
    conn.close()
    return dict(record), "success"


def get_borrowed_by_user(user_id: int) -> list[dict]:
    """รายการที่ผู้ใช้ยืมอยู่ในขณะนี้"""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT br.id, i.barcode, i.name AS item_name
        FROM borrow_records br
        JOIN items i ON br.item_id = i.id
        WHERE br.user_id = ? AND br.status = 'borrowed'
        """,
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def do_return(record_id: int):
    conn = get_db()
    conn.execute(
        "UPDATE borrow_records SET status='returned', return_time=datetime('now','localtime') WHERE id=?",
        (record_id,),
    )
    conn.commit()
    conn.close()


def check_user_borrowed_item(user_id: int, item_id: int) -> dict | None:
    """ตรวจว่าผู้ใช้คนนี้ยืมของชิ้นนี้อยู่หรือไม่ คืน record หรือ None"""
    conn = get_db()
    row = conn.execute(
        """
        SELECT br.id, br.user_id, br.item_id,
               u.name AS user_name, i.name AS item_name
        FROM borrow_records br
        JOIN users u ON br.user_id = u.id
        JOIN items i ON br.item_id = i.id
        WHERE br.user_id = ? AND br.item_id = ? AND br.status = 'borrowed'
        """,
        (user_id, item_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ─────────────────────────────────────────────
#  History / Status
# ─────────────────────────────────────────────
def get_history(limit: int = 200) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT br.id, u.name AS user_name, i.name AS item_name, i.barcode,
               br.borrow_time, br.return_time, br.status
        FROM borrow_records br
        JOIN users u ON br.user_id = u.id
        JOIN items i ON br.item_id = i.id
        ORDER BY br.borrow_time DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_history_by_item(item_id: int) -> list[dict]:
    """ประวัติการยืม-คืนของสิ่งของชิ้นนี้"""
    conn = get_db()
    rows = conn.execute(
        """
        SELECT br.id, u.name AS user_name, i.name AS item_name, i.barcode,
               br.borrow_time, br.return_time, br.status
        FROM borrow_records br
        JOIN users u ON br.user_id = u.id
        JOIN items i ON br.item_id = i.id
        WHERE br.item_id = ?
        ORDER BY br.borrow_time DESC
        """,
        (item_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_borrow_record(record_id: int):
    """ลบประวัติการยืม-คืน 1 รายการ"""
    conn = get_db()
    try:
        conn.execute("DELETE FROM borrow_records WHERE id=?", (record_id,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def get_currently_borrowed() -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT br.id, br.user_id, u.name AS user_name,
               i.name AS item_name, i.barcode, br.borrow_time,
               CAST(JULIANDAY('now') - JULIANDAY(br.borrow_time) AS INTEGER) AS days_borrowed
        FROM borrow_records br
        JOIN users u ON br.user_id = u.id
        JOIN items i ON br.item_id = i.id
        WHERE br.status = 'borrowed'
        ORDER BY br.borrow_time DESC
        """,
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
