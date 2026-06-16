"""
main.py — FastAPI backend for Borrow & Return System
รัน: python main.py  (หรือ uvicorn main:app --reload)
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import os
import socket

import config as cfg
import database as db
import face_manager as fm
import ha_integration as ha

# ─── Startup ────────────────────────────────────────────────
db.init_db()
fm.ensure_dirs()   # สร้าง data/faces ถ้ายังไม่มี

app = FastAPI(title="Borrow & Return System", version="1.0")
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/faces", StaticFiles(directory=cfg.FACES_DIR), name="faces")


# ─────────────────────────────────────────────────────────────
#  Pydantic models
# ─────────────────────────────────────────────────────────────
class ItemCreate(BaseModel):
    barcode: str
    name: str
    description: str = ""


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class UserCreate(BaseModel):
    name: str


class BorrowRequest(BaseModel):
    user_id: int
    barcode: str


class ReturnRequest(BaseModel):
    barcode: Optional[str] = None
    user_id: Optional[int] = None


class FrameRequest(BaseModel):
    image: str  # base64-encoded JPEG/PNG from browser


class UserCreateWithImage(BaseModel):
    name: str
    image: str  # base64-encoded face image from browser


class UserUpdate(BaseModel):
    name: Optional[str] = None
    image: Optional[str] = None  # base64-encoded new face image (ถ้าต้องการเปลี่ยนรูป)


class SmartScanRequest(BaseModel):
    user_id: int
    barcode: str


# ─────────────────────────────────────────────────────────────
#  Static / Root
# ─────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    with open("static/index.html", encoding="utf-8") as f:
        return f.read()


@app.get("/admin", response_class=HTMLResponse)
async def admin_page():
    with open("static/admin.html", encoding="utf-8") as f:
        return f.read()


# ─────────────────────────────────────────────────────────────
#  Camera endpoints
# ─────────────────────────────────────────────────────────────
@app.get("/api/camera/preview")
async def camera_preview():
    img = fm.capture_frame_as_base64()
    if not img:
        raise HTTPException(status_code=500, detail="ไม่สามารถเปิดกล้องได้")
    return {"image": img}


@app.post("/api/camera/recognize")
async def recognize_face():
    user, message = fm.recognize_face()
    if user is None:
        return {"success": False, "message": message}
    return {"success": True, "user": user, "message": "จดจำใบหน้าสำเร็จ"}


@app.post("/api/camera/recognize_frame")
async def recognize_face_from_frame(body: FrameRequest):
    """รับ base64 frame จาก browser WebRTC และจดจำใบหน้าโดยไม่ต้องเปิดกล้องฝั่ง backend"""
    user, message = fm.recognize_face_from_frame(body.image)
    if user is None:
        return {"success": False, "message": message}
    return {"success": True, "user": user, "message": "จดจำใบหน้าสำเร็จ"}


# ─────────────────────────────────────────────────────────────
#  Users
# ─────────────────────────────────────────────────────────────
@app.get("/api/users")
async def list_users():
    return db.get_all_users()


@app.post("/api/users")
async def create_user(body: UserCreate):
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="กรุณาใส่ชื่อ")
    uid, msg = fm.add_user_face(body.name.strip())
    if uid is None:
        raise HTTPException(status_code=400, detail=msg)
    return {"id": uid, "message": f"เพิ่ม '{body.name}' สำเร็จ"}


@app.post("/api/users/with_image")
async def create_user_with_image(body: UserCreateWithImage):
    """เพิ่มผู้ใช้พร้อม face encoding จากรูปที่อัปโหลด (base64)"""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="กรุณาใส่ชื่อ")
    uid, msg = fm.add_user_face_from_image(body.name.strip(), body.image)
    if uid is None:
        raise HTTPException(status_code=400, detail=msg)
    return {"id": uid, "message": f"เพิ่ม '{body.name}' สำเร็จ (สร้าง face encoding เรียบร้อย)"}


@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int):
    db.delete_user(user_id)
    return {"message": "ลบผู้ใช้สำเร็จ"}


@app.patch("/api/users/{user_id}")
async def update_user(user_id: int, body: UserUpdate):
    """อัปเดตชื่อ และ/หรือรูปใบหน้าผู้ใช้"""
    if body.name is not None and not body.name.strip():
        raise HTTPException(status_code=400, detail="ชื่อไม่ควรว่าง")
    name = body.name.strip() if body.name else None
    ok, msg = fm.update_user_face_from_image(user_id, name, body.image)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"message": "อัปเดตสำเร็จ"}


# ─────────────────────────────────────────────────────────────
#  Items
# ─────────────────────────────────────────────────────────────
@app.get("/api/items")
async def list_items():
    return db.get_all_items()


@app.post("/api/items")
async def create_item(body: ItemCreate):
    if not body.barcode.strip() or not body.name.strip():
        raise HTTPException(status_code=400, detail="กรุณาใส่บาร์โค้ดและชื่อสิ่งของ")
    try:
        iid = db.add_item(body.barcode.strip(), body.name.strip(), body.description.strip())
        return {"id": iid, "message": f"เพิ่ม '{body.name}' สำเร็จ"}
    except Exception:
        raise HTTPException(status_code=400, detail="บาร์โค้ดนี้มีอยู่ในระบบแล้ว")


@app.delete("/api/items/{item_id}")
async def delete_item(item_id: int):
    db.delete_item(item_id)
    return {"message": "ลบสิ่งของสำเร็จ"}


@app.patch("/api/items/{item_id}")
async def update_item(item_id: int, body: ItemUpdate):
    """อัปเดตชื่อและคำอธิบายสิ่งของ"""
    if body.name is not None and not body.name.strip():
        raise HTTPException(status_code=400, detail="ชื่อไม่ควรว่าง")
    db.update_item(
        item_id,
        body.name.strip() if body.name is not None else None,
        body.description.strip() if body.description is not None else None,
    )
    return {"message": "อัปเดตสำเร็จ"}


@app.get("/api/items/barcode/{barcode}")
async def lookup_barcode(barcode: str):
    item = db.get_item_by_barcode(barcode)
    if not item:
        return {"found": False}
    return {"found": True, "item": item}


# ─────────────────────────────────────────────────────────────
#  Borrow
# ─────────────────────────────────────────────────────────────
@app.post("/api/borrow")
async def borrow(body: BorrowRequest, bg: BackgroundTasks):
    item = db.get_item_by_barcode(body.barcode)
    if not item:
        raise HTTPException(status_code=404, detail="ไม่พบสิ่งของในระบบ (บาร์โค้ดไม่ตรง)")

    rid, msg = db.borrow_item(body.user_id, item["id"])
    if rid is None:
        raise HTTPException(status_code=400, detail=msg)

    borrowed = db.get_currently_borrowed()
    users = db.get_all_users()
    u = next((x for x in users if x["id"] == body.user_id), None)
    if u:
        bg.add_task(ha.notify_borrow, u["name"], item["name"], len(borrowed))

    return {"success": True, "record_id": rid,
            "message": f"บันทึกการยืม '{item['name']}' สำเร็จ"}


# ────────────────────────────────────────────────────────────
#  Smart Scan — ยืม/คืนอัตโนมัติ
# ────────────────────────────────────────────────────────────
@app.post("/api/smart_scan")
async def smart_scan(body: SmartScanRequest, bg: BackgroundTasks):
    """
    สแกนอัจฉริยะ: ตรวจว่าผู้ใช้ยืมของชิ้นนี้อยู่หรือไม่
    - ยืมอยู่ → คืนทันที
    - ยังไม่เคยยืม → ยืมทันที
    """
    item = db.get_item_by_barcode(body.barcode)
    if not item:
        raise HTTPException(status_code=404, detail="ไม่พบบาร์โค้ดนี้ในระบบ")

    # เช็คว่าผู้ใช้คนนี้ยืมของชิ้นนี้อยู่หรือไม่
    user_record = db.check_user_borrowed_item(body.user_id, item["id"])

    if user_record:
        # ==== คืนของ ====
        db.do_return(user_record["id"])
        total = len(db.get_currently_borrowed())
        users = db.get_all_users()
        u = next((x for x in users if x["id"] == body.user_id), None)
        user_name = u["name"] if u else str(body.user_id)
        bg.add_task(ha.notify_return, user_name, item["name"], total)
        return {
            "action":  "return",
            "success": True,
            "message": f"คืน '{item['name']}' สำเร็จ",
            "item_name": item["name"],
        }
    else:
        # ==== ยืมของ ====
        # ตรวจว่าของชิ้นนี้ถูกคนอื่นยืมอยู่หรือไม่ (เฎพาะคนนี้เท่านั้นที่คืนได้)
        rid, msg = db.borrow_item(body.user_id, item["id"])
        if rid is None:
            raise HTTPException(status_code=400, detail=msg)
        borrowed = db.get_currently_borrowed()
        users = db.get_all_users()
        u = next((x for x in users if x["id"] == body.user_id), None)
        if u:
            bg.add_task(ha.notify_borrow, u["name"], item["name"], len(borrowed))
        return {
            "action":  "borrow",
            "success": True,
            "message": f"ยืม '{item['name']}' สำเร็จ",
            "item_name": item["name"],
        }


# ─────────────────────────────────────────────────────────────
#  Return
# ─────────────────────────────────────────────────────────────
@app.post("/api/return")
async def return_item(body: ReturnRequest, bg: BackgroundTasks):
    # คืนผ่านบาร์โค้ด
    if body.barcode:
        record, msg = db.return_item_by_barcode(body.barcode)
        if record is None:
            raise HTTPException(status_code=400, detail=msg)
        total = len(db.get_currently_borrowed())
        bg.add_task(ha.notify_return, record["user_name"], record["item_name"], total)
        return {"success": True, "message": f"คืน '{record['item_name']}' สำเร็จ", "record": record}

    # คืนผ่านใบหน้า (แสดงรายการที่ยืม)
    if body.user_id:
        items = db.get_borrowed_by_user(body.user_id)
        if not items:
            raise HTTPException(status_code=400, detail="ผู้ใช้นี้ไม่มีรายการยืมอยู่")
        return {"success": True, "pending_items": items}

    raise HTTPException(status_code=400, detail="กรุณาระบุ barcode หรือ user_id")


@app.post("/api/return/confirm/{record_id}")
async def confirm_return(record_id: int, bg: BackgroundTasks):
    db.do_return(record_id)
    total = len(db.get_currently_borrowed())
    bg.add_task(ha.push_full_status,
                len(db.get_all_users()), len(db.get_all_items()), total)
    return {"success": True, "message": "บันทึกการคืนสำเร็จ"}


# ─────────────────────────────────────────────────────────────
#  History & Status
# ─────────────────────────────────────────────────────────────
@app.get("/api/history")
async def history(limit: int = 200):
    return db.get_history(limit)


@app.get("/api/history/item/{item_id}")
async def item_history(item_id: int):
    return db.get_history_by_item(item_id)


@app.delete("/api/history/{record_id}")
async def delete_history_record(record_id: int):
    db.delete_borrow_record(record_id)
    return {"message": "ลบประวัติสำเร็จ"}


@app.get("/api/borrowed")
async def currently_borrowed():
    return db.get_currently_borrowed()


@app.get("/api/status")
async def status():
    users   = db.get_all_users()
    items   = db.get_all_items()
    borrowed = db.get_currently_borrowed()
    return {
        "total_users":      len(users),
        "total_items":      len(items),
        "currently_borrowed": len(borrowed),
        "system_status":    "online",
    }


def _find_available_port(host: str, start_port: int, max_tries: int = 10) -> int:
    """Return the first free port starting from start_port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        for port in range(start_port, start_port + max_tries):
            try:
                sock.bind((host, port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"ไม่สามารถหา port ว่างได้จาก {start_port} ถึง {start_port + max_tries - 1}")


# ─────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    import sys

    # Fix Unicode output on Windows terminal
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    requested_port = int(os.getenv("PORT", cfg.PORT))
    actual_port = _find_available_port(cfg.HOST, requested_port)

    print(f"[START] Borrow & Return System  ->  http://{cfg.HOST}:{actual_port}")
    uvicorn.run("main:app", host=cfg.HOST, port=actual_port, reload=False)
